"""AudioTrace — structured analysis for voice-agent call recordings.

Public API:
    >>> import audiotrace
    >>> report = audiotrace.analyze("call.wav", metadata={"provider": "vapi"})

The extraction pipeline is not implemented yet; the data contract
(:class:`CallReport` and friends) is stable and lives in ``audiotrace.models``.
"""

from audiotrace.core import analyze
from audiotrace.cost import PricingTable
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
    Word,
)
from audiotrace.report import (
    Delta,
    Metric,
    diff,
    render_html,
    render_json,
    summarize,
    write_report,
)

__version__ = "1.1.1"

__all__ = [
    "analyze",
    "PricingTable",
    "summarize",
    "diff",
    "render_json",
    "render_html",
    "write_report",
    "Metric",
    "Delta",
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
    "Word",
    "__version__",
]
