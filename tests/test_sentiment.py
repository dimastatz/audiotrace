import sys
from unittest.mock import MagicMock, patch

import pytest

from audiotrace.models import Sentiment, Transcript, Turn
from audiotrace.sentiment import (
    _detect_caller_frustration,
    _find_shift_points,
    clear_model_cache,
    extract_sentiment,
    get_sentiment_pipeline,
)

mock_transformers = MagicMock()


@pytest.fixture(autouse=True)
def mock_heavy_deps():
    mock_transformers.reset_mock(return_value=True, side_effect=True)
    with patch.dict(sys.modules, {"transformers": mock_transformers}):
        yield
    clear_model_cache()


def _make_pipe(*labels_and_scores: tuple[str, float]) -> MagicMock:
    """Return a mock pipeline callable that produces the given results."""
    pipe = MagicMock()
    pipe.return_value = [{"label": lbl, "score": sc} for lbl, sc in labels_and_scores]
    mock_transformers.pipeline.return_value = pipe
    return pipe


def _turns(*texts: str, speaker: str = "agent") -> list[Turn]:
    return [
        Turn(speaker=speaker, text=t, start_ms=i * 1000, end_ms=(i + 1) * 1000)
        for i, t in enumerate(texts)
    ]


# --- extract_sentiment ---


def test_extract_sentiment_empty_transcript():
    result = extract_sentiment(Transcript())
    assert result == Sentiment()


def test_extract_sentiment_positive_turn():
    _make_pipe(("POSITIVE", 0.9))
    transcript = Transcript(turns=_turns("great call"))
    result = extract_sentiment(transcript)
    assert result.by_turn == pytest.approx([0.9])
    assert result.overall == pytest.approx(0.9)
    assert result.shift_points == []
    assert result.caller_frustration is False


def test_extract_sentiment_negative_turn():
    _make_pipe(("NEGATIVE", 0.8))
    transcript = Transcript(turns=_turns("terrible service"))
    result = extract_sentiment(transcript)
    assert result.by_turn == pytest.approx([-0.8])
    assert result.overall == pytest.approx(-0.8)


def test_extract_sentiment_by_turn_length_matches_turns():
    _make_pipe(("POSITIVE", 0.7), ("NEGATIVE", 0.6), ("POSITIVE", 0.5))
    turns = _turns("good", "bad", "okay")
    result = extract_sentiment(Transcript(turns=turns))
    assert len(result.by_turn) == 3


def test_extract_sentiment_overall_is_mean():
    _make_pipe(("POSITIVE", 0.8), ("NEGATIVE", 0.4))
    turns = _turns("good", "bad")
    result = extract_sentiment(Transcript(turns=turns))
    assert result.overall == pytest.approx((0.8 + -0.4) / 2)


# --- get_sentiment_pipeline (caching) ---


def test_get_sentiment_pipeline_caches_model():
    pipe = MagicMock()
    mock_transformers.pipeline.return_value = pipe

    p1 = get_sentiment_pipeline("some-model")
    p2 = get_sentiment_pipeline("some-model")

    assert p1 is p2
    mock_transformers.pipeline.assert_called_once()


def test_get_sentiment_pipeline_different_models_load_separately():
    mock_transformers.pipeline.side_effect = lambda *a, **kw: MagicMock()

    p1 = get_sentiment_pipeline("model-a")
    p2 = get_sentiment_pipeline("model-b")

    assert p1 is not p2
    assert mock_transformers.pipeline.call_count == 2


# --- _find_shift_points ---


def test_find_shift_points_no_shifts():
    assert _find_shift_points([0.5, 0.6, 0.55]) == []


def test_find_shift_points_single_score():
    assert _find_shift_points([0.9]) == []


def test_find_shift_points_detects_shift():
    # 0.9 → -0.9: delta = 1.8 > 0.4
    assert _find_shift_points([0.9, -0.9]) == [1]


def test_find_shift_points_multiple_shifts():
    scores = [0.9, -0.9, 0.8, -0.8]
    assert _find_shift_points(scores) == [1, 2, 3]


def test_find_shift_points_exactly_at_threshold_not_included():
    # delta == 0.4 → not strictly greater, should not appear
    assert _find_shift_points([0.0, 0.4]) == []


def test_find_shift_points_just_above_threshold_included():
    assert _find_shift_points([0.0, 0.41]) == [1]


# --- _detect_caller_frustration ---


def test_detect_caller_frustration_no_callers():
    turns = _turns("hello", "hi", speaker="agent")
    scores = [-0.9, -0.9]
    assert _detect_caller_frustration(turns, scores) is False


def test_detect_caller_frustration_single_negative_caller():
    turns = [Turn(speaker="caller", text="bad", start_ms=0, end_ms=1000)]
    assert _detect_caller_frustration(turns, [-0.9]) is False


def test_detect_caller_frustration_two_consecutive_triggers():
    turns = [
        Turn(speaker="caller", text="a", start_ms=0, end_ms=1000),
        Turn(speaker="caller", text="b", start_ms=1000, end_ms=2000),
    ]
    assert _detect_caller_frustration(turns, [-0.5, -0.5]) is True


def test_detect_caller_frustration_agent_turns_do_not_reset_counter():
    turns = [
        Turn(speaker="caller", text="a", start_ms=0, end_ms=1000),
        Turn(speaker="agent", text="x", start_ms=1000, end_ms=2000),
        Turn(speaker="caller", text="b", start_ms=2000, end_ms=3000),
    ]
    scores = [-0.5, 0.9, -0.5]
    # agent turn should not reset consecutive caller count
    assert _detect_caller_frustration(turns, scores) is True


def test_detect_caller_frustration_resets_on_positive_caller_turn():
    turns = [
        Turn(speaker="caller", text="a", start_ms=0, end_ms=1000),
        Turn(speaker="caller", text="b", start_ms=1000, end_ms=2000),
        Turn(speaker="caller", text="c", start_ms=2000, end_ms=3000),
    ]
    scores = [-0.5, 0.8, -0.5]
    # positive turn in the middle resets the streak
    assert _detect_caller_frustration(turns, scores) is False


def test_detect_caller_frustration_at_threshold_not_triggered():
    # score == -0.3 → not strictly less than threshold
    turns = [
        Turn(speaker="caller", text="a", start_ms=0, end_ms=1000),
        Turn(speaker="caller", text="b", start_ms=1000, end_ms=2000),
    ]
    assert _detect_caller_frustration(turns, [-0.3, -0.3]) is False
