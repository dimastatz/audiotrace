"""Provider adapters against recorded-shape API responses — no network calls."""

import base64
import json
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from audiotrace import adapters
from audiotrace.adapters import (
    METADATA_KEYS,
    AdapterError,
    RetellAdapter,
    TwilioAdapter,
    VapiAdapter,
    default_cache_dir,
    get_adapter,
)

AUDIO = b"RIFF....WAVEfmt fake-audio"


class FakeTransport:
    """Routes requests by URL prefix to canned bodies (dict -> JSON, bytes as-is,
    int -> HTTPError with that status, Exception -> raised)."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        for prefix, body in self.routes.items():
            if request.full_url.startswith(prefix):
                if isinstance(body, int):
                    raise HTTPError(request.full_url, body, "err", {}, BytesIO(b""))
                if isinstance(body, Exception):
                    raise body
                if callable(body):
                    body = body(request)
                return body if isinstance(body, bytes) else json.dumps(body).encode()
        raise AssertionError(f"unexpected request {request.full_url}")


# Response shapes follow the providers' API references (Vapi GET /call/{id},
# Retell GET /v2/get-call/{id}, Twilio Recording resource).
VAPI_CALL = {
    "id": "call_1",
    "assistantId": "asst_9",
    "startedAt": "2026-10-01T10:00:00.000Z",
    "endedReason": "customer-ended-call",
    "cost": 0.137,
    "createdAt": "2026-10-01T10:00:00.000Z",
    "artifact": {"recording": {"mono": {"combinedUrl": "https://storage.vapi.ai/call_1.wav"}}},
}
RETELL_CALL = {
    "call_id": "rc_1",
    "agent_id": "agent_7",
    "agent_version": 3,
    "start_timestamp": 1_790_000_000_000,
    "disconnection_reason": "user_hangup",
    "recording_url": "https://retell.example/rc_1.mp3?sig=abc",
    "call_cost": {"combined_cost": 12.5},
}
TWILIO_REC = {
    "sid": "RE123",
    "call_sid": "CA456",
    "date_created": "Wed, 01 Oct 2026 10:00:00 +0000",
    "price": "-0.0025",
    "price_unit": "USD",
    "status": "completed",
}


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache"


def test_vapi_fetch_call_downloads_and_normalizes(cache):
    transport = FakeTransport(
        {
            "https://api.vapi.ai/call/call_1": VAPI_CALL,
            "https://storage.vapi.ai/": AUDIO,
        }
    )
    call = VapiAdapter(api_key="k", cache_dir=cache, transport=transport).fetch_call("call_1")

    assert call.audio == cache / "recordings" / "vapi" / "call_1.wav"
    assert call.audio.read_bytes() == AUDIO
    assert set(METADATA_KEYS) <= set(call.metadata)
    assert call.metadata == {
        "call_id": "call_1",
        "provider": "vapi",
        "agent_id": "asst_9",
        "agent_version": None,
        "started_at": "2026-10-01T10:00:00.000Z",
        "ended_reason": "customer-ended-call",
        "provider_cost_usd": 0.137,
    }
    assert transport.requests[0].get_header("Authorization") == "Bearer k"
    assert transport.requests[1].get_header("Authorization") is None  # signed URL
    assert "k" not in json.dumps(call.metadata)


def test_recordings_are_cached_unless_refreshed(cache):
    transport = FakeTransport(
        {"https://api.vapi.ai/call/": VAPI_CALL, "https://storage.vapi.ai/": AUDIO}
    )
    adapter = VapiAdapter(api_key="k", cache_dir=cache, transport=transport)
    adapter.fetch_call("call_1")
    adapter.fetch_call("call_1")
    assert sum("storage" in r.full_url for r in transport.requests) == 1
    adapter.fetch_call("call_1", refresh=True)
    assert sum("storage" in r.full_url for r in transport.requests) == 2
    assert not list(cache.rglob("*.part"))


@pytest.mark.parametrize(
    "raw, url",
    [
        ({"artifact": {"recording": {"stereoUrl": "https://x/s.wav"}}}, "https://x/s.wav"),
        ({"artifact": {"recordingUrl": "https://x/r.mp3"}}, "https://x/r.mp3"),
        ({"artifact": {"stereoRecordingUrl": "https://x/st.wav"}}, "https://x/st.wav"),
        ({"recordingUrl": "https://x/old.wav"}, "https://x/old.wav"),
        ({}, None),
    ],
)
def test_vapi_recording_url_fallbacks(raw, url):
    assert VapiAdapter(api_key="k")._recording_url(raw) == url


def test_vapi_without_cost_or_recording(cache):
    call = dict(VAPI_CALL, cost=None, artifact={})
    adapter = VapiAdapter(
        api_key="k", cache_dir=cache, transport=FakeTransport({"https://api.vapi.ai/": call})
    )
    with pytest.raises(AdapterError, match="has no recording"):
        adapter.fetch_call("call_1")
    assert adapter._metadata(call)["provider_cost_usd"] is None


def test_vapi_list_calls_pages_backwards_by_creation_time():
    page1 = [{"id": f"c{i}", "createdAt": f"t{i}"} for i in range(2)]
    page2 = [{"id": "c2", "createdAt": "t2"}]

    def respond(request):
        query = parse_qs(urlparse(request.full_url).query)
        return page2 if "createdAtLt" in query else page1

    transport = FakeTransport({"https://api.vapi.ai/call?": respond})
    since = datetime(2026, 10, 1, tzinfo=timezone.utc)
    ids = list(VapiAdapter(api_key="k", transport=transport).list_calls(since=since, limit=2))
    assert ids == ["c0", "c1"]
    query = parse_qs(urlparse(transport.requests[0].full_url).query)
    assert query == {"limit": ["2"], "createdAtGt": ["2026-10-01T00:00:00+00:00"]}

    transport.requests.clear()
    ids = list(VapiAdapter(api_key="k", transport=transport).list_calls(limit=5))
    assert ids == ["c0", "c1"]  # first page wasn't full: no second request
    assert len(transport.requests) == 1


def test_vapi_list_calls_follows_full_pages(monkeypatch):
    monkeypatch.setattr(adapters, "PAGE_SIZE", 1)
    pages = iter([[{"id": "a", "createdAt": "t1"}], [{"id": "b", "createdAt": "t2"}], []])
    transport = FakeTransport({"https://api.vapi.ai/call?": lambda r: next(pages)})
    adapter = VapiAdapter(api_key="k", transport=transport)
    adapter_list = list(adapter.list_calls(limit=3))
    assert adapter_list == ["a", "b"]
    assert "createdAtLt=t1" in transport.requests[1].full_url


def test_retell_fetch_call_converts_cents_and_timestamps(cache):
    transport = FakeTransport(
        {
            "https://api.retellai.com/v2/get-call/rc_1": RETELL_CALL,
            "https://retell.example/": AUDIO,
        }
    )
    call = RetellAdapter(api_key="r", cache_dir=cache, transport=transport).fetch_call("rc_1")
    assert call.audio.name == "rc_1.mp3"
    assert call.metadata["provider_cost_usd"] == pytest.approx(0.125)
    assert call.metadata["agent_version"] == 3
    assert call.metadata["started_at"] == "2026-09-21T14:13:20+00:00"
    assert call.metadata["ended_reason"] == "user_hangup"


def test_retell_metadata_without_cost_and_multichannel_fallback():
    adapter = RetellAdapter(api_key="r")
    raw = {"call_id": "x", "recording_multi_channel_url": "https://r/m.wav"}
    assert adapter._metadata(raw)["provider_cost_usd"] is None
    assert adapter._metadata(raw)["started_at"] is None
    assert adapter._recording_url(raw) == "https://r/m.wav"
    assert adapter._recording_url({}) is None


def test_retell_list_calls_paginates_with_filter():
    pages = iter(
        [
            {
                "items": [{"call_id": "a"}, {"call_id": "b"}],
                "has_more": True,
                "pagination_key": "k1",
            },
            {"items": [{"call_id": "c"}], "has_more": False, "pagination_key": "k2"},
        ]
    )
    transport = FakeTransport({"https://api.retellai.com/v3/list-calls": lambda r: next(pages)})
    since = datetime(2026, 10, 1, tzinfo=timezone.utc)
    ids = list(RetellAdapter(api_key="r", transport=transport).list_calls(since=since))
    assert ids == ["a", "b", "c"]
    first = json.loads(transport.requests[0].data)
    assert transport.requests[0].get_method() == "POST"
    assert first["filter_criteria"]["start_timestamp"] == {
        "type": "number",
        "op": "gt",
        "value": 1_790_812_800_000,
    }
    assert json.loads(transport.requests[1].data)["pagination_key"] == "k1"


def test_retell_list_respects_limit():
    page = {"items": [{"call_id": c} for c in "abc"], "has_more": True, "pagination_key": "k"}
    transport = FakeTransport({"https://api.retellai.com/": page})
    assert list(RetellAdapter(api_key="r", transport=transport).list_calls(limit=2)) == ["a", "b"]
    assert len(transport.requests) == 1


def test_twilio_fetch_recording_with_basic_auth(cache):
    transport = FakeTransport(
        {
            "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE123.json": TWILIO_REC,
            "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE123.wav": AUDIO,
        }
    )
    adapter = TwilioAdapter(account_sid="AC1", auth_token="t", cache_dir=cache, transport=transport)
    call = adapter.fetch_call("RE123")
    assert call.audio.name == "RE123.wav"
    assert call.metadata["provider_cost_usd"] == pytest.approx(0.0025)
    assert call.metadata["twilio_call_sid"] == "CA456"
    assert call.metadata["started_at"] == "2026-10-01T10:00:00+00:00"
    expected = "Basic " + base64.b64encode(b"AC1:t").decode()
    assert all(r.get_header("Authorization") == expected for r in transport.requests)


def test_twilio_metadata_edge_cases():
    adapter = TwilioAdapter(account_sid="AC1", auth_token="t")
    assert adapter._recording_url({"sid": "RE1", "status": "processing"}) is None
    assert adapter._recording_url({}) is None
    meta = adapter._metadata({"sid": "RE1", "price": "-1.0", "price_unit": "EUR"})
    assert meta["provider_cost_usd"] is None and meta["started_at"] is None


def test_twilio_list_follows_next_page_uri():
    pages = {
        "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings.json?": {
            "recordings": [{"sid": "RE1"}],
            "next_page_uri": "/2010-04-01/Accounts/AC1/Recordings.json?Page=1",
        },
        "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings.json?Page=1": {
            "recordings": [{"sid": "RE2"}],
            "next_page_uri": None,
        },
    }
    # Longest prefix first so the page-2 URL doesn't match page 1.
    transport = FakeTransport(dict(sorted(pages.items(), key=lambda kv: -len(kv[0]))))
    since = datetime(2026, 10, 1, tzinfo=timezone.utc)
    adapter = TwilioAdapter(account_sid="AC1", auth_token="t", transport=transport)
    assert list(adapter.list_calls(since=since)) == ["RE1", "RE2"]
    assert "DateCreated%3E=2026-10-01" in transport.requests[0].full_url


@pytest.mark.parametrize(
    "status, message",
    [(404, "call nope not found"), (401, "credentials rejected"), (500, "HTTP 500")],
)
def test_http_errors_become_adapter_errors(status, message):
    adapter = VapiAdapter(api_key="k", transport=FakeTransport({"https://": status}))
    with pytest.raises(AdapterError, match=message):
        adapter.fetch_call("nope")


def test_network_and_json_errors():
    down = VapiAdapter(api_key="k", transport=FakeTransport({"https://": URLError("dns")}))
    with pytest.raises(AdapterError, match="cannot reach"):
        down.fetch_call("x")
    garbage = VapiAdapter(api_key="k", transport=FakeTransport({"https://": b"<html>"}))
    with pytest.raises(AdapterError, match="invalid JSON"):
        garbage.fetch_call("x")


def test_missing_credentials(monkeypatch):
    for env in ("VAPI_API_KEY", "RETELL_API_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"):
        monkeypatch.delenv(env, raising=False)
    with pytest.raises(AdapterError, match="set VAPI_API_KEY"):
        VapiAdapter()
    with pytest.raises(AdapterError, match="set RETELL_API_KEY"):
        RetellAdapter()
    with pytest.raises(AdapterError, match="set TWILIO_ACCOUNT_SID"):
        TwilioAdapter(auth_token="t")
    monkeypatch.setenv("VAPI_API_KEY", "from-env")
    assert VapiAdapter()._headers["Authorization"] == "Bearer from-env"


def test_get_adapter_and_cache_dir(monkeypatch, tmp_path):
    assert isinstance(get_adapter("Retell", api_key="r"), RetellAdapter)
    with pytest.raises(AdapterError, match="Unknown provider 'bland'"):
        get_adapter("bland")
    monkeypatch.setenv("AUDIOTRACE_CACHE", str(tmp_path))
    assert default_cache_dir() == tmp_path
    monkeypatch.delenv("AUDIOTRACE_CACHE")
    assert default_cache_dir().parts[-2:] == (".cache", "audiotrace")


def test_unknown_suffix_and_odd_call_ids_are_safe(cache):
    transport = FakeTransport(
        {
            "https://api.vapi.ai/": dict(VAPI_CALL, artifact={"recordingUrl": "https://s/x.bin"}),
            "https://s/": AUDIO,
        }
    )
    call = VapiAdapter(api_key="k", cache_dir=cache, transport=transport).fetch_call("a/b c")
    assert call.audio.name == "a_b_c.wav"


def test_default_transport_uses_urlopen(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"body"

    seen = {}

    def fake_urlopen(request, timeout):
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(adapters, "urlopen", fake_urlopen)
    assert adapters._urlopen(object()) == b"body"
    assert seen["timeout"] == adapters.TIMEOUT_S


def test_fetch_calls_by_id_or_latest(cache):
    from audiotrace.adapters import fetch_calls

    transport = FakeTransport(
        {
            "https://api.vapi.ai/call?": [{"id": "call_1", "createdAt": "t"}],
            "https://api.vapi.ai/call/": VAPI_CALL,
            "https://storage.vapi.ai/": AUDIO,
        }
    )
    adapter = VapiAdapter(api_key="k", cache_dir=cache, transport=transport)
    assert list(fetch_calls(adapter, ["call_1"])) == ["call_1"]
    latest = fetch_calls(adapter, limit=5)
    assert list(latest) == ["call_1"] and latest["call_1"].audio.exists()
    empty = VapiAdapter(api_key="k", transport=FakeTransport({"https://api.vapi.ai/call?": []}))
    with pytest.raises(AdapterError, match="no calls found"):
        fetch_calls(empty)
