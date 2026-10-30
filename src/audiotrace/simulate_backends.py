"""Default backends for simulated callers (PRD 0010).

* :class:`ClaudeCaller` — the caller's brain, via the Anthropic API
  (``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile).
* :class:`ClaudeJudge` — grades a scenario's free-text ``judge`` criterion.
* :class:`KokoroSpeech` — local Kokoro TTS (Python 3.10–3.12; on macOS needs
  ``brew install espeak-ng``, see ``scripts/gen_golden.py``).
* :class:`WhisperListener` — transcribes agent audio that came without text.

All heavy imports are deferred, and all live in ``pip install audiotrace[simulate]``.
Credentials come from the environment and are never written into reports.
"""

from __future__ import annotations

import importlib
import zlib
from typing import Any

import numpy as np

from audiotrace.simulate import (
    SAMPLE_RATE,
    CallerTurn,
    History,
    Persona,
    Scenario,
    SimulationError,
)

DEFAULT_MODEL = "claude-opus-5-5"
# Server-side fallback: if the model declines a turn, the API retries it on a
# fallback model inside the same call instead of stopping the simulation.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# The caller appends this to its last line to hang up.
END_MARK = "[END]"

_CALLER_SYSTEM = """\
You are role-playing a person phoning a company's voice agent. This is a QA test of \
that agent; stay in character and never mention that you are an AI or a test.

Your goal: {goal}
How you talk: {style}
{hints}
Each of your replies is spoken aloud by text-to-speech, so write only the words you \
say: no stage directions, no markdown, one to three short sentences. Messages from \
the agent arrive as transcripts and may contain recognition errors.

When your goal is met, or you give up, say a natural goodbye and end that reply with \
{end}. Don't end the call before the agent has had a chance to help."""

_JUDGE_SYSTEM = """\
You grade transcripts of phone calls between a voice agent and a caller. Decide \
whether the transcript satisfies the criterion. Speaker labels and words may contain \
speech-recognition errors; judge the substance.

Answer with PASS or FAIL on the first line, then one sentence explaining why."""


def _client(client: Any) -> Any:
    if client is not None:
        return client
    import anthropic

    return anthropic.Anthropic()


def _ask(client: Any, model: str, system: str, messages: list[dict[str, str]], **extra: Any) -> str:
    """One Messages call with refusal fallback; returns the text of the reply."""
    response = client.beta.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=messages,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        **extra,
    )
    if response.stop_reason == "refusal":
        raise SimulationError(f"{model} declined the request")
    return "".join(b.text for b in response.content if b.type == "text").strip()


class ClaudeCaller:
    """Plays the caller with Claude: persona style + goal in, next line out."""

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "low", client: Any = None):
        self.model = model
        self.effort = effort
        self._client_obj = client

    def next_turn(self, scenario: Scenario, persona: Persona, history: History) -> CallerTurn:
        self._client_obj = _client(self._client_obj)
        hints = "".join(f"- {h}\n" for h in scenario.hints)
        system = _CALLER_SYSTEM.format(
            goal=scenario.goal,
            style=persona.style,
            hints=f"Facts you know:\n{hints}" if hints else "",
            end=END_MARK,
        )
        text = _ask(
            self._client_obj,
            self.model,
            system,
            _as_messages(history),
            output_config={"effort": self.effort},
        )
        hang_up = END_MARK in text
        return CallerTurn(text=text.replace(END_MARK, "").strip(), hang_up=hang_up)


def _as_messages(history: History) -> list[dict[str, str]]:
    """The agent speaks as "user", the caller (Claude) as "assistant". The list
    must start and end on a user turn, so silence is made explicit."""
    messages = [
        {"role": "user" if speaker == "agent" else "assistant", "content": text or "(silence)"}
        for speaker, text in history
    ]
    if not messages or messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": "(The call connects. Silence.)"})
    if messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": "(silence)"})
    return messages


class ClaudeJudge:
    """Grades a free-text success criterion against the call transcript."""

    def __init__(self, model: str = DEFAULT_MODEL, client: Any = None):
        self.model = model
        self._client_obj = client

    def grade(self, criterion: str, transcript: str) -> tuple[bool, str]:
        self._client_obj = _client(self._client_obj)
        prompt = f"Criterion: {criterion}\n\nTranscript:\n{transcript}"
        text = _ask(
            self._client_obj, self.model, _JUDGE_SYSTEM, [{"role": "user", "content": prompt}]
        )
        verdict, _, reason = text.partition("\n")
        verdict = verdict.strip().upper()
        if verdict.startswith("PASS"):
            return True, reason.strip()
        if verdict.startswith("FAIL"):
            return False, reason.strip() or "criterion not met"
        raise SimulationError(f"Judge gave no PASS/FAIL verdict: {text[:200]!r}")


class KokoroSpeech:
    """Local Kokoro TTS. Voices are Kokoro ids (``af_heart``, ``bm_lewis``, ...);
    the first letter picks the language pipeline. Seeded per line, so the same
    text and voice always render the same audio."""

    def __init__(self, repo_id: str = "hexgrad/Kokoro-82M") -> None:
        self.repo_id = repo_id
        self._pipelines: dict[str, Any] = {}

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        torch = importlib.import_module("torch")
        kokoro = importlib.import_module("kokoro")

        torch.manual_seed(zlib.crc32(f"{voice}:{text}".encode()))
        lang = voice[0]
        if lang not in self._pipelines:
            self._pipelines[lang] = kokoro.KPipeline(lang_code=lang, repo_id=self.repo_id)
        chunks = [audio.numpy() for _, _, audio in self._pipelines[lang](text, voice, speed)]
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)


class WhisperListener:
    """Transcribes agent audio with the same Whisper model ``analyze()`` uses."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name

    def transcribe(self, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        import librosa

        from audiotrace.transcripts import WHISPER_MODEL, get_whisper_model

        if not audio.size:
            return ""
        model = get_whisper_model(self.model_name or WHISPER_MODEL)
        clip = librosa.resample(audio.astype(np.float32), orig_sr=sample_rate, target_sr=16_000)
        result = model.transcribe(clip, fp16=False)
        return str(result["text"]).strip()
