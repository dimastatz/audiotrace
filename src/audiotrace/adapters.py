"""Provider adapters: fetch a call from a provider's API as ``analyze()`` input (PRD 0012).

    >>> from audiotrace.adapters import VapiAdapter
    >>> call = VapiAdapter().fetch_call("abc123")      # VAPI_API_KEY from the env
    >>> report = audiotrace.analyze(call.audio, call.metadata)

Every adapter returns a :class:`ProviderCall`: a local recording plus metadata
with the same keys from every provider (:data:`METADATA_KEYS`, ``None`` where a
provider doesn't report one). Recordings are downloaded once into a cache
directory and reused.

Plain HTTP over the standard library — no provider SDKs, so no extra installs.
Credentials come from arguments or environment variables and are never put in
metadata or reports.
"""

from __future__ import annotations

import base64
import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

# Normalized metadata keys, present on every ProviderCall.
METADATA_KEYS = (
    "call_id",
    "provider",
    "agent_id",
    "agent_version",
    "started_at",
    "ended_reason",
    "provider_cost_usd",
)

TIMEOUT_S = 60
# Calls requested per API page.
PAGE_SIZE = 100
AUDIO_SUFFIXES = (".wav", ".mp3", ".ogg", ".opus", ".m4a", ".flac", ".webm")

# (request) -> response body. Swappable so tests never touch the network.
Transport = Callable[[Request], bytes]


class AdapterError(Exception):
    """Missing credentials, an unknown call, or a provider/API failure."""


@dataclass(frozen=True)
class ProviderCall:
    """A provider call as ``analyze()`` input: a local recording and metadata."""

    audio: Path
    metadata: dict[str, Any] = field(default_factory=dict)


def default_cache_dir() -> Path:
    """``$AUDIOTRACE_CACHE`` or ``~/.cache/audiotrace``; recordings live under
    ``recordings/<provider>/`` and stay until you delete them."""
    root = os.environ.get("AUDIOTRACE_CACHE") or Path.home() / ".cache" / "audiotrace"
    return Path(root)


def _urlopen(request: Request) -> bytes:
    with urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 (https only)
        body: bytes = response.read()
        return body


def _iso_ms(epoch_ms: Any) -> str | None:
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=timezone.utc).isoformat()


def _safe(call_id: str) -> str:
    return re.sub(r"[^\w.-]+", "_", call_id) or "call"


class BaseAdapter(ABC):
    """Fetch calls from one provider. Subclasses set :attr:`provider` and
    implement :meth:`_get_call`, :meth:`_list_page`, :meth:`_recording_url`,
    :meth:`_metadata`."""

    provider: str = ""

    def __init__(
        self, cache_dir: str | Path | None = None, transport: Transport | None = None
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self._transport = transport or _urlopen

    # --- public API ---------------------------------------------------------

    def fetch_call(self, call_id: str, refresh: bool = False) -> ProviderCall:
        """Download (or reuse the cached) recording of ``call_id``."""
        raw = self._get_call(call_id)
        url = self._recording_url(raw)
        if not url:
            raise AdapterError(f"{self.provider} call {call_id} has no recording (yet)")
        metadata: dict[str, Any] = dict.fromkeys(METADATA_KEYS)
        metadata.update(self._metadata(raw))
        metadata["provider"] = self.provider
        return ProviderCall(audio=self._download(call_id, url, refresh), metadata=metadata)

    def list_calls(self, since: datetime | None = None, limit: int = 100) -> Iterator[str]:
        """Call IDs, newest first where the provider allows, at most ``limit``."""
        yielded = 0
        cursor: str | None = None
        while yielded < limit:
            ids, cursor = self._list_page(since, min(limit - yielded, PAGE_SIZE), cursor)
            for call_id in ids[: limit - yielded]:
                yield call_id
                yielded += 1
            if not cursor or not ids:
                return

    # --- provider hooks -----------------------------------------------------

    @abstractmethod
    def _get_call(self, call_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def _list_page(
        self, since: datetime | None, limit: int, cursor: str | None
    ) -> tuple[list[str], str | None]: ...

    @abstractmethod
    def _recording_url(self, raw: dict[str, Any]) -> str | None: ...

    @abstractmethod
    def _metadata(self, raw: dict[str, Any]) -> dict[str, Any]: ...

    def _recording_headers(self) -> dict[str, str]:
        """Headers for downloading the recording (none: provider URLs are signed)."""
        return {}

    # --- HTTP -----------------------------------------------------------------

    def _request(
        self,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
        what: str = "",
    ) -> bytes:
        data = json.dumps(body).encode() if body is not None else None
        all_headers = {"Accept": "application/json", **headers}
        if data is not None:
            all_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=all_headers, method="POST" if data else "GET")
        try:
            return self._transport(request)
        except HTTPError as exc:
            if exc.code == 404:
                raise AdapterError(f"{self.provider}: {what or url} not found") from exc
            if exc.code in (401, 403):
                raise AdapterError(f"{self.provider}: credentials rejected ({exc.code})") from exc
            raise AdapterError(f"{self.provider}: HTTP {exc.code} for {what or url}") from exc
        except URLError as exc:
            raise AdapterError(f"{self.provider}: cannot reach the API ({exc.reason})") from exc

    def _json(self, url: str, headers: dict[str, str], **kwargs: Any) -> Any:
        raw = self._request(url, headers, **kwargs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"{self.provider}: invalid JSON from {url}") from exc

    def _download(self, call_id: str, url: str, refresh: bool) -> Path:
        suffix = Path(urlparse(url).path).suffix.lower()
        suffix = suffix if suffix in AUDIO_SUFFIXES else ".wav"
        path = self.cache_dir / "recordings" / self.provider / f"{_safe(call_id)}{suffix}"
        if path.exists() and not refresh:
            return path
        audio = self._request(url, self._recording_headers(), what=f"recording of {call_id}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(audio)
        tmp.replace(path)  # never leave a half-written recording in the cache
        return path


def _require(value: str | None, env: str, provider: str) -> str:
    resolved = value or os.environ.get(env)
    if not resolved:
        raise AdapterError(f"{provider}: no credentials (pass them or set {env})")
    return resolved


class VapiAdapter(BaseAdapter):
    """Vapi calls via ``GET /call/{id}`` and ``GET /call``. Key: ``VAPI_API_KEY``."""

    provider = "vapi"
    base_url = "https://api.vapi.ai"

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._headers = {"Authorization": f"Bearer {_require(api_key, 'VAPI_API_KEY', 'vapi')}"}

    def _get_call(self, call_id: str) -> dict[str, Any]:
        data: dict[str, Any] = self._json(
            f"{self.base_url}/call/{call_id}", self._headers, what=f"call {call_id}"
        )
        return data

    def _list_page(
        self, since: datetime | None, limit: int, cursor: str | None
    ) -> tuple[list[str], str | None]:
        # Vapi returns newest first; page backwards with createdAtLt.
        params: dict[str, Any] = {"limit": limit}
        if since is not None:
            params["createdAtGt"] = since.isoformat()
        if cursor:
            params["createdAtLt"] = cursor
        calls = self._json(f"{self.base_url}/call?{urlencode(params)}", self._headers)
        ids = [c["id"] for c in calls]
        # Vapi pages by time: continue below the oldest call of a full page.
        more = len(calls) == limit and calls[-1].get("createdAt")
        return ids, more or None

    def _recording_url(self, raw: dict[str, Any]) -> str | None:
        artifact = raw.get("artifact") or {}
        recording = artifact.get("recording") or {}
        mono = recording.get("mono") or {}
        url = (
            mono.get("combinedUrl")
            or recording.get("stereoUrl")
            or artifact.get("recordingUrl")
            or artifact.get("stereoRecordingUrl")
            or raw.get("recordingUrl")
        )
        return str(url) if url else None

    def _metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        cost = raw.get("cost")
        return {
            "call_id": raw.get("id"),
            "agent_id": raw.get("assistantId"),
            "started_at": raw.get("startedAt"),
            "ended_reason": raw.get("endedReason"),
            "provider_cost_usd": float(cost) if cost is not None else None,
        }


class RetellAdapter(BaseAdapter):
    """Retell calls via ``GET /v2/get-call/{id}`` and ``POST /v3/list-calls``.
    Key: ``RETELL_API_KEY``. Retell reports cost in cents; metadata is in USD."""

    provider = "retell"
    base_url = "https://api.retellai.com"

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        key = _require(api_key, "RETELL_API_KEY", "retell")
        self._headers = {"Authorization": f"Bearer {key}"}

    def _get_call(self, call_id: str) -> dict[str, Any]:
        data: dict[str, Any] = self._json(
            f"{self.base_url}/v2/get-call/{call_id}", self._headers, what=f"call {call_id}"
        )
        return data

    def _list_page(
        self, since: datetime | None, limit: int, cursor: str | None
    ) -> tuple[list[str], str | None]:
        body: dict[str, Any] = {"limit": limit, "sort_order": "descending"}
        if since is not None:
            body["filter_criteria"] = {
                "start_timestamp": {
                    "type": "number",
                    "op": "gt",
                    "value": int(since.timestamp() * 1000),
                }
            }
        if cursor:
            body["pagination_key"] = cursor
        page = self._json(f"{self.base_url}/v3/list-calls", self._headers, body=body)
        ids = [c["call_id"] for c in page.get("items", [])]
        return ids, page.get("pagination_key") if page.get("has_more") else None

    def _recording_url(self, raw: dict[str, Any]) -> str | None:
        url = raw.get("recording_url") or raw.get("recording_multi_channel_url")
        return str(url) if url else None

    def _metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        cents = (raw.get("call_cost") or {}).get("combined_cost")
        return {
            "call_id": raw.get("call_id"),
            "agent_id": raw.get("agent_id"),
            "agent_version": raw.get("agent_version"),
            "started_at": _iso_ms(raw.get("start_timestamp")),
            "ended_reason": raw.get("disconnection_reason"),
            "provider_cost_usd": float(cents) / 100 if cents is not None else None,
        }


class TwilioAdapter(BaseAdapter):
    """Twilio *recordings* (call IDs are Recording SIDs, ``RE...``).
    Credentials: ``TWILIO_ACCOUNT_SID`` and ``TWILIO_AUTH_TOKEN``."""

    provider = "twilio"
    base_url = "https://api.twilio.com/2010-04-01"

    def __init__(
        self, account_sid: str | None = None, auth_token: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.account_sid = _require(account_sid, "TWILIO_ACCOUNT_SID", "twilio")
        token = _require(auth_token, "TWILIO_AUTH_TOKEN", "twilio")
        basic = base64.b64encode(f"{self.account_sid}:{token}".encode()).decode()
        self._headers = {"Authorization": f"Basic {basic}"}

    @property
    def _account_url(self) -> str:
        return f"{self.base_url}/Accounts/{self.account_sid}"

    def _get_call(self, call_id: str) -> dict[str, Any]:
        data: dict[str, Any] = self._json(
            f"{self._account_url}/Recordings/{call_id}.json",
            self._headers,
            what=f"recording {call_id}",
        )
        return data

    def _list_page(
        self, since: datetime | None, limit: int, cursor: str | None
    ) -> tuple[list[str], str | None]:
        if cursor:
            url = f"https://api.twilio.com{cursor}"
        else:
            params: dict[str, Any] = {"PageSize": limit}
            if since is not None:
                params["DateCreated>"] = since.strftime("%Y-%m-%d")
            url = f"{self._account_url}/Recordings.json?{urlencode(params)}"
        page = self._json(url, self._headers)
        return [r["sid"] for r in page.get("recordings", [])], page.get("next_page_uri")

    def _recording_url(self, raw: dict[str, Any]) -> str | None:
        if raw.get("status") not in (None, "completed"):
            return None
        sid = raw.get("sid")
        return f"{self._account_url}/Recordings/{sid}.wav" if sid else None

    def _recording_headers(self) -> dict[str, str]:
        return self._headers

    def _metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        price = raw.get("price")
        created = raw.get("date_created")
        usd = (raw.get("price_unit") or "USD").upper() == "USD"
        return {
            "call_id": raw.get("sid"),
            "twilio_call_sid": raw.get("call_sid"),
            "started_at": parsedate_to_datetime(created).isoformat() if created else None,
            # Twilio reports charges as negative amounts.
            "provider_cost_usd": abs(float(price)) if price is not None and usd else None,
        }


ADAPTERS: dict[str, type[BaseAdapter]] = {
    "vapi": VapiAdapter,
    "retell": RetellAdapter,
    "twilio": TwilioAdapter,
}


def get_adapter(provider: str, **kwargs: Any) -> BaseAdapter:
    """Construct the adapter for ``provider`` (``vapi``, ``retell``, ``twilio``)."""
    try:
        cls = ADAPTERS[provider.lower()]
    except KeyError:
        raise AdapterError(
            f"Unknown provider {provider!r} (available: {', '.join(sorted(ADAPTERS))})"
        ) from None
    return cls(**kwargs)


def fetch_calls(
    adapter: BaseAdapter,
    call_ids: list[str] | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> dict[str, ProviderCall]:
    """Fetch the given calls, or the latest ``limit`` since ``since``, keyed by
    call id (the key the regression baseline uses)."""
    ids = call_ids if call_ids else list(adapter.list_calls(since=since, limit=limit))
    if not ids:
        raise AdapterError(f"{adapter.provider}: no calls found")
    return {call_id: adapter.fetch_call(call_id) for call_id in ids}
