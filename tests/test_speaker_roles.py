"""The extractors must agree on who the agent and caller are, whatever the labels.

Regression tests for the two-speaker default ("AI Agent" / "Customer", what the
CLI and GitHub Action produce): latency, frustration, drop-off, intent, cost,
and the report all used to look for "agent" / "caller" only.
"""

from unittest.mock import MagicMock, patch

import pytest

from audiotrace.cost import _speaker_char_counts
from audiotrace.events import _classify_intent, _detect_drop_off
from audiotrace.latency import extract_waterfall
from audiotrace.models import Transcript, Turn
from audiotrace.report import _bubble
from audiotrace.sentiment import _detect_caller_frustration
from audiotrace.transcripts import DEFAULT_TWO_SPEAKER_LABELS, speaker_role

AGENT, CALLER = DEFAULT_TWO_SPEAKER_LABELS


@pytest.mark.parametrize(
    "label, role",
    [
        ("agent", "agent"),
        ("AI Agent", "agent"),
        ("Assistant", "agent"),
        ("bot", "agent"),
        ("caller", "caller"),
        (" Customer ", "caller"),
        ("user", "caller"),
        ("SPEAKER_00", None),
        ("unknown", None),
        ("", None),
    ],
)
def test_speaker_role(label, role):
    assert speaker_role(label) == role


def _turn(speaker, text="words here", start_ms=0, end_ms=1000):
    return Turn(speaker=speaker, text=text, start_ms=start_ms, end_ms=end_ms)


def test_latency_waterfall_with_default_labels():
    transcript = Transcript(
        turns=[
            _turn(AGENT, end_ms=1000),
            _turn(CALLER, start_ms=1200, end_ms=2000),
            _turn(AGENT, start_ms=3500, end_ms=4000),
        ]
    )
    spans = extract_waterfall(transcript)
    assert [(s.start_ms, s.duration_ms) for s in spans] == [(2000, 1500)]


def test_frustration_with_default_labels():
    turns = [_turn(CALLER), _turn(CALLER), _turn(AGENT)]
    assert _detect_caller_frustration(turns, [-0.9, -0.9, 0.0])


def test_drop_off_when_customer_speaks_last():
    assert _detect_drop_off([_turn(AGENT), _turn(CALLER)], duration_ms=1000) == (True, 1)
    assert _detect_drop_off([_turn(CALLER), _turn(AGENT)], duration_ms=1000) == (False, None)


def test_intent_uses_only_customer_turns():
    pipe = MagicMock(return_value={"labels": ["billing"]})
    transcript = Transcript(
        full_text="agent text customer text",
        turns=[_turn(AGENT, "agent text"), _turn(CALLER, "customer text")],
    )
    with patch("audiotrace.events.get_zero_shot_pipeline", return_value=pipe):
        assert _classify_intent(transcript, ("billing",), "model") == "billing"
    assert pipe.call_args.args[0] == "customer text"


def test_cost_split_with_default_labels():
    transcript = Transcript(turns=[_turn(AGENT, "a" * 30), _turn(CALLER, "c" * 10)])
    assert _speaker_char_counts(transcript) == (30, 10)


def test_report_bubbles_by_role():
    assert 'class="bubble agent"' in _bubble(_turn(AGENT))
    assert 'class="bubble caller"' in _bubble(_turn(CALLER))
    assert 'class="bubble caller"' in _bubble(_turn("SPEAKER_01"))
