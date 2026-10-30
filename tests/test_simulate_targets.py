"""Vapi WebSocket target against a scripted fake socket — no network."""

import json

import numpy as np
import pytest

from audiotrace.simulate import SAMPLE_RATE, MockTarget, Scenario, SimulationError
from audiotrace.simulate_targets import (
    FRAME_MS,
    WIRE_RATE,
    VapiTarget,
    _resample,
    resolve_target,
    vapi_target_factory,
)

SCENARIO = Scenario(name="s", goal="g")
FRAME = WIRE_RATE * FRAME_MS // 1000


class Closed(Exception):
    pass


def loud(frames=1):
    t = np.arange(FRAME * frames)
    return (0.3 * np.sin(t * 0.2) * 32767).astype("<i2").tobytes()


def quiet(frames=1):
    return np.zeros(FRAME * frames, dtype="<i2").tobytes()


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeSocket:
    """recv() pops scripted items; each recv advances the fake clock by 0.1 s.
    Items: bytes/str are messages, None is a recv timeout, Closed is raised."""

    def __init__(self, clock, script):
        self.clock = clock
        self.script = list(script)
        self.sent = []
        self.closed = False
        self.fail_send = False

    def recv(self, timeout):
        self.clock.now += 0.1
        item = self.script.pop(0) if self.script else None
        if item is None:
            raise TimeoutError
        if isinstance(item, type) and issubclass(item, Exception):
            raise item()
        return item

    def send(self, data):
        if self.fail_send:
            raise Closed()
        self.sent.append(data)

    def close(self):
        self.closed = True


def make_target(script, **kwargs):
    clock = FakeClock()
    socket = FakeSocket(clock, script)
    requests = []

    def transport(request):
        requests.append(request)
        return json.dumps(
            {
                "id": "call_9",
                "transport": {"websocketCallUrl": "wss://api.vapi.ai/call_9/transport"},
            }
        ).encode()

    urls = []
    target = VapiTarget(
        "asst_1",
        api_key="k",
        transport=transport,
        connect=lambda url: urls.append(url) or socket,
        closed_errors=(Closed,),
        clock=clock,
        sleep=lambda s: None,
        **kwargs,
    )
    return target, socket, requests, urls


def test_start_creates_a_websocket_call_and_collects_the_greeting():
    script = [quiet(), '{"type": "status"}', None, loud(), quiet(), loud(), None]
    script += [quiet()] * 20
    target, socket, requests, urls = make_target(script, end_silence_ms=500)

    reply = target.start(SCENARIO)

    body = json.loads(requests[0].data)
    assert requests[0].full_url == "https://api.vapi.ai/call"
    assert requests[0].get_header("Authorization") == "Bearer k"
    assert body["assistantId"] == "asst_1"
    assert body["transport"] == {
        "provider": "vapi.websocket",
        "audioFormat": {"format": "pcm_s16le", "container": "raw", "sampleRate": 16000},
    }
    assert urls == ["wss://api.vapi.ai/call_9/transport"] and target.call_id == "call_9"
    assert reply.text is None and not reply.hung_up
    assert reply.delay_ms == 400  # three recvs of leading silence/status/timeout, then speech
    # loud + quiet + loud + trailing quiet frames until 0.5 s of silence, resampled to 24 kHz
    assert reply.audio.size % (FRAME * SAMPLE_RATE // WIRE_RATE) == 0
    assert reply.audio.size >= 3 * FRAME * SAMPLE_RATE // WIRE_RATE


def test_silent_agent_times_out_with_empty_audio():
    target, _, _, _ = make_target([quiet()] * 5, first_audio_timeout_s=0.3)
    reply = target.start(SCENARIO)
    assert reply.audio.size == 0 and reply.delay_ms == 0 and not reply.hung_up


def test_respond_streams_caller_audio_in_frames_with_trailing_silence():
    target, socket, _, _ = make_target([loud(), *[quiet()] * 20, loud(), *[quiet()] * 20])
    sleeps = []
    target._sleep = sleeps.append
    target.start(SCENARIO)
    caller = np.ones(SAMPLE_RATE // 2, np.float32) * 0.1  # 0.5 s at 24 kHz
    reply = target.respond(caller, "hello")
    wire_samples = WIRE_RATE // 2 + int(0.6 * WIRE_RATE)
    assert len(socket.sent) == -(-wire_samples // FRAME)
    assert all(len(chunk) <= FRAME * 2 for chunk in socket.sent)
    assert len(sleeps) == len(socket.sent)
    assert reply.audio.size > 0


def test_agent_hang_up_is_reported_and_later_turns_are_skipped():
    target, socket, _, _ = make_target([loud(), Closed])
    reply = target.start(SCENARIO)
    assert reply.hung_up and reply.audio.size > 0
    assert target.respond(np.ones(10, np.float32), "x").hung_up
    assert socket.sent == []


def test_send_failure_marks_hang_up():
    target, socket, _, _ = make_target([loud(), *[quiet()] * 20])
    target.start(SCENARIO)
    socket.fail_send = True
    assert target.respond(np.ones(100, np.float32), "x").hung_up


def test_close_ends_the_call_once():
    target, socket, _, _ = make_target([loud(), *[quiet()] * 20])
    target.close()  # before start: nothing to close
    target.start(SCENARIO)
    target.close()
    assert json.loads(socket.sent[-1]) == {"type": "end-call"} and socket.closed
    target.close()


def test_close_tolerates_an_already_closed_socket():
    target, socket, _, _ = make_target([loud(), *[quiet()] * 20])
    target.start(SCENARIO)
    socket.fail_send = True
    target.close()
    assert socket.closed


def test_start_errors_are_simulation_errors():
    def broken(request):
        return b'{"error": "bad assistant"}'

    target = VapiTarget("asst_1", api_key="k", transport=broken, connect=lambda u: None)
    with pytest.raises(SimulationError, match="could not start a call"):
        target.start(SCENARIO)


def test_credentials_required(monkeypatch):
    monkeypatch.delenv("VAPI_API_KEY", raising=False)
    with pytest.raises(SimulationError, match="VAPI_API_KEY"):
        VapiTarget("asst_1")
    monkeypatch.setenv("VAPI_API_KEY", "env")
    assert VapiTarget("asst_1")._key == "env"


def test_default_closed_errors_are_websockets():
    pytest.importorskip("websockets")
    from websockets.exceptions import ConnectionClosed

    target = VapiTarget("a", api_key="k")
    assert target._closed_types() == (ConnectionClosed,)


def test_resample_round_trip_lengths():
    audio = np.ones(SAMPLE_RATE, np.float32)
    assert _resample(audio, SAMPLE_RATE, WIRE_RATE).size == WIRE_RATE
    assert _resample(audio, SAMPLE_RATE, SAMPLE_RATE) is not audio
    assert _resample(np.zeros(0), SAMPLE_RATE, WIRE_RATE).size == 0


def test_resolve_target_specs(monkeypatch):
    monkeypatch.setenv("VAPI_API_KEY", "k")
    mock = resolve_target("mock", speech=object())
    assert isinstance(mock(Scenario(name="m", goal="g", mock={})), MockTarget)
    vapi = resolve_target("vapi:asst_7", speech=None)
    assert vapi(SCENARIO).assistant_id == "asst_7"
    assert isinstance(vapi_target_factory("a", api_key="x")(SCENARIO), VapiTarget)
    with pytest.raises(SimulationError, match="vapi:<assistant_id>"):
        resolve_target("vapi:", speech=None)
    with pytest.raises(SimulationError, match="retell targets aren't supported"):
        resolve_target("retell:agent_1", speech=None)
    with pytest.raises(SimulationError, match="sip targets"):
        resolve_target("sip:+15551234", speech=None)
    factory = resolve_target("audiotrace.simulate:mock_target_factory", speech=None)
    assert callable(factory)
