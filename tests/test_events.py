import sys
from unittest.mock import MagicMock, patch

import pytest

from audiotrace.events import (
    DEFAULT_INTENT_LABELS,
    _check_compliance,
    _classify_intent,
    _detect_drop_off,
    clear_model_cache,
    extract_events,
    get_zero_shot_pipeline,
)
from audiotrace.models import Transcript, Turn

mock_transformers = MagicMock()


@pytest.fixture(autouse=True)
def mock_heavy_deps():
    mock_transformers.reset_mock(return_value=True, side_effect=True)
    with patch.dict(sys.modules, {"transformers": mock_transformers}):
        yield
    clear_model_cache()


def _set_intent(label: str) -> MagicMock:
    """Make the mock zero-shot pipeline return ``label`` as the top result."""
    pipe = MagicMock()
    pipe.return_value = {"labels": [label, "other"], "scores": [0.9, 0.1]}
    mock_transformers.pipeline.return_value = pipe
    return pipe


def _turn(speaker: str, text: str, start_ms: int = 0, end_ms: int = 1000) -> Turn:
    return Turn(speaker=speaker, text=text, start_ms=start_ms, end_ms=end_ms)


# --- extract_events: outcome ---


def test_extract_events_empty_transcript_is_failed():
    result = extract_events(Transcript(), duration_ms=1000)
    assert result.outcome == "failed"
    assert result.failure_type == "no_speech"
    assert result.drop_off is False
    assert result.drop_off_turn is None


def test_extract_events_completed():
    _set_intent("billing")
    transcript = Transcript(
        full_text="this call is recorded. agent helps.",
        turns=[
            _turn("agent", "this call is recorded", 0, 1000),
            _turn("caller", "I need help", 1000, 2000),
            _turn("agent", "all set, goodbye", 2000, 3000),
        ],
    )
    result = extract_events(transcript, duration_ms=3000)
    assert result.outcome == "completed"
    assert result.failure_type is None
    assert result.drop_off is False


def test_extract_events_dropped_via_trailing_silence():
    _set_intent("support")
    transcript = Transcript(
        full_text="this is recorded. hello?",
        turns=[
            _turn("agent", "this is recorded", 0, 1000),
            _turn("agent", "hello?", 1000, 2000),
        ],
    )
    # Call is 10s but last speech ends at 2s → 8s trailing silence
    result = extract_events(transcript, duration_ms=10_000)
    assert result.outcome == "dropped"
    assert result.drop_off is True
    assert result.drop_off_turn == 1


# --- _detect_drop_off ---


def test_detect_drop_off_trailing_silence():
    turns = [_turn("agent", "hi", 0, 1000)]
    drop_off, turn_idx = _detect_drop_off(turns, duration_ms=10_000)
    assert drop_off is True
    assert turn_idx == 0


def test_detect_drop_off_caller_last_turn():
    turns = [
        _turn("agent", "hello", 0, 1000),
        _turn("caller", "wait what", 1000, 2000),
    ]
    drop_off, turn_idx = _detect_drop_off(turns, duration_ms=2000)
    assert drop_off is True
    assert turn_idx == 1


def test_detect_drop_off_none_when_clean_ending():
    turns = [
        _turn("caller", "thanks", 0, 1000),
        _turn("agent", "goodbye", 1000, 2000),
    ]
    drop_off, turn_idx = _detect_drop_off(turns, duration_ms=2200)
    assert drop_off is False
    assert turn_idx is None


# --- _classify_intent ---


def test_classify_intent_uses_caller_turns():
    pipe = _set_intent("cancellation")
    transcript = Transcript(
        turns=[
            _turn("agent", "how can I help"),
            _turn("caller", "I want to cancel my plan"),
        ]
    )
    intent = _classify_intent(transcript, DEFAULT_INTENT_LABELS, "model")
    assert intent == "cancellation"
    # Only caller text should be classified
    args, _ = pipe.call_args
    assert args[0] == "I want to cancel my plan"


def test_classify_intent_falls_back_to_full_text():
    pipe = _set_intent("billing")
    transcript = Transcript(
        full_text="some text about a bill",
        turns=[_turn("unknown", "some text about a bill")],
    )
    intent = _classify_intent(transcript, DEFAULT_INTENT_LABELS, "model")
    assert intent == "billing"
    args, _ = pipe.call_args
    assert args[0] == "some text about a bill"


def test_classify_intent_empty_returns_empty_string():
    transcript = Transcript(full_text="", turns=[_turn("unknown", "")])
    intent = _classify_intent(transcript, DEFAULT_INTENT_LABELS, "model")
    assert intent == ""
    mock_transformers.pipeline.assert_not_called()


# --- get_zero_shot_pipeline caching ---


def test_get_zero_shot_pipeline_caches():
    pipe = MagicMock()
    mock_transformers.pipeline.return_value = pipe
    p1 = get_zero_shot_pipeline("m")
    p2 = get_zero_shot_pipeline("m")
    assert p1 is p2
    mock_transformers.pipeline.assert_called_once()


# --- _check_compliance ---


def test_check_compliance_missing_consent():
    transcript = Transcript(full_text="hello how can I help you today")
    flags = _check_compliance(transcript, requires_consent=True)
    assert "missing_consent" in flags


def test_check_compliance_consent_present():
    transcript = Transcript(full_text="this call may be recorded for quality")
    flags = _check_compliance(transcript, requires_consent=True)
    assert "missing_consent" not in flags


def test_check_compliance_consent_not_required():
    transcript = Transcript(full_text="hello there")
    flags = _check_compliance(transcript, requires_consent=False)
    assert "missing_consent" not in flags


def test_check_compliance_pii_ssn():
    transcript = Transcript(full_text="this is recorded. my ssn is 123-45-6789")
    flags = _check_compliance(transcript, requires_consent=True)
    assert "pii_exposed" in flags


def test_check_compliance_pii_email():
    transcript = Transcript(full_text="recorded. email me at john@example.com")
    flags = _check_compliance(transcript, requires_consent=True)
    assert "pii_exposed" in flags


def test_check_compliance_pii_credit_card():
    transcript = Transcript(full_text="recorded. card 4111 1111 1111 1111 please")
    flags = _check_compliance(transcript, requires_consent=True)
    assert "pii_exposed" in flags


def test_check_compliance_clean_call():
    transcript = Transcript(full_text="this call is recorded for quality purposes")
    flags = _check_compliance(transcript, requires_consent=True)
    assert flags == []
