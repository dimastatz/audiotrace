"""AudioTrace — structured analysis for voice-agent call recordings.

Public API:
    >>> import audiotrace
    >>> report = audiotrace.analyze("call.wav", metadata={"provider": "vapi"})

The extraction pipeline is not implemented yet; the data contract
(:class:`CallReport` and friends) is stable and lives in ``audiotrace.models``.
"""

from audiotrace.core import analyze, batch
from audiotrace.models import (
    CallReport,
    Cost,
    Events,
    Gap,
    Latency,
    LatencySpan,
    MediaInfo,
    Quality,
    Sentiment,
    Transcript,
    Turn,
)

__version__ = "0.1.0"

__all__ = [
    "analyze",
    "batch",
    "CallReport",
    "Cost",
    "Events",
    "Gap",
    "Latency",
    "LatencySpan",
    "MediaInfo",
    "Quality",
    "Sentiment",
    "Transcript",
    "Turn",
    "__version__",
]
