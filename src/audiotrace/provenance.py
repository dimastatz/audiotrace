"""Extraction-stack provenance (PRD 0009 Part A).

Records which models and library versions produced a :class:`CallReport`, and
compares two reports' stacks so a metric move that coincides with a stack
change reads as *measurement changed*, not as a silent agent regression.

Pure standard library + the existing models; no new dependencies.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from importlib import metadata

from audiotrace.events import INTENT_MODEL
from audiotrace.models import CallReport, Provenance
from audiotrace.sentiment import SENTIMENT_MODEL
from audiotrace.transcripts import WHISPER_MODEL

# Provenance field -> installed distribution whose version it records.
# AudioTrace's own version comes from ``__version__`` instead: an editable
# install's metadata goes stale until it is reinstalled.
_PACKAGES = {
    "whisper_version": "openai-whisper",
    "pyannote_version": "pyannote.audio",
    "librosa_version": "librosa",
    "transformers_version": "transformers",
    "torch_version": "torch",
}


@dataclass(frozen=True)
class ProvenanceChange:
    """One extraction-stack field that differs between baseline and current."""

    field: str
    before: str
    after: str


def collect_provenance(diarization: str, whisper_model: str = WHISPER_MODEL) -> Provenance:
    """Snapshot the extraction stack in this process.

    Args:
        diarization: The diarization path actually taken (see
            :func:`audiotrace.transcripts.diarization_method`).
        whisper_model: The Whisper model name used for transcription.
    """
    from audiotrace import __version__  # deferred: the package imports this module

    versions = {name: _version(dist) for name, dist in _PACKAGES.items()}
    return Provenance(
        audiotrace_version=__version__,
        whisper_model=whisper_model,
        diarization=diarization,
        sentiment_model=SENTIMENT_MODEL,
        intent_model=INTENT_MODEL,
        python_version=platform.python_version(),
        **versions,
    )


def provenance_changes(baseline: CallReport, current: CallReport) -> list[ProvenanceChange]:
    """List the extraction-stack fields that differ between two reports.

    A report without provenance (produced before it was recorded) counts as an
    unknown stack: comparing it against a recorded one is itself a change.
    """
    before, after = baseline.provenance, current.provenance
    if before is None and after is None:
        return []
    if before is None or after is None:
        return [
            ProvenanceChange(
                "provenance",
                "unrecorded" if before is None else "recorded",
                "unrecorded" if after is None else "recorded",
            )
        ]
    old, new = before.model_dump(), after.model_dump()
    return [ProvenanceChange(key, old[key], new[key]) for key in old if old[key] != new[key]]


def _version(dist: str) -> str:
    """The installed version of ``dist``, or "" when it isn't installed."""
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return ""
