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

from audiotrace.extractors import extract_media_info
from audiotrace.models import CallReport, Latency
from audiotrace.quality import extract_quality
from audiotrace.transcripts import extract_transcript

AudioInput = Union[str, Path]


def analyze(
    audio: AudioInput,
    metadata: dict[str, object] | None = None,
    hf_token: str | None = None,
) -> CallReport:
    """Analyze a single call recording and return a structured report.

    Args:
        audio: Path to an audio file readable by FFmpeg.
        metadata: Optional call metadata (call_id, agent_version, provider, ...).
        hf_token: Optional HuggingFace token for pyannote.audio diarization.
            If not provided, looks for HF_TOKEN environment variable.

    Returns:
        A populated :class:`~audiotrace.models.CallReport`.
    """
    start_time = time.perf_counter()
    token = hf_token or os.environ.get("HF_TOKEN")

    # 1. Media extraction
    media = extract_media_info(audio)

    # 2. Transcription and Diarization (Local Models)
    stt_start = time.perf_counter()
    transcript = extract_transcript(audio, hf_token=token)
    stt_duration_ms = int((time.perf_counter() - stt_start) * 1000)

    # 3. Quality signal extraction (Librosa)
    quality = extract_quality(audio, transcript, media.duration_ms)

    total_duration_ms = int((time.perf_counter() - start_time) * 1000)

    latency = Latency(
        stt_ms=stt_duration_ms,
        total_ms=total_duration_ms,
    )

    return CallReport(
        media=media,
        transcript=transcript,
        quality=quality,
        latency=latency,
    )
