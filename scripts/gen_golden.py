"""Render the golden call set from scenario files.

Each ``tests/fixtures/golden/scenarios/<id>.yaml`` scripts one two-party call:
who speaks, what they say, the silence (or overlap) before each turn, and the
line condition. This script voices every turn with Kokoro TTS, lays the turns
out on one timeline, applies the line condition, and encodes the call as
``tests/fixtures/golden/calls/<id>.opus`` (mono, 24 kbps) with FFmpeg.

Output is reproducible for a given scenario, Kokoro version, and voice set:
timing jitter, line noise, and Kokoro's vocoder are all seeded from the scenario
id, and the Ogg container is written bit-exact, so re-rendering on the same
machine gives byte-identical files. Other machines may differ slightly
(floating-point and library versions).

Kokoro is *not* a library dependency. Install it in a separate environment
(Kokoro supports Python <= 3.12):

    python3.12 -m venv .venv-golden
    .venv-golden/bin/pip install "kokoro>=0.9" soundfile pyyaml
    .venv-golden/bin/python scripts/gen_golden.py            # all scenarios
    .venv-golden/bin/python scripts/gen_golden.py billing_01  # just one

Kokoro's English front end falls back to espeak-ng. On macOS the copy bundled
with ``espeakng-loader`` points at a non-existent build path; install it with
``brew install espeak-ng`` and this script picks it up (or set
``ESPEAK_LIBRARY`` / ``ESPEAK_DATA_PATH``).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "fixtures" / "golden"
SAMPLE_RATE = 24_000  # Kokoro's native rate

# Silence before a turn when the scenario doesn't set ``gap_ms``. Agents answer
# a little slower than people do; jitter keeps calls from sounding metronomic.
DEFAULT_GAP_MS = {"agent": 800, "caller": 450}
GAP_JITTER_MS = 150
LEAD_IN_MS = 300

# Line conditions: (FFmpeg audio filter or None, noise level as dBFS or None).
LINES: dict[str, tuple[str | None, float | None]] = {
    "clean": (None, None),
    "phone": ("highpass=f=300,lowpass=f=3400", -48.0),
    "noisy": (None, -32.0),
}


def _configure_espeak() -> None:
    """Point phonemizer at a working espeak-ng (see module docstring)."""
    import misaki.espeak  # noqa: F401  (sets the bundled, possibly broken, paths)
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    library = os.environ.get("ESPEAK_LIBRARY")
    data = os.environ.get("ESPEAK_DATA_PATH")
    brew = Path("/opt/homebrew")
    if library is None and (brew / "lib" / "libespeak-ng.dylib").exists():
        library = str(brew / "lib" / "libespeak-ng.dylib")
        data = data or str(brew / "share" / "espeak-ng-data")
    if library:
        EspeakWrapper.set_library(library)
    if data:
        EspeakWrapper.set_data_path(data)


class Voices:
    """Lazily built Kokoro pipelines, one per language code (voice prefix)."""

    def __init__(self) -> None:
        self._pipelines: dict[str, Any] = {}

    def say(self, text: str, voice: str, speed: float, seed: int) -> np.ndarray:
        import torch
        from kokoro import KPipeline

        torch.manual_seed(seed)  # Kokoro's vocoder samples noise; seed it for repeatability

        lang = voice[0]  # "a" = American English, "b" = British English
        if lang not in self._pipelines:
            self._pipelines[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        chunks = [audio.numpy() for _, _, audio in self._pipelines[lang](text, voice, speed)]
        return np.concatenate(chunks).astype(np.float32)


def render(scenario: dict[str, Any], voices: Voices, seed: int) -> np.ndarray:
    """Lay out every turn on one mono timeline and return the samples."""
    rng = np.random.default_rng(seed)
    roles = {role: scenario[role] for role in ("agent", "caller")}
    pieces: list[tuple[int, np.ndarray]] = []
    cursor = int(LEAD_IN_MS * SAMPLE_RATE / 1000)  # end of the previous turn
    for index, turn in enumerate(scenario["turns"]):
        role = "agent" if "agent" in turn else "caller"
        voice = roles[role]
        speech = voices.say(turn[role], voice["voice"], voice.get("speed", 1.0), seed + index)
        if "gap_ms" in turn:
            gap_ms = float(turn["gap_ms"])  # negative = barge-in overlap
        else:
            gap_ms = DEFAULT_GAP_MS[role] + rng.uniform(-GAP_JITTER_MS, GAP_JITTER_MS)
        start = max(0, cursor + int(gap_ms * SAMPLE_RATE / 1000))
        pieces.append((start, speech))
        cursor = max(cursor, start + len(speech))

    tail = int(scenario.get("end_silence_ms", 600) * SAMPLE_RATE / 1000)
    mix = np.zeros(cursor + tail, dtype=np.float32)
    for start, speech in pieces:
        mix[start : start + len(speech)] += speech

    _, noise_dbfs = LINES[scenario.get("line", "clean")]
    if noise_dbfs is not None:
        mix += (10 ** (noise_dbfs / 20) * rng.standard_normal(len(mix))).astype(np.float32)
    peak = float(np.max(np.abs(mix))) or 1.0
    return mix * (0.89 / peak)  # about -1 dBFS, no clipping on overlaps


def encode(samples: np.ndarray, line: str, out: Path) -> None:
    """Write Opus (mono, 24 kbps) via FFmpeg, applying the line's filter."""
    audio_filter, _ = LINES[line]
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "call.wav"
        sf.write(wav, samples, SAMPLE_RATE)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav)]
        if audio_filter:
            cmd += ["-af", audio_filter]
        cmd += ["-ac", "1", "-c:a", "libopus", "-b:a", "24k", "-map_metadata", "-1"]
        cmd += ["-fflags", "+bitexact", "-flags:a", "+bitexact"]  # fixed Ogg serial
        subprocess.run([*cmd, str(out)], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="Scenario ids to render (default: all).")
    args = parser.parse_args(argv)

    scenario_dir = GOLDEN / "scenarios"
    paths = sorted(scenario_dir.glob("*.yaml"))
    if args.ids:
        paths = [scenario_dir / f"{i}.yaml" for i in args.ids]

    _configure_espeak()
    voices = Voices()
    out_dir = GOLDEN / "calls"
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
        samples = render(scenario, voices, seed=zlib.crc32(path.stem.encode()))
        out = out_dir / f"{path.stem}.opus"
        encode(samples, scenario.get("line", "clean"), out)
        print(f"{out.relative_to(ROOT)}  {len(samples) / SAMPLE_RATE:5.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
