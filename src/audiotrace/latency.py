"""Agent-response latency waterfall derived from diarized turn timestamps."""

from __future__ import annotations

from audiotrace.models import LatencySpan, Transcript

# Gaps at or below this many milliseconds are conversational micro-pauses (or
# overlapping barge-in, i.e. a negative gap) rather than agent response latency,
# and are omitted from the waterfall.
RESPONSE_NOISE_FLOOR_MS = 250


def extract_waterfall(transcript: Transcript) -> list[LatencySpan]:
    """Build the agent-response latency waterfall from diarized turns.

    For every caller turn immediately followed by an agent turn, emit one
    ``LatencySpan`` measuring the silence before the agent replied. Derived
    purely from turn timestamps — no audio re-processing or provider metadata.

    Args:
        transcript: The transcript produced by extract_transcript().

    Returns:
        Chronologically ordered list of ``"agent_response"`` spans. Empty when
        speakers are unlabeled (``"unknown"``) or no qualifying gap exists.
    """
    spans: list[LatencySpan] = []
    for caller, agent in zip(transcript.turns, transcript.turns[1:]):
        if caller.speaker != "caller" or agent.speaker != "agent":
            continue
        gap_ms = agent.start_ms - caller.end_ms
        if gap_ms <= RESPONSE_NOISE_FLOOR_MS:
            continue
        spans.append(
            LatencySpan(
                name="agent_response",
                start_ms=caller.end_ms,
                duration_ms=gap_ms,
            )
        )
    return spans
