import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from audiotrace import simulate_backends as backends
from audiotrace.simulate import BUILTIN_PERSONAS, Scenario, SimulationError


class FakeClient:
    """Stands in for anthropic.Anthropic(): records requests, replays texts."""

    def __init__(self, *texts, stop_reason="end_turn"):
        self.texts = list(texts)
        self.requests = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        content = [
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=self.texts.pop(0)),
        ]
        return SimpleNamespace(stop_reason=self.stop_reason, content=content)


SCENARIO = Scenario(name="s", goal="Cancel my plan", hints=["Account 12345"])


def test_caller_builds_the_request_and_returns_the_line():
    client = FakeClient("Hi, I'd like to cancel.")
    caller = backends.ClaudeCaller(client=client)

    turn = caller.next_turn(SCENARIO, BUILTIN_PERSONAS["frustrated"], [("agent", "Hello")])

    assert turn.text == "Hi, I'd like to cancel." and not turn.hang_up
    request = client.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["betas"] == [backends.FALLBACK_BETA]
    assert request["fallbacks"] == "default"
    assert request["output_config"] == {"effort": "low"}
    assert request["messages"] == [{"role": "user", "content": "Hello"}]
    assert "Cancel my plan" in request["system"]
    assert "- Account 12345" in request["system"]
    assert BUILTIN_PERSONAS["frustrated"].style in request["system"]


def test_caller_hangs_up_on_the_end_mark():
    caller = backends.ClaudeCaller(model="claude-sonnet-5-5", effort="medium", client=None)
    caller._client_obj = FakeClient("Great, thanks. Bye! [END]")
    turn = caller.next_turn(Scenario(name="s", goal="g"), BUILTIN_PERSONAS["neutral"], [])
    assert turn.text == "Great, thanks. Bye!" and turn.hang_up
    request = caller._client_obj.requests[0]
    assert request["model"] == "claude-sonnet-5-5"
    assert "Facts you know" not in request["system"]


def test_refusal_raises():
    caller = backends.ClaudeCaller(client=FakeClient("", stop_reason="refusal"))
    with pytest.raises(SimulationError, match="declined"):
        caller.next_turn(SCENARIO, BUILTIN_PERSONAS["neutral"], [])


def test_default_client_is_the_anthropic_sdk():
    fake = MagicMock()
    with patch.dict(sys.modules, {"anthropic": fake}):
        assert backends._client(None) is fake.Anthropic.return_value
    client = object()
    assert backends._client(client) is client


@pytest.mark.parametrize(
    "history, expected",
    [
        ([], [("user", "(The call connects. Silence.)")]),
        (
            [("caller", "Hello?"), ("agent", "")],
            [
                ("user", "(The call connects. Silence.)"),
                ("assistant", "Hello?"),
                ("user", "(silence)"),
            ],
        ),
        (
            [("agent", "Hi"), ("caller", "Hey")],
            [("user", "Hi"), ("assistant", "Hey"), ("user", "(silence)")],
        ),
    ],
)
def test_history_becomes_alternating_messages(history, expected):
    messages = backends._as_messages(history)
    assert [(m["role"], m["content"]) for m in messages] == expected


def test_judge_parses_pass_and_fail():
    client = FakeClient("PASS\nA Thursday slot was booked.", "FAIL", "fail: \nNo time given.")
    judge = backends.ClaudeJudge(client=client)
    assert judge.grade("time booked", "agent: hi") == (True, "A Thursday slot was booked.")
    assert judge.grade("time booked", "agent: hi") == (False, "criterion not met")
    assert judge.grade("time booked", "agent: hi") == (False, "No time given.")
    assert "Criterion: time booked" in client.requests[0]["messages"][0]["content"]
    assert "agent: hi" in client.requests[0]["messages"][0]["content"]


def test_judge_rejects_an_unparseable_answer():
    judge = backends.ClaudeJudge(client=FakeClient("Maybe?"))
    with pytest.raises(SimulationError, match="no PASS/FAIL"):
        judge.grade("x", "y")


def test_kokoro_speech_seeds_and_caches_pipelines():
    torch = MagicMock()
    kokoro = MagicMock()
    chunk = MagicMock()
    chunk.numpy.return_value = np.ones(10, dtype=np.float64)
    kokoro.KPipeline.return_value.side_effect = lambda text, voice, speed: [(None, None, chunk)] * 2

    with patch.dict(sys.modules, {"torch": torch, "kokoro": kokoro}):
        speech = backends.KokoroSpeech()
        audio = speech.synthesize("hello", "af_heart", 1.0)
        speech.synthesize("again", "am_adam", 1.1)

    assert audio.dtype == np.float32 and audio.size == 20
    kokoro.KPipeline.assert_called_once_with(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    assert torch.manual_seed.call_count == 2


def test_kokoro_speech_with_no_chunks_is_empty():
    kokoro = MagicMock()
    kokoro.KPipeline.return_value.return_value = []
    with patch.dict(sys.modules, {"torch": MagicMock(), "kokoro": kokoro}):
        assert backends.KokoroSpeech().synthesize("", "bf_emma", 1.0).size == 0


def test_whisper_listener_resamples_and_transcribes():
    model = MagicMock()
    model.transcribe.return_value = {"text": "  thanks for calling "}
    with patch("audiotrace.transcripts.get_whisper_model", return_value=model) as get:
        listener = backends.WhisperListener()
        text = listener.transcribe(np.zeros(24_000, dtype=np.float32), 24_000)
        assert listener.transcribe(np.zeros(0, dtype=np.float32)) == ""

    assert text == "thanks for calling"
    get.assert_called_once_with("base")
    clip = model.transcribe.call_args.args[0]
    assert clip.size == 16_000
