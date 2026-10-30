"""Live targets for simulated callers (PRD 0010).

:class:`VapiTarget` calls a Vapi assistant over Vapi's WebSocket transport
(``POST /call`` with ``transport.provider = "vapi.websocket"``): raw 16 kHz
PCM16 audio both ways, JSON control messages, ``{"type": "end-call"}`` to hang
up. Caller audio is streamed in real time (20 ms frames) so the agent's voice
activity detection behaves as on a real call; the agent's turn is over once
it has spoken and then stayed quiet for ``end_silence_ms``.

Needs ``websockets`` (in ``audiotrace[simulate]``) and ``VAPI_API_KEY``.

Retell and SIP targets are not implemented: Retell web calls only connect
through Retell's WebRTC client SDK (no documented raw-audio interface), and a
SIP target needs a full SIP/RTP stack. See PRD 0010.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

import numpy as np

from audiotrace.adapters import Transport, _urlopen
from audiotrace.simulate import (
    SAMPLE_RATE,
    AgentReply,
    Scenario,
    SimulationError,
    Target,
    TargetFactory,
)

WIRE_RATE = 16_000
FRAME_MS = 20
# Frames quieter than this (RMS, full scale = 1) count as silence.
SPEECH_RMS = 0.01


def _resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or not audio.size:
        return audio.astype(np.float32)
    n = int(round(audio.size * dst / src))
    x = np.linspace(0, audio.size - 1, n)
    return np.asarray(np.interp(x, np.arange(audio.size), audio), dtype=np.float32)


def _to_pcm16(audio: np.ndarray) -> bytes:
    return bytes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def _from_pcm16(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def _default_connect(url: str) -> Any:  # pragma: no cover - needs a live socket
    from websockets.sync.client import connect

    return connect(url)


def _default_closed_errors() -> tuple[type[BaseException], ...]:
    from websockets.exceptions import ConnectionClosed

    return (ConnectionClosed,)


class VapiTarget:
    """One simulated call to a Vapi assistant (a fresh call per scenario)."""

    api_url = "https://api.vapi.ai/call"

    def __init__(
        self,
        assistant_id: str,
        api_key: str | None = None,
        end_silence_ms: int = 1200,
        first_audio_timeout_s: float = 15.0,
        realtime: bool = True,
        transport: Transport | None = None,
        connect: Callable[[str], Any] | None = None,
        closed_errors: tuple[type[BaseException], ...] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key or os.environ.get("VAPI_API_KEY")
        if not key:
            raise SimulationError("Vapi target: no credentials (pass api_key or set VAPI_API_KEY)")
        self.assistant_id = assistant_id
        self.end_silence_s = end_silence_ms / 1000
        self.first_audio_timeout_s = first_audio_timeout_s
        self.realtime = realtime
        self.call_id: str | None = None
        self._key = key
        self._transport = transport or _urlopen
        self._connect = connect or _default_connect
        self._closed = closed_errors
        self._clock = clock
        self._sleep = sleep
        self._ws: Any = None
        self._hung_up = False

    # --- Target interface -------------------------------------------------------

    def start(self, scenario: Scenario) -> AgentReply:
        from urllib.request import Request

        body = {
            "assistantId": self.assistant_id,
            "metadata": {"audiotrace_scenario": scenario.name},
            "transport": {
                "provider": "vapi.websocket",
                "audioFormat": {"format": "pcm_s16le", "container": "raw", "sampleRate": WIRE_RATE},
            },
        }
        request = Request(
            self.api_url,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            call = json.loads(self._transport(request))
            url = call["transport"]["websocketCallUrl"]
        except Exception as exc:
            raise SimulationError(f"Vapi target: could not start a call: {exc}") from exc
        self.call_id = call.get("id")
        self._ws = self._connect(url)
        return self._listen()

    def respond(self, caller_audio: np.ndarray, caller_text: str) -> AgentReply:
        if self._hung_up:
            return AgentReply(audio=np.zeros(0, np.float32), text=None, hung_up=True)
        wire = _resample(caller_audio, SAMPLE_RATE, WIRE_RATE)
        # Trailing silence lets the agent's end-of-speech detection fire.
        wire = np.concatenate([wire, np.zeros(int(0.6 * WIRE_RATE), np.float32)])
        step = WIRE_RATE * FRAME_MS // 1000
        try:
            for i in range(0, wire.size, step):
                self._ws.send(_to_pcm16(wire[i : i + step]))
                if self.realtime:
                    self._sleep(FRAME_MS / 1000)
        except self._closed_types():
            self._hung_up = True
            return AgentReply(audio=np.zeros(0, np.float32), text=None, hung_up=True)
        return self._listen()

    def close(self) -> None:
        if self._ws is None:
            return
        try:
            self._ws.send(json.dumps({"type": "end-call"}))
        except self._closed_types():
            pass
        self._ws.close()
        self._ws = None

    # --- internals ---------------------------------------------------------------

    def _closed_types(self) -> tuple[type[BaseException], ...]:
        if self._closed is None:
            self._closed = _default_closed_errors()
        return self._closed

    def _listen(self) -> AgentReply:
        """Collect one agent turn: wait for speech, stop after trailing silence."""
        frames: list[np.ndarray] = []
        t0 = self._clock()
        started: float | None = None
        last_voice = t0
        while True:
            now = self._clock()
            if started is None and now - t0 > self.first_audio_timeout_s:
                break
            if started is not None and now - last_voice > self.end_silence_s:
                break
            try:
                message = self._ws.recv(timeout=0.1)
            except TimeoutError:
                continue
            except self._closed_types():
                self._hung_up = True
                break
            if isinstance(message, str):
                continue  # JSON status/transcript messages; the Listener transcribes audio
            now = self._clock()  # when this frame arrived
            frame = _from_pcm16(message)
            loud = _rms(frame) >= SPEECH_RMS
            if started is None:
                if not loud:
                    continue  # leading silence before the agent speaks
                started = now
            frames.append(frame)
            if loud:
                last_voice = now
        audio = np.concatenate(frames) if frames else np.zeros(0, np.float32)
        delay_ms = int((started - t0) * 1000) if started is not None else 0
        return AgentReply(
            audio=_resample(audio, WIRE_RATE, SAMPLE_RATE),
            text=None,
            delay_ms=delay_ms,
            hung_up=self._hung_up,
        )


def vapi_target_factory(assistant_id: str, **kwargs: Any) -> TargetFactory:
    """A factory for ``--target vapi:<assistant_id>``: one call per scenario."""

    def factory(scenario: Scenario) -> Target:
        return VapiTarget(assistant_id, **kwargs)

    return factory


def resolve_target(spec: str, speech: Any) -> TargetFactory:
    """``mock``, ``vapi:<assistant_id>``, or ``module:factory``."""
    from audiotrace.simulate import load_target_factory, mock_target_factory

    if spec == "mock":
        return mock_target_factory(speech)
    if spec.startswith("vapi:"):
        assistant_id = spec.split(":", 1)[1]
        if not assistant_id:
            raise SimulationError("Use --target vapi:<assistant_id>")
        return vapi_target_factory(assistant_id)
    if spec.split(":", 1)[0] in ("retell", "sip"):
        raise SimulationError(
            f"{spec.split(':', 1)[0]} targets aren't supported yet (see PRD 0010); "
            "wrap your agent in a module:factory target instead"
        )
    return load_target_factory(spec)
