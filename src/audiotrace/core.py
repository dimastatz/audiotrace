"""Top-level analysis entry points.

The signal-extraction pipeline (FFmpeg -> Whisper/pyannote/Librosa -> sentiment)
is not implemented yet. See docs/prd/0001-core-analyze.md for the spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from audiotrace.extractors import extract_media_info
from audiotrace.models import CallReport

AudioInput = Union[str, Path]


def analyze(
    audio: AudioInput,
    metadata: dict[str, object] | None = None,
) -> CallReport:
    """Analyze a single call recording and return a structured report.

    Args:
        audio: Path to an audio file readable by FFmpeg.
        metadata: Optional call metadata (call_id, agent_version, provider, ...).

    Returns:
        A populated :class:`~audiotrace.models.CallReport`.
    """
    media = extract_media_info(audio)
    return CallReport(media=media)


def batch(
    audio_files: list[AudioInput],
    concurrency: int = 10,
) -> list[CallReport]:
    """Analyze many recordings concurrently.
    ...

        Args:
            audio_files: Audio file paths to analyze.
            concurrency: Maximum number of concurrent analyses.

        Returns:
            One :class:`~audiotrace.models.CallReport` per input, in order.
    """
    raise NotImplementedError(
        "audiotrace.batch is not implemented yet — see docs/prd/0001-core-analyze.md"
    )
