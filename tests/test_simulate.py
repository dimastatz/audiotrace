import wave
from pathlib import Path

import numpy as np
import pytest

from audiotrace import simulate as sim
from audiotrace.models import CallReport, Events, SimulationResult, Transcript, Turn
from audiotrace.report import render_html, render_json

pytest.importorskip("yaml")

SR = sim.SAMPLE_RATE


# --- Fakes -------------------------------------------------------------------


class FakeSpeech:
    """Renders a 0.1 s tone per word, so audio length tracks the text."""

    def __init__(self):
        self.calls = []

    def synthesize(self, text, voice, speed):
        self.calls.append((text, voice, speed))
        n = int(0.1 * SR * len(text.split()))
        return (0.3 * np.cos(np.arange(n) * 0.05)).astype(np.float32)


class ScriptedCaller:
    def __init__(self, lines):
        self.lines = list(lines)
        self.seen = []

    def next_turn(self, scenario, persona, history):
        self.seen.append(list(history))
        text, hang_up = self.lines.pop(0)
        return sim.CallerTurn(text=text, hang_up=hang_up)


class FakeJudge:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []

    def grade(self, criterion, transcript):
        self.calls.append((criterion, transcript))
        return self.verdict


class FakeListener:
    def transcribe(self, audio, sample_rate):
        return f"heard {audio.size} samples"


def fake_analyzer(text="we can do thursday", outcome="completed", intent="billing"):
    seen = {}

    def analyze(path, labels):
        seen["path"] = path
        seen["labels"] = labels
        return CallReport(
            transcript=Transcript(
                full_text=text,
                turns=[Turn(speaker=labels[0], text=text, start_ms=0, end_ms=1000)],
            ),
            events=Events(outcome=outcome, intent_detected=intent),
        )

    analyze.seen = seen
    return analyze


def _scenario(**overrides):
    data = {
        "name": "reschedule",
        "goal": "Move the appointment",
        "success": {"outcome": "completed", "must_mention": ["Thursday"]},
        "mock": {"greeting": "hello this call is recorded", "replies": ["sure", "done"]},
    }
    data.update(overrides)
    return sim.Scenario.model_validate(data)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- Suite loading -------------------------------------------------------------


def test_load_suite_reads_scenarios_personas_and_noise(tmp_path):
    _write(tmp_path / "a.yaml", "name: a\ngoal: g\npersona: hurried\nnoise: hum\n")
    _write(tmp_path / "b.yaml", "name: b\ngoal: g\n")
    _write(tmp_path / "personas" / "p.yaml", "name: hurried\nstyle: rushed\n")
    _write(tmp_path / "noise" / "n.yaml", "name: hum\nkind: file\nfile: hum.wav\n")

    suite = sim.load_suite(tmp_path)

    assert [s.name for s in suite.scenarios] == ["a", "b"]
    assert suite.personas["hurried"].style == "rushed"
    assert "neutral" in suite.personas  # built-ins kept
    assert suite.noise["hum"].file == str(tmp_path / "noise" / "hum.wav")
    assert not suite.needs_judge()


def test_suite_needs_judge_when_a_scenario_sets_one(tmp_path):
    _write(tmp_path / "a.yaml", "name: a\ngoal: g\nsuccess:\n  judge: agent was polite\n")
    assert sim.load_suite(tmp_path).needs_judge()


@pytest.mark.parametrize(
    "files, message",
    [
        ({"a.yaml": "name: a\ngoal: g\npersona: nobody\n"}, "unknown persona 'nobody'"),
        ({"a.yaml": "name: a\ngoal: g\nnoise: jet\n"}, "unknown noise 'jet'"),
        ({"a.yaml": "name: a\n"}, "goal"),
        ({"a.yaml": "name: a\ngoal: g\ncolour: red\n"}, "colour"),
        ({"a.yaml": "name: a\ngoal: g\nmax_turns: 0\n"}, "max_turns"),
        ({"a.yaml": "name: [unclosed\n"}, "a.yaml"),
        ({"a.yaml": "name: x\ngoal: g\n", "b.yaml": "name: x\ngoal: g\n"}, "Duplicate"),
        ({"notes.txt": "nothing here"}, "No scenarios"),
        ({"a.yaml": "name: a\ngoal: g\n", "noise/n.yaml": "name: n\nkind: file\n"}, "needs a"),
    ],
)
def test_load_suite_rejects_bad_input(tmp_path, files, message):
    for rel, text in files.items():
        _write(tmp_path / rel, text)
    with pytest.raises(sim.SimulationError, match=message):
        sim.load_suite(tmp_path)


def test_load_suite_needs_a_directory(tmp_path):
    with pytest.raises(sim.SimulationError, match="Not a directory"):
        sim.load_suite(tmp_path / "missing")


def test_init_scaffold_loads_and_never_overwrites(tmp_path):
    written = sim.init_scenarios(tmp_path)
    assert len(written) == len(sim.INIT_FILES)

    suite = sim.load_suite(tmp_path)
    assert {s.name for s in suite.scenarios} == {"reschedule-appointment", "cancel-subscription"}
    assert "hurried-parent" in suite.personas
    assert all(s.mock is not None for s in suite.scenarios)

    (tmp_path / "cancel-subscription.yaml").write_text("edited", encoding="utf-8")
    assert sim.init_scenarios(tmp_path) == []
    assert (tmp_path / "cancel-subscription.yaml").read_text(encoding="utf-8") == "edited"


def test_builtin_personas_and_noise_cover_the_prd_defaults():
    assert set(sim.BUILTIN_PERSONAS) == {
        "neutral",
        "frustrated",
        "heavy_accent",
        "interrupter",
        "silent",
    }
    assert set(sim.BUILTIN_NOISE) == {"clean", "cafe", "street", "car", "bad_line"}
    assert sim.BUILTIN_PERSONAS["interrupter"].barge_in


# --- Targets -------------------------------------------------------------------


def test_mock_target_plays_greeting_then_replies_then_hangs_up():
    speech = FakeSpeech()
    target = sim.MockTarget(sim.MockScript(greeting="hi", replies=["one"], delay_ms=50), speech)

    first = target.start(_scenario())
    assert (first.text, first.delay_ms, first.hung_up) == ("hi", 50, False)
    assert first.audio.size > 0
    assert target.respond(np.zeros(1), "x").text == "one"
    last = target.respond(np.zeros(1), "y")
    assert last.hung_up and last.audio.size == 0
    target.close()
    assert [c[0] for c in speech.calls] == ["hi", "one"]


def test_mock_target_with_no_greeting_is_silent():
    reply = sim.MockTarget(sim.MockScript(), FakeSpeech()).start(_scenario())
    assert reply.audio.size == 0 and reply.text == ""


def test_mock_target_factory_needs_a_mock_script():
    factory = sim.mock_target_factory(FakeSpeech())
    assert isinstance(factory(_scenario()), sim.MockTarget)
    with pytest.raises(sim.SimulationError, match="no 'mock' script"):
        factory(_scenario(mock=None))


def test_load_target_factory_resolves_module_attribute():
    factory = sim.load_target_factory("audiotrace.simulate:mock_target_factory")
    assert factory is sim.mock_target_factory


@pytest.mark.parametrize(
    "spec, message",
    [
        ("vapi", "module:factory"),
        ("no_such_module_xyz:make", "Cannot load"),
        ("audiotrace.simulate:missing", "Cannot load"),
        ("audiotrace.simulate:SAMPLE_RATE", "not callable"),
    ],
)
def test_load_target_factory_errors(spec, message):
    with pytest.raises(sim.SimulationError, match=message):
        sim.load_target_factory(spec)


# --- Audio ---------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["white", "pink", "brown"])
def test_make_noise_is_unit_rms_and_seeded(kind):
    profile = sim.NoiseProfile(name="n", kind=kind)
    a = sim.make_noise(profile, 4000, np.random.default_rng(1))
    b = sim.make_noise(profile, 4000, np.random.default_rng(1))
    assert a.dtype == np.float32 and a.size == 4000
    assert np.sqrt(np.mean(a**2)) == pytest.approx(1.0, rel=1e-3)
    assert np.array_equal(a, b)


def test_make_noise_none_and_empty_are_zero():
    rng = np.random.default_rng(0)
    assert not sim.make_noise(sim.NoiseProfile(name="c"), 10, rng).any()
    assert sim.make_noise(sim.NoiseProfile(name="w", kind="white"), 0, rng).size == 0


def _write_wav(path: Path, samples: np.ndarray) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes((samples * 32767).astype("<i2").tobytes())
    return path


def test_make_noise_loops_a_noise_file(tmp_path):
    path = _write_wav(tmp_path / "hum.wav", 0.5 * np.sin(np.arange(1000) * 0.1))
    profile = sim.NoiseProfile(name="hum", kind="file", file=str(path))
    noise = sim.make_noise(profile, 3000, np.random.default_rng(0))
    assert noise.size == 3000
    assert np.allclose(noise[:1000], noise[1000:2000])


def test_make_noise_rejects_an_empty_file(tmp_path):
    path = _write_wav(tmp_path / "empty.wav", np.zeros(0))
    with pytest.raises(sim.SimulationError, match="empty"):
        sim.make_noise(
            sim.NoiseProfile(name="e", kind="file", file=str(path)), 10, np.random.default_rng(0)
        )


def test_apply_line_mixes_at_the_requested_snr():
    speech = (0.2 * np.sin(np.arange(SR) * 0.07)).astype(np.float32)
    profile = sim.NoiseProfile(name="n", kind="white", snr_db=20.0)
    noisy = sim.apply_line(speech, profile, np.random.default_rng(0))
    added = noisy - speech
    snr = 20 * np.log10(np.sqrt(np.mean(speech**2)) / np.sqrt(np.mean(added**2)))
    assert snr == pytest.approx(20.0, abs=0.5)


def test_apply_line_clean_is_unchanged_and_band_limits():
    rng = np.random.default_rng(0)
    speech = np.sin(2 * np.pi * 100 * np.arange(SR) / SR).astype(np.float32)  # 100 Hz
    assert np.array_equal(sim.apply_line(speech, sim.BUILTIN_NOISE["clean"], rng), speech)
    phone = sim.NoiseProfile(name="p", band=(300.0, 3400.0))
    assert np.abs(sim.apply_line(speech, phone, rng)).max() < 1e-3  # 100 Hz removed


def test_write_stereo_wav_normalizes_loud_audio(tmp_path):
    path = tmp_path / "out" / "call.wav"
    sim.write_stereo_wav(path, np.full(100, 2.0, np.float32), np.zeros(100, np.float32))
    with wave.open(str(path)) as wav:
        assert (wav.getnchannels(), wav.getframerate(), wav.getnframes()) == (2, SR, 100)
        frames = np.frombuffer(wav.readframes(100), dtype="<i2").reshape(-1, 2)
    assert frames[:, 0].max() == int(0.89 * 32767)
    assert not frames[:, 1].any()


# --- Verdict ---------------------------------------------------------------------


def _report(text="We moved you to Thursday", outcome="completed", intent="billing"):
    return CallReport(
        transcript=Transcript(
            full_text=text, turns=[Turn(speaker="agent", text=text, start_ms=0, end_ms=1)]
        ),
        events=Events(outcome=outcome, intent_detected=intent),
    )


def test_evaluate_passes_when_every_criterion_holds():
    success = sim.SuccessCriteria(outcome="completed", intent="billing", must_mention=["thursday"])
    assert sim.evaluate(success, _report()) == (True, "all success criteria met")


def test_evaluate_lists_every_failure():
    success = sim.SuccessCriteria(
        outcome="completed", intent="sales", must_mention=["Thursday", "refund", "credit"]
    )
    passed, reason = sim.evaluate(success, _report(outcome="dropped"))
    assert not passed
    assert "outcome 'dropped', expected 'completed'" in reason
    assert "intent 'billing', expected 'sales'" in reason
    assert "never mentioned: refund, credit" in reason


def test_evaluate_with_no_criteria_passes():
    assert sim.evaluate(sim.SuccessCriteria(), _report())[0]


def test_evaluate_calls_the_judge_with_the_dialogue():
    judge = FakeJudge((False, "no time was confirmed"))
    success = sim.SuccessCriteria(judge="A time was confirmed")
    passed, reason = sim.evaluate(success, _report(), judge)
    assert not passed and reason == "judge: no time was confirmed"
    assert judge.calls == [("A time was confirmed", "agent: We moved you to Thursday")]
    assert sim.evaluate(success, _report(), FakeJudge((True, "fine")))[0]


def test_evaluate_judge_uses_full_text_when_there_are_no_turns():
    judge = FakeJudge((True, ""))
    sim.evaluate(
        sim.SuccessCriteria(judge="x"), CallReport(transcript=Transcript(full_text="t")), judge
    )
    assert judge.calls[0][1] == "t"


def test_evaluate_judge_criterion_without_a_judge_errors():
    with pytest.raises(sim.SimulationError, match="needs a Judge"):
        sim.evaluate(sim.SuccessCriteria(judge="x"), _report())


# --- The call loop -----------------------------------------------------------------


def _simulator(lines, analyzer=None, listener=None, judge=None):
    return sim.Simulator(
        caller=ScriptedCaller(lines),
        speech=FakeSpeech(),
        listener=listener,
        judge=judge,
        analyzer=analyzer or fake_analyzer(),
    )


def test_run_plays_the_call_and_attaches_a_passing_verdict(tmp_path):
    analyzer = fake_analyzer(text="we can do Thursday")
    simulator = _simulator(
        [("I need to move it", False), ("Thursday please", False), ("thanks bye", True)],
        analyzer,
    )
    scenario = _scenario(noise="cafe")
    report = simulator.run(scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path)

    assert report.simulation == SimulationResult(
        scenario="reschedule",
        persona="neutral",
        noise="cafe",
        task_completed=True,
        reason="all success criteria met",
        turns=3,
    )
    assert analyzer.seen["path"] == tmp_path / "reschedule.wav"
    assert analyzer.seen["labels"] == ["agent", "caller"]
    with wave.open(str(tmp_path / "reschedule.wav")) as wav:
        assert wav.getnchannels() == 2
    # The caller saw the agent's words, in order.
    assert simulator.caller.seen[1] == [
        ("agent", "hello this call is recorded"),
        ("caller", "I need to move it"),
        ("agent", "sure"),
    ]


def test_run_records_a_failed_verdict(tmp_path):
    simulator = _simulator([("bye", True)], fake_analyzer(text="sorry", outcome="dropped"))
    scenario = _scenario()
    report = simulator.run(scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path)
    assert not report.simulation.task_completed
    assert "never mentioned: Thursday" in report.simulation.reason


def test_run_stops_when_the_target_hangs_up(tmp_path):
    simulator = _simulator([("one", False), ("two", False), ("three", False)])
    scenario = _scenario(mock={"greeting": "hi", "replies": ["ok"]})
    report = simulator.run(scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path)
    assert report.simulation.turns == 2


def test_run_stops_at_max_turns(tmp_path):
    simulator = _simulator([("a", False), ("b", False)])
    scenario = _scenario(max_turns=1)
    report = simulator.run(scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path)
    assert report.simulation.turns == 1


def test_run_caller_first_when_agent_is_silent(tmp_path):
    analyzer = fake_analyzer()
    simulator = _simulator([("hello?", False), ("bye", True)], analyzer)
    scenario = _scenario(mock={"replies": ["hi there"]})
    simulator.run(scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path)
    assert analyzer.seen["labels"] == ["caller", "agent"]


def test_run_hang_up_without_words_ends_the_call(tmp_path):
    simulator = _simulator([("hi", False), ("", True)])
    scenario = _scenario()
    report = simulator.run(scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path)
    assert report.simulation.turns == 1


def test_run_errors_when_the_caller_never_speaks(tmp_path):
    simulator = _simulator([("", True)])
    scenario = _scenario()
    with pytest.raises(sim.SimulationError, match="never spoke"):
        simulator.run(scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path)


class RecordingTarget:
    """Returns audio without text and records what it was sent."""

    def __init__(self, delay_ms=700):
        self.received = []
        self.closed = False
        self.delay_ms = delay_ms

    def start(self, scenario):
        return sim.AgentReply(audio=np.ones(SR, np.float32) * 0.1, delay_ms=self.delay_ms)

    def respond(self, caller_audio, caller_text):
        self.received.append((caller_audio.size, caller_text))
        return sim.AgentReply(audio=np.ones(SR // 2, np.float32) * 0.1, hung_up=True)

    def close(self):
        self.closed = True


def test_run_transcribes_agent_audio_without_text_and_closes_target(tmp_path):
    simulator = _simulator([("hello", False)], listener=FakeListener())
    target = RecordingTarget()
    simulator.run(_scenario(), target, tmp_path)
    assert simulator.caller.seen[0] == [("agent", f"heard {SR} samples")]
    assert target.received == [(int(0.1 * SR), "hello")]
    assert target.closed


def test_run_needs_a_listener_for_audio_only_targets(tmp_path):
    target = RecordingTarget()
    with pytest.raises(sim.SimulationError, match="no Listener"):
        _simulator([("hello", False)]).run(_scenario(), target, tmp_path)
    assert target.closed  # closed even when the call fails


def test_barge_in_persona_overlaps_the_agent(tmp_path):
    def caller_channel(persona):
        simulator = _simulator([("hello there", False)], listener=FakeListener())
        simulator.run(_scenario(persona=persona), RecordingTarget(delay_ms=0), tmp_path)
        with wave.open(str(tmp_path / "reschedule.wav")) as wav:
            frames = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").reshape(-1, 2)
        return np.flatnonzero(frames[:, 0])[0], np.flatnonzero(frames[:, 1])[0]

    lead = sim._samples(sim.LEAD_IN_MS)
    caller_start, agent_start = caller_channel("interrupter")
    assert agent_start == lead
    assert caller_start == lead + SR - sim._samples(sim.BARGE_IN_OVERLAP_MS)
    caller_start, _ = caller_channel("neutral")
    assert caller_start == lead + SR + sim._samples(500)


def test_run_uses_suite_personas_and_noise(tmp_path):
    personas = {"p": sim.Persona(name="p", style="s", voice="bm_george", speed=0.9)}
    noise = {"n": sim.NoiseProfile(name="n")}
    simulator = _simulator([("bye", True)])
    scenario = _scenario(persona="p", noise="n")
    report = simulator.run(
        scenario, sim.MockTarget(scenario.mock, FakeSpeech()), tmp_path, personas, noise
    )
    assert (report.simulation.persona, report.simulation.noise) == ("p", "n")
    assert simulator.speech.calls == [("bye", "bm_george", 0.9)]


def test_default_analyzer_labels_speakers(monkeypatch, tmp_path):
    calls = {}

    def fake_analyze(path, num_speakers, speaker_labels):
        calls.update(path=path, num_speakers=num_speakers, labels=speaker_labels)
        return CallReport()

    monkeypatch.setattr("audiotrace.core.analyze", fake_analyze)
    sim.default_analyzer(tmp_path / "x.wav", ["agent", "caller"])
    assert calls == {"path": tmp_path / "x.wav", "num_speakers": 2, "labels": ["agent", "caller"]}


# --- Suites and output ----------------------------------------------------------


def test_run_suite_keys_reports_by_scenario_and_formats_verdicts(tmp_path):
    good = _scenario(name="good")
    bad = _scenario(name="bad / one", success={"must_mention": ["refund"]})
    suite = sim.Suite(scenarios=[good, bad], personas=sim.BUILTIN_PERSONAS, noise=sim.BUILTIN_NOISE)
    simulator = _simulator([("hi", True), ("hi", True)])

    reports = sim.run_suite(suite, simulator, sim.mock_target_factory(FakeSpeech()), tmp_path)

    assert list(reports) == ["good", "bad / one"]
    assert (tmp_path / "bad_one.wav").exists()
    assert sim.failed_scenarios(reports) == ["bad / one"]
    text = sim.format_verdicts(reports)
    assert text.splitlines()[0] == "FAIL — 1 of 2 scenario(s) did not complete the task"
    assert "ok   good (neutral/clean, 1 turn(s): all success criteria met)" in text
    assert "FAIL bad / one (neutral/clean, 1 turn(s): never mentioned: refund)" in text


def test_format_verdicts_pass_and_unsimulated_reports():
    passing = _report()
    passing.simulation = SimulationResult(
        scenario="a", persona="neutral", noise="clean", task_completed=True
    )
    assert sim.format_verdicts({"a": passing}).startswith("PASS — 1 scenario(s)")
    assert sim.failed_scenarios({"real": CallReport()}) == ["real"]
    assert sim.format_verdicts({"real": CallReport()}).endswith("  FAIL real")


def test_safe_name():
    assert sim.safe_name("a b/c") == "a_b_c"
    assert sim.safe_name("///") == "scenario"


def test_reports_show_the_simulation_verdict():
    report = _report()
    assert "Task" not in render_html(report)
    report.simulation = SimulationResult(
        scenario="cancel", persona="frustrated", noise="cafe", task_completed=False, reason="r<"
    )
    page = render_html(report)
    assert '<p class="banner bad">Task failed: cancel · frustrated · cafe — r&lt;</p>' in page
    report.simulation.task_completed = True
    assert '<p class="banner ok">Task completed' in render_html(report)
    assert '"task_completed": true' in render_json(report)
