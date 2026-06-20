"""Top-level analysis entry points.

The signal-extraction pipeline (FFmpeg -> Whisper/pyannote/Librosa -> sentiment)
is partially implemented. See docs/prd/0001-core-analyze.md and
docs/prd/0002-transcript.md for the specs.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Union

from audiotrace.cost import PricingTable, extract_cost
from audiotrace.events import extract_events
from audiotrace.extractors import extract_media_info
from audiotrace.latency import extract_waterfall
from audiotrace.models import CallReport, Latency
from audiotrace.quality import extract_quality
from audiotrace.sentiment import extract_sentiment
from audiotrace.transcripts import extract_transcript

AudioInput = Union[str, Path]


def analyze(
    audio: AudioInput,
    metadata: dict[str, object] | None = None,
    hf_token: str | None = None,
    pricing: PricingTable | None = None,
    num_speakers: int | None = None,
    speaker_labels: list[str] | None = None,
) -> CallReport:
    """Analyze a single call recording and return a structured report.

    Args:
        audio: Path to an audio file readable by FFmpeg.
        metadata: Optional call metadata (call_id, agent_version, provider, ...).
        hf_token: Optional HuggingFace token for pyannote.audio diarization.
            If not provided, looks for HF_TOKEN environment variable.
        num_speakers: Expected number of speakers. Enables role labelling even
            when diarization is unavailable (two speakers become "AI Agent" and
            "Customer").
        speaker_labels: Optional custom speaker labels, applied in order of
            appearance instead of the defaults.

    Returns:
        A populated :class:`~audiotrace.models.CallReport`.
    """
    start_time = time.perf_counter()
    token = hf_token or os.environ.get("HF_TOKEN")

    # 1. Media extraction
    media = extract_media_info(audio)

    # 2. Transcription and Diarization (Local Models)
    stt_start = time.perf_counter()
    transcript = extract_transcript(
        audio, hf_token=token, num_speakers=num_speakers, speaker_labels=speaker_labels
    )
    stt_duration_ms = int((time.perf_counter() - stt_start) * 1000)

    # 3. Quality signal extraction (Librosa)
    quality = extract_quality(audio, transcript, media.duration_ms)

    # 4. Sentiment extraction (local Transformers)
    sentiment = extract_sentiment(transcript)

    # 5. Cost attribution
    cost = extract_cost(media, transcript, pricing)

    # 6. Event extraction (outcome, drop-off, intent, compliance)
    events = extract_events(transcript, media.duration_ms)

    total_duration_ms = int((time.perf_counter() - start_time) * 1000)

    latency = Latency(
        stt_ms=stt_duration_ms,
        total_ms=total_duration_ms,
        waterfall=extract_waterfall(transcript),
    )

    return CallReport(
        media=media,
        transcript=transcript,
        quality=quality,
        sentiment=sentiment,
        cost=cost,
        events=events,
        latency=latency,
    )
