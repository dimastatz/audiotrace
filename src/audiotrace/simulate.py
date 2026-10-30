"""Simulated callers: scripted synthetic calls against an agent (PRD 0010).

A *scenario* says what the caller wants and how to tell whether they got it; a
*persona* says how they talk (style, voice, barge-in, response delay); a *noise
profile* says what their line sounds like. :func:`run_scenario` plays the call
turn by turn against a :class:`Target` (the agent under test), records it as
stereo (caller left, agent right), runs the recording through
:func:`audiotrace.analyze`, and attaches a :class:`~audiotrace.models.SimulationResult`
with the task-completion verdict.

Every moving part is an interface so the loop runs offline in tests:

* :class:`CallerModel` decides what the caller says next (default: Claude,
  :class:`audiotrace.simulate_backends.ClaudeCaller`).
* :class:`Speech` voices it (default: local Kokoro TTS).
* :class:`Listener` transcribes the agent's audio for the caller (default:
  Whisper) when the target doesn't return text itself.
* :class:`Judge` grades a scenario's free-text ``judge`` criterion (default:
  Claude). Only called for scenarios that set one.
* :class:`Target` is the agent. :class:`MockTarget` replays the scenario's
  ``mock`` script; provider adapters (Vapi, Retell, SIP) come later.
"""

from __future__ import annotations

import importlib
import re
import wave
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from audiotrace.models import CallReport, SimulationResult

SAMPLE_RATE = 24_000
LEAD_IN_MS = 300
# How far a barge-in persona starts talking before the agent finishes.
BARGE_IN_OVERLAP_MS = 600


class SimulationError(Exception):
    """A scenario suite is invalid, or a simulated call couldn't be placed."""


# --- Schemas ---------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SuccessCriteria(_Strict):
    """What has to be true at the end of the call for the task to count as done.

    Every set field must hold. ``outcome`` and ``intent`` are compared with the
    report's ``events``; ``must_mention`` phrases must appear in the transcript
    (case-insensitive). ``judge`` is a free-text criterion graded by an LLM.
    """

    outcome: str | None = None
    intent: str | None = None
    must_mention: list[str] = Field(default_factory=list)
    judge: str | None = None


class MockScript(_Strict):
    """The agent's side of the call for ``--target mock``: lines played in order."""

    greeting: str = ""
    replies: list[str] = Field(default_factory=list)
    voice: str = "am_michael"
    # Silence before each agent line; raise it to plant a slow agent.
    delay_ms: int = Field(default=700, ge=0)


class Scenario(_Strict):
    name: str
    goal: str
    persona: str = "neutral"
    noise: str = "clean"
    max_turns: int = Field(default=12, ge=1)
    # Facts or turn hints for the caller (account number, what to ask first, ...).
    hints: list[str] = Field(default_factory=list)
    success: SuccessCriteria = Field(default_factory=SuccessCriteria)
    mock: MockScript | None = None


class Persona(_Strict):
    name: str
    # Prompt text describing how this caller talks.
    style: str
    voice: str = "af_heart"
    speed: float = Field(default=1.0, gt=0)
    barge_in: bool = False
    # Silence before the caller answers the agent.
    response_delay_ms: int = Field(default=500, ge=0)


class NoiseProfile(_Strict):
    name: str
    # "file" mixes the audio at ``file`` (resolved relative to the profile's YAML).
    kind: Literal["none", "white", "pink", "brown", "file"] = "none"
    file: str | None = None
    # Speech-to-noise ratio of the caller's line.
    snr_db: float = 20.0
    # Band-pass (low, high) Hz applied to the caller's line, e.g. a phone line.
    band: tuple[float, float] | None = None


BUILTIN_PERSONAS: dict[str, Persona] = {
    p.name: p
    for p in (
        Persona(
            name="neutral",
            style="Polite and cooperative. Answers questions directly.",
        ),
        Persona(
            name="frustrated",
            style=(
                "Annoyed: this is not your first call about the problem. Short "
                "sentences, complains about the wait and the service, pushes back "
                "when asked to repeat information."
            ),
            voice="am_adam",
            speed=1.1,
            response_delay_ms=300,
        ),
        Persona(
            # Kokoro has no strongly accented English voices; a British voice
            # spoken slower is the closest stand-in until a TTS with accents is
            # plugged in.
            name="heavy_accent",
            style="Non-native English speaker. Simple vocabulary, occasional odd phrasing.",
            voice="bm_lewis",
            speed=0.85,
            response_delay_ms=900,
        ),
        Persona(
            name="interrupter",
            style="Impatient. Starts answering before the agent has finished.",
            voice="af_bella",
            speed=1.15,
            barge_in=True,
            response_delay_ms=0,
        ),
        Persona(
            name="silent",
            style=(
                "Reluctant and terse. Says as little as possible, often a word or "
                "two, and only volunteers information when asked directly."
            ),
            voice="bf_emma",
            response_delay_ms=3000,
        ),
    )
}

BUILTIN_NOISE: dict[str, NoiseProfile] = {
    n.name: n
    for n in (
        NoiseProfile(name="clean"),
        NoiseProfile(name="cafe", kind="pink", snr_db=15.0),
        NoiseProfile(name="street", kind="brown", snr_db=10.0),
        NoiseProfile(name="car", kind="brown", snr_db=12.0, band=(60.0, 6000.0)),
        NoiseProfile(name="bad_line", kind="white", snr_db=20.0, band=(300.0, 3400.0)),
    )
}


@dataclass(frozen=True)
class Suite:
    """A loaded scenario directory: scenarios plus the personas and noise they use."""

    scenarios: list[Scenario]
    personas: dict[str, Persona]
    noise: dict[str, NoiseProfile]

    def needs_judge(self) -> bool:
        return any(s.success.judge for s in self.scenarios)


def _load_yaml(path: Path, model: type[BaseModel]) -> Any:
    import yaml  # in the [simulate] extra

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return model.model_validate(data)
    except (yaml.YAMLError, ValidationError) as exc:
        raise SimulationError(f"{path}: {exc}") from exc


def load_suite(directory: str | Path) -> Suite:
    """Load ``*.yaml`` scenarios, plus ``personas/*.yaml`` and ``noise/*.yaml``.

    User personas and noise profiles override built-ins of the same name. Every
    scenario's persona and noise must resolve, or :class:`SimulationError` is
    raised naming the file and the choices available.
    """
    root = Path(directory)
    if not root.is_dir():
        raise SimulationError(f"Not a directory: {root}")

    personas = dict(BUILTIN_PERSONAS)
    for path in sorted((root / "personas").glob("*.yaml")):
        persona = _load_yaml(path, Persona)
        personas[persona.name] = persona

    noise = dict(BUILTIN_NOISE)
    for path in sorted((root / "noise").glob("*.yaml")):
        profile = _load_yaml(path, NoiseProfile)
        if profile.kind == "file":
            if not profile.file:
                raise SimulationError(f"{path}: kind 'file' needs a 'file' path")
            profile = profile.model_copy(update={"file": str(path.parent / profile.file)})
        noise[profile.name] = profile

    scenarios: list[Scenario] = []
    for path in sorted(root.glob("*.yaml")):
        scenario = _load_yaml(path, Scenario)
        if scenario.persona not in personas:
            raise SimulationError(
                f"{path}: unknown persona {scenario.persona!r} "
                f"(available: {', '.join(sorted(personas))})"
            )
        if scenario.noise not in noise:
            raise SimulationError(
                f"{path}: unknown noise {scenario.noise!r} (available: {', '.join(sorted(noise))})"
            )
        scenarios.append(scenario)

    names = [s.name for s in scenarios]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise SimulationError(f"Duplicate scenario names: {', '.join(dupes)}")
    if not scenarios:
        raise SimulationError(f"No scenarios (*.yaml) in {root}")
    return Suite(scenarios=scenarios, personas=personas, noise=noise)


# --- Interfaces --------------------------------------------------------------


@dataclass(frozen=True)
class CallerTurn:
    """What the caller says next; ``hang_up`` ends the call after it's spoken."""

    text: str
    hang_up: bool = False


@dataclass(frozen=True)
class AgentReply:
    """One agent turn. ``text`` is the agent's words when the target knows them
    (skips transcription); ``delay_ms`` is the silence before the agent spoke."""

    audio: np.ndarray
    text: str | None = None
    delay_ms: int = 700
    hung_up: bool = False


# (speaker, text) pairs, "agent" or "caller", in call order.
History = list[tuple[str, str]]


class CallerModel(Protocol):
    def next_turn(self, scenario: Scenario, persona: Persona, history: History) -> CallerTurn: ...


class Speech(Protocol):
    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray: ...


class Listener(Protocol):
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str: ...


class Judge(Protocol):
    def grade(self, criterion: str, transcript: str) -> tuple[bool, str]: ...


class Target(Protocol):
    """The agent under test. ``caller_text`` is a hint for mocks; real adapters
    should only use the audio."""

    def start(self, scenario: Scenario) -> AgentReply: ...

    def respond(self, caller_audio: np.ndarray, caller_text: str) -> AgentReply: ...

    def close(self) -> None: ...


class MockTarget:
    """Plays a scenario's ``mock`` script: the greeting, then one reply per caller
    turn, then hangs up when the replies run out."""

    def __init__(self, script: MockScript, speech: Speech) -> None:
        self._script = script
        self._speech = speech
        self._replies = list(script.replies)

    def _say(self, text: str) -> AgentReply:
        audio = self._speech.synthesize(text, self._script.voice, 1.0) if text else _silence()
        return AgentReply(audio=audio, text=text, delay_ms=self._script.delay_ms)

    def start(self, scenario: Scenario) -> AgentReply:
        return self._say(self._script.greeting)

    def respond(self, caller_audio: np.ndarray, caller_text: str) -> AgentReply:
        if not self._replies:
            return AgentReply(audio=_silence(), text="", hung_up=True)
        return self._say(self._replies.pop(0))

    def close(self) -> None:
        pass


TargetFactory = Callable[[Scenario], Target]


def mock_target_factory(speech: Speech) -> TargetFactory:
    """A factory for ``--target mock``: each scenario must carry a ``mock`` script."""

    def factory(scenario: Scenario) -> Target:
        if scenario.mock is None:
            raise SimulationError(f"Scenario {scenario.name!r} has no 'mock' script")
        return MockTarget(scenario.mock, speech)

    return factory


def load_target_factory(spec: str) -> TargetFactory:
    """Resolve a ``module:attribute`` spec to a target factory (custom agents)."""
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise SimulationError(f"Target must be 'mock' or 'module:factory', got {spec!r}")
    try:
        factory = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise SimulationError(f"Cannot load target {spec!r}: {exc}") from exc
    if not callable(factory):
        raise SimulationError(f"Target {spec!r} is not callable")
    return factory  # type: ignore[no-any-return]


# --- Audio -------------------------------------------------------------------


def _silence() -> np.ndarray:
    return np.zeros(0, dtype=np.float32)


def _samples(ms: float) -> int:
    return int(ms * SAMPLE_RATE / 1000)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def _band_pass(x: np.ndarray, low: float, high: float) -> np.ndarray:
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(x.size, d=1 / SAMPLE_RATE)
    spectrum[(freqs < low) | (freqs > high)] = 0
    return np.fft.irfft(spectrum, n=x.size).astype(np.float32)


def make_noise(profile: NoiseProfile, length: int, rng: np.random.Generator) -> np.ndarray:
    """``length`` samples of the profile's noise, at unit RMS (zeros for "none")."""
    if profile.kind == "none" or length == 0:
        return np.zeros(length, dtype=np.float32)
    if profile.kind == "file":
        import librosa

        loaded, _ = librosa.load(str(profile.file), sr=SAMPLE_RATE, mono=True)
        if not loaded.size:
            raise SimulationError(f"Noise file is empty: {profile.file}")
        noise = np.resize(loaded.astype(np.float64), length)  # loops short files
    else:
        noise = rng.standard_normal(length)
        if profile.kind == "pink":
            spectrum = np.fft.rfft(noise)
            freqs = np.fft.rfftfreq(length)
            freqs[0] = freqs[1] if length > 1 else 1.0
            noise = np.fft.irfft(spectrum / np.sqrt(freqs), n=length)
        elif profile.kind == "brown":
            noise = np.cumsum(noise)
            noise -= np.linspace(noise[0], noise[-1], length)  # remove the drift
    noise = noise - noise.mean()
    level = _rms(noise)
    return np.asarray(noise / level if level else noise, dtype=np.float32)


def apply_line(caller: np.ndarray, profile: NoiseProfile, rng: np.random.Generator) -> np.ndarray:
    """Mix the profile's noise into the caller channel at its SNR, then band-limit."""
    out: np.ndarray = caller.astype(np.float32)
    speech = caller[np.abs(caller) > 1e-4]
    if profile.kind != "none":
        level = _rms(speech) or 0.05
        out = out + make_noise(profile, caller.size, rng) * level / 10 ** (profile.snr_db / 20)
    if profile.band is not None and out.size:
        out = _band_pass(out, *profile.band)
    return out


def write_stereo_wav(path: Path, left: np.ndarray, right: np.ndarray) -> None:
    """Write 16-bit stereo PCM at SAMPLE_RATE, peak-normalized to avoid clipping."""
    peak = max(float(np.max(np.abs(left), initial=0)), float(np.max(np.abs(right), initial=0)))
    scale = 0.89 / peak if peak > 0.89 else 1.0
    frames = np.stack([left, right], axis=1) * scale
    pcm = (np.clip(frames, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())


# --- Verdict -----------------------------------------------------------------


def evaluate(
    success: SuccessCriteria, report: CallReport, judge: Judge | None = None
) -> tuple[bool, str]:
    """Check the report against every set criterion; returns (passed, reason)."""
    failures: list[str] = []
    if success.outcome is not None and report.events.outcome != success.outcome:
        failures.append(f"outcome {report.events.outcome!r}, expected {success.outcome!r}")
    if success.intent is not None and report.events.intent_detected != success.intent:
        failures.append(f"intent {report.events.intent_detected!r}, expected {success.intent!r}")
    text = report.transcript.full_text.lower()
    missing = [p for p in success.must_mention if p.lower() not in text]
    if missing:
        failures.append(f"never mentioned: {', '.join(missing)}")
    if success.judge:
        if judge is None:
            raise SimulationError("A 'judge' criterion needs a Judge")
        passed, why = judge.grade(success.judge, _dialogue(report))
        if not passed:
            failures.append(f"judge: {why}")
    if failures:
        return False, "; ".join(failures)
    return True, "all success criteria met"


def _dialogue(report: CallReport) -> str:
    turns = report.transcript.turns
    if not turns:
        return report.transcript.full_text
    return "\n".join(f"{t.speaker}: {t.text}" for t in turns)


# --- The call loop -------------------------------------------------------------


Analyzer = Callable[[Path, list[str]], CallReport]


def default_analyzer(path: Path, labels: list[str]) -> CallReport:
    """Analyze a two-party recording, labelling speakers in order of appearance."""
    from audiotrace.core import analyze

    return analyze(path, num_speakers=2, speaker_labels=labels)


@dataclass
class Simulator:
    """Runs scenarios: wires the caller, voice, listener, judge, and analyzer."""

    caller: CallerModel
    speech: Speech
    listener: Listener | None = None
    judge: Judge | None = None
    analyzer: Analyzer = default_analyzer

    def run(
        self,
        scenario: Scenario,
        target: Target,
        out_dir: str | Path,
        personas: dict[str, Persona] | None = None,
        noise: dict[str, NoiseProfile] | None = None,
    ) -> CallReport:
        """Play one scenario against ``target``; returns the analyzed report with
        its ``simulation`` verdict. The recording lands in ``out_dir/<name>.wav``."""
        persona = (personas or BUILTIN_PERSONAS)[scenario.persona]
        profile = (noise or BUILTIN_NOISE)[scenario.noise]
        rng = np.random.default_rng(zlib.crc32(scenario.name.encode()))

        try:
            pieces, history = self._converse(scenario, persona, target)
        finally:
            target.close()

        if not any(role == "caller" for role, _, _ in pieces):
            raise SimulationError(f"Scenario {scenario.name!r}: the caller never spoke")
        length = max(start + audio.size for _, start, audio in pieces) + _samples(LEAD_IN_MS)
        channels = {"caller": np.zeros(length, np.float32), "agent": np.zeros(length, np.float32)}
        for role, start, audio in pieces:
            channels[role][start : start + audio.size] += audio
        caller = apply_line(channels["caller"], profile, rng)

        path = Path(out_dir) / f"{safe_name(scenario.name)}.wav"
        write_stereo_wav(path, caller, channels["agent"])
        labels = [role for role in ("agent", "caller") if role == pieces[0][0]]
        labels += [role for role in ("agent", "caller") if role not in labels]
        report = self.analyzer(path, labels)

        passed, reason = evaluate(scenario.success, report, self.judge)
        report.simulation = SimulationResult(
            scenario=scenario.name,
            persona=persona.name,
            noise=profile.name,
            task_completed=passed,
            reason=reason,
            turns=sum(1 for role, _ in history if role == "caller"),
        )
        return report

    def _converse(
        self, scenario: Scenario, persona: Persona, target: Target
    ) -> tuple[list[tuple[str, int, np.ndarray]], History]:
        """Alternate agent and caller turns; returns placed audio and the dialogue."""
        pieces: list[tuple[str, int, np.ndarray]] = []
        history: History = []
        cursor = _samples(LEAD_IN_MS)  # end of the latest audio
        reply = target.start(scenario)
        caller_turns = 0
        while True:
            if reply.audio.size:
                start = cursor + _samples(reply.delay_ms)
                pieces.append(("agent", start, reply.audio))
                agent_span = (start, start + reply.audio.size)
                cursor = max(cursor, agent_span[1])
                history.append(("agent", self._hear(reply)))
            else:
                agent_span = None
            if reply.hung_up or caller_turns >= scenario.max_turns:
                break

            turn = self.caller.next_turn(scenario, persona, history)
            if turn.text:
                audio = self.speech.synthesize(turn.text, persona.voice, persona.speed)
                if persona.barge_in and agent_span is not None:
                    start = max(agent_span[0], agent_span[1] - _samples(BARGE_IN_OVERLAP_MS))
                else:
                    start = cursor + _samples(persona.response_delay_ms)
                pieces.append(("caller", start, audio))
                cursor = max(cursor, start + audio.size)
                history.append(("caller", turn.text))
                caller_turns += 1
            if turn.hang_up:
                break
            reply = target.respond(pieces[-1][2] if turn.text else _silence(), turn.text)
        return pieces, history

    def _hear(self, reply: AgentReply) -> str:
        if reply.text is not None:
            return reply.text
        if self.listener is None:
            raise SimulationError("Target returned audio without text and no Listener is set")
        return self.listener.transcribe(reply.audio, SAMPLE_RATE)


def run_suite(
    suite: Suite, simulator: Simulator, factory: TargetFactory, out_dir: str | Path
) -> dict[str, CallReport]:
    """Run every scenario in ``suite``; reports are keyed by scenario name so a
    regular baseline file (``audiotrace check``) can gate them."""
    return {
        scenario.name: simulator.run(
            scenario, factory(scenario), out_dir, suite.personas, suite.noise
        )
        for scenario in suite.scenarios
    }


def failed_scenarios(reports: dict[str, CallReport]) -> list[str]:
    """Names of scenarios whose task-completion verdict failed."""
    return [
        name
        for name, report in reports.items()
        if report.simulation is None or not report.simulation.task_completed
    ]


def format_verdicts(reports: dict[str, CallReport]) -> str:
    """A headline plus one line per scenario, for CI logs."""
    failed = failed_scenarios(reports)
    if failed:
        lines = [f"FAIL — {len(failed)} of {len(reports)} scenario(s) did not complete the task"]
    else:
        lines = [f"PASS — {len(reports)} scenario(s) completed the task"]
    for name, report in reports.items():
        sim = report.simulation
        mark = "ok  " if name not in failed else "FAIL"
        detail = f"{sim.persona}/{sim.noise}, {sim.turns} turn(s): {sim.reason}" if sim else ""
        lines.append(f"  {mark} {name} ({detail})" if sim else f"  {mark} {name}")
    return "\n".join(lines)


def safe_name(name: str) -> str:
    """A file-system-safe stem for a scenario name."""
    return re.sub(r"[^\w.-]+", "_", name).strip("_") or "scenario"


# --- Scaffold ----------------------------------------------------------------

INIT_FILES: dict[str, str] = {
    "reschedule-appointment.yaml": """\
# A simulated caller scenario (PRD 0010). Run with:
#   audiotrace simulate scenarios/ --target mock
name: reschedule-appointment
goal: Move my Tuesday 3pm dentist appointment to Thursday morning.
# persona: neutral | frustrated | heavy_accent | interrupter | silent | personas/*.yaml
persona: neutral
# noise: clean | cafe | street | car | bad_line | noise/*.yaml
noise: cafe
max_turns: 8
hints:
  - Your name is Sam Rivera and your date of birth is March 4th 1990.
success:
  outcome: completed
  must_mention: ["Thursday"]
  # judge: The agent confirmed a specific new time on Thursday morning.

# The agent's side for `--target mock`. Point --target at your own agent
# (module:factory) to test it for real.
mock:
  greeting: >-
    Thanks for calling Bright Smile Dental, this call may be recorded.
    How can I help?
  replies:
    - Sure, I can help with that. Can I have your name and date of birth?
    - Thanks Sam. I have Thursday at 9am or 10:30am. Which works better?
    - Done, you're booked for Thursday at 10:30am. Anything else?
    - You're welcome, have a great day. Goodbye.
""",
    "cancel-subscription.yaml": """\
name: cancel-subscription
goal: Cancel my streaming subscription today without being talked into a discount.
persona: frustrated
noise: bad_line
max_turns: 8
success:
  outcome: completed
  must_mention: ["cancel"]
mock:
  greeting: >-
    Hi, you've reached StreamCo support. This call is recorded for quality.
    What can I do for you?
  replies:
    - I'm sorry to hear that. Before I cancel, can I offer you three months at half price?
    - Understood. Your subscription is cancelled as of today, and you won't be charged again.
    - Thanks for being with us. Goodbye.
""",
    "personas/hurried-parent.yaml": """\
# A custom persona. Scenarios refer to it by name.
name: hurried-parent
style: Calling while looking after a toddler. Distracted, asks the agent to repeat things.
voice: af_sarah
speed: 1.1
barge_in: false
response_delay_ms: 1200
""",
}


def init_scenarios(directory: str | Path) -> list[Path]:
    """Write example scenarios and a custom persona; never overwrites files."""
    root = Path(directory)
    written: list[Path] = []
    for rel, content in INIT_FILES.items():
        path = root / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
