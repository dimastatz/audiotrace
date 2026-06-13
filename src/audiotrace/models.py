"""Pydantic models describing a normalized call analysis.

The shape mirrors the public ``CallReport`` documented in the README. These
models are the stable contract of the library; the extraction pipeline that
fills them in lives in :mod:`audiotrace.core` (currently a stub).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MediaInfo(BaseModel):
    """Metadata about the media file containing the call recording."""

    duration_ms: int
    sample_rate_hz: int
    channels: int
    codec: str
    file_size_bytes: int
    file_format: str
    bitrate_kbps: float


class Turn(BaseModel):
    """A single speaker turn within the transcript."""

    speaker: str
    text: str
    start_ms: int
    end_ms: int


class Transcript(BaseModel):
    full_text: str = ""
    turns: list[Turn] = Field(default_factory=list)
    language: str = "en"


class Gap(BaseModel):
    """A stretch of silence in the call."""

    start_ms: int
    end_ms: int


class Quality(BaseModel):
    overall_score: float = 0.0
    interruptions: int = 0
    silence_gaps: list[Gap] = Field(default_factory=list)
    speaking_pace_wpm: float = 0.0
    pitch_variance: float = 0.0
    turn_length_avg_ms: float = 0.0


class Sentiment(BaseModel):
    by_turn: list[float] = Field(default_factory=list)
    overall: float = 0.0
    shift_points: list[int] = Field(default_factory=list)
    caller_frustration: bool = False


class LatencySpan(BaseModel):
    """One node in the latency waterfall (STT, LLM, TTS, telephony, ...)."""

    name: str
    start_ms: int
    duration_ms: int


class Latency(BaseModel):
    stt_ms: int = 0
    llm_first_token_ms: int = 0
    llm_full_response_ms: int = 0
    tts_ms: int = 0
    total_ms: int = 0
    waterfall: list[LatencySpan] = Field(default_factory=list)


class Cost(BaseModel):
    stt_usd: float = 0.0
    llm_usd: float = 0.0
    tts_usd: float = 0.0
    telephony_usd: float = 0.0
    total_usd: float = 0.0


class Events(BaseModel):
    outcome: str = "completed"
    drop_off: bool = False
    drop_off_turn: int | None = None
    intent_detected: str = ""
    failure_type: str | None = None
    compliance_flags: list[str] = Field(default_factory=list)


class CallReport(BaseModel):
    """The full structured analysis of a single call."""

    media: MediaInfo | None = None
    transcript: Transcript = Field(default_factory=Transcript)
    quality: Quality = Field(default_factory=Quality)
    sentiment: Sentiment = Field(default_factory=Sentiment)
    latency: Latency = Field(default_factory=Latency)
    cost: Cost = Field(default_factory=Cost)
    events: Events = Field(default_factory=Events)
