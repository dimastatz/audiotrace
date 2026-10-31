"""Custom webhook adapter and receiver (PRD 0014) — downloads are faked."""

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from audiotrace.adapters import AdapterError, CustomAdapter, resolve_path
from audiotrace.models import CallReport
from audiotrace.webhook import WebhookApp, make_server, sign, verify

AUDIO = b"fake-audio"

# Two differently shaped end-of-call events, e.g. a LiveKit egress hook and
# a home-grown SIP stack.
LIVEKIT_EVENT = {
    "event": "egress_ended",
    "data": {
        "id": "EG_1",
        "recording": {"files": [{"location": "https://bucket.example/EG_1.ogg"}]},
        "metadata": {"agent_version": "v2.1"},
        "started_at": "2026-10-30T09:00:00Z",
    },
}
LIVEKIT_MAPPING = {
    "recording_url": "$.data.recording.files[0].location",
    "call_id": "$.data.id",
    "agent_version": "$.data.metadata.agent_version",
    "started_at": "$.data.started_at",
}
SIP_EVENT = {"uuid": 42, "wav": "https://pbx.example/rec/42.wav", "hangup_cause": "NORMAL"}
SIP_MAPPING = {
    "recording_url": "wav",
    "call_id": "uuid",
    "ended_reason": "hangup_cause",
    "campaign": lambda payload: "spring" if payload["uuid"] > 10 else None,
}


def fake_transport(seen):
    def transport(request):
        seen.append(request)
        return AUDIO

    return transport


@pytest.mark.parametrize(
    "path, expected",
    [
        ("$.data.id", "EG_1"),
        ("data.recording.files[0].location", "https://bucket.example/EG_1.ogg"),
        ("$.data.recording.files[3].location", None),
        ("$.data.nope", None),
        ("$.event[0]", None),
        ("$.data.id.deeper", None),
    ],
)
def test_resolve_path(path, expected):
    assert resolve_path(LIVEKIT_EVENT, path) == expected


@pytest.mark.parametrize(
    "event, mapping, call_id, suffix, extra",
    [
        (LIVEKIT_EVENT, LIVEKIT_MAPPING, "EG_1", ".ogg", {"agent_version": "v2.1"}),
        (SIP_EVENT, SIP_MAPPING, "42", ".wav", {"ended_reason": "NORMAL", "campaign": "spring"}),
    ],
)
def test_parse_maps_two_payload_shapes(tmp_path, event, mapping, call_id, suffix, extra):
    seen = []
    adapter = CustomAdapter(mapping, cache_dir=tmp_path, transport=fake_transport(seen))
    call = adapter.parse(event)
    assert call.audio.name == call_id + suffix and call.audio.read_bytes() == AUDIO
    assert call.metadata["call_id"] == call_id
    assert call.metadata["provider"] == "custom"
    assert call.metadata["provider_cost_usd"] is None  # normalized keys always present
    for key, value in extra.items():
        assert call.metadata[key] == value


def test_optional_fields_are_skipped_and_required_ones_error(tmp_path):
    adapter = CustomAdapter(SIP_MAPPING, cache_dir=tmp_path, transport=fake_transport([]))
    small = dict(SIP_EVENT, uuid=1)
    del small["hangup_cause"]
    assert adapter.extract(small)[1]["ended_reason"] is None
    assert "campaign" not in adapter.extract(small)[1]
    with pytest.raises(AdapterError, match="no 'recording_url' at 'wav'"):
        adapter.extract({"uuid": 1})
    with pytest.raises(AdapterError, match="Mapping must define: call_id"):
        CustomAdapter({"recording_url": "x"})


def test_custom_adapter_has_no_api(tmp_path):
    adapter = CustomAdapter(SIP_MAPPING, cache_dir=tmp_path, transport=fake_transport([]))
    with pytest.raises(AdapterError, match="use parse"):
        adapter.fetch_call("42")
    assert list(adapter.list_calls()) == []
    assert adapter._recording_url(SIP_EVENT) == "https://pbx.example/rec/42.wav"
    assert adapter._metadata(SIP_EVENT)["call_id"] == "42"


def test_from_yaml_with_headers_from_env(tmp_path, monkeypatch):
    pytest.importorskip("yaml")
    monkeypatch.setenv("REC_TOKEN", "s3cr3t")
    path = tmp_path / "mapping.yaml"
    path.write_text(
        "provider: livekit\n"
        "recording_headers:\n  Authorization: Bearer ${REC_TOKEN}\n"
        "fields:\n  recording_url: $.data.recording.files[0].location\n  call_id: $.data.id\n",
        encoding="utf-8",
    )
    seen = []
    adapter = CustomAdapter.from_yaml(path, cache_dir=tmp_path, transport=fake_transport(seen))
    call = adapter.parse(LIVEKIT_EVENT)
    assert call.metadata["provider"] == "livekit"
    assert seen[0].get_header("Authorization") == "Bearer s3cr3t"

    bare = tmp_path / "bare.yaml"
    bare.write_text("recording_url: wav\ncall_id: uuid\n", encoding="utf-8")
    assert CustomAdapter.from_yaml(bare).mapping == {"recording_url": "wav", "call_id": "uuid"}
    bad = tmp_path / "bad.yaml"
    bad.write_text("- a list\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="expected a mapping"):
        CustomAdapter.from_yaml(bad)


# --- receiver ---------------------------------------------------------------------


SECRET = "shh"


def _app(tmp_path, analyzer=None):
    adapter = CustomAdapter(SIP_MAPPING, cache_dir=tmp_path / "cache", transport=fake_transport([]))
    return WebhookApp(
        adapter=adapter,
        secret=SECRET,
        out_dir=tmp_path / "reports",
        analyzer=analyzer or (lambda call: CallReport()),
    )


def test_sign_and_verify():
    body = b'{"a": 1}'
    assert verify(body, SECRET, sign(body, SECRET))
    assert not verify(body, SECRET, sign(body, "other"))
    assert not verify(body, SECRET, None)
    assert not verify(body, SECRET, "")


def test_handle_rejects_bad_requests(tmp_path):
    app = _app(tmp_path)
    body = json.dumps(SIP_EVENT).encode()
    assert app.handle(body, {})[0] == 401
    assert app.handle(body, {"X-AudioTrace-Signature": "sha256=deadbeef"})[0] == 401
    assert app.handle(b"not json", {"X-AudioTrace-Signature": sign(b"not json", SECRET)}) == (
        400,
        {"error": "body is not JSON"},
    )
    empty = b"{}"
    status, reply = app.handle(empty, {"x-audiotrace-signature": sign(empty, SECRET)})
    assert status == 422 and "recording_url" in reply["error"]
    assert app.jobs.empty()


def test_handle_queues_and_process_writes_the_report(tmp_path):
    analyzed = []
    app = _app(tmp_path, analyzer=lambda call: analyzed.append(call) or CallReport())
    body = json.dumps(SIP_EVENT).encode()
    assert app.handle(body, {"X-AudioTrace-Signature": sign(body, SECRET)}) == (
        202,
        {"call_id": "42", "status": "queued"},
    )
    out = app.process(app.jobs.get())
    assert out == tmp_path / "reports" / "42.json"
    assert out.exists() and (tmp_path / "reports" / "42.html").exists()
    assert analyzed[0].metadata["ended_reason"] == "NORMAL"


def test_worker_survives_a_failing_call_and_stops_on_none(tmp_path):
    calls = []

    def analyzer(call):
        calls.append(call)
        if len(calls) == 1:
            raise RuntimeError("model crashed")
        return CallReport()

    app = _app(tmp_path, analyzer)
    for payload in (SIP_EVENT, dict(SIP_EVENT, uuid=7), None):
        app.jobs.put(payload)
    app.work()
    assert len(calls) == 2
    assert (tmp_path / "reports" / "7.json").exists()
    assert not (tmp_path / "reports" / "42.json").exists()


def test_http_server_end_to_end(tmp_path):
    app = _app(tmp_path)
    server = make_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/"
    try:
        body = json.dumps(SIP_EVENT).encode()
        request = Request(base, data=body, headers={"X-AudioTrace-Signature": sign(body, SECRET)})
        with urlopen(request) as response:
            assert response.status == 202
            assert json.loads(response.read())["call_id"] == "42"
        with pytest.raises(HTTPError) as unsigned:
            urlopen(Request(base, data=body))
        assert unsigned.value.code == 401
        with pytest.raises(HTTPError) as huge:
            urlopen(Request(base, data=b"x", headers={"Content-Length": "2000000"}))
        assert huge.value.code == 413
        with urlopen(base) as health:
            assert json.loads(health.read()) == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()
    assert app.jobs.qsize() == 1


def test_default_analyzer_runs_analyze(monkeypatch, tmp_path):
    from audiotrace import webhook
    from audiotrace.adapters import ProviderCall

    seen = {}

    def fake_analyze(audio, metadata, num_speakers):
        seen.update(audio=audio, metadata=metadata, num_speakers=num_speakers)
        return CallReport()

    monkeypatch.setattr("audiotrace.core.analyze", fake_analyze)
    webhook.default_analyzer(ProviderCall(audio=tmp_path / "a.wav", metadata={"x": 1}))
    assert seen == {"audio": tmp_path / "a.wav", "metadata": {"x": 1}, "num_speakers": 2}
