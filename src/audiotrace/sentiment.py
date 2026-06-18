"""Sentiment extraction using a local HuggingFace Transformers model."""

from __future__ import annotations

import logging
from typing import Any

from audiotrace.models import Sentiment, Transcript, Turn

logger = logging.getLogger(__name__)

SENTIMENT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"
SHIFT_THRESHOLD = 0.4
FRUSTRATION_THRESHOLD = -0.3
FRUSTRATION_CONSECUTIVE = 2

_MODELS: dict[str, Any] = {}


def clear_model_cache() -> None:
    """Clear the global model cache."""
    _MODELS.clear()


def get_sentiment_pipeline(model_name: str = SENTIMENT_MODEL) -> Any:
    """Load and cache a HuggingFace sentiment-analysis pipeline."""
    from transformers import pipeline  # type: ignore

    if model_name not in _MODELS:
        logger.info("Loading sentiment model: %s", model_name)
        _MODELS[model_name] = pipeline("sentiment-analysis", model=model_name)
    return _MODELS[model_name]


def extract_sentiment(
    transcript: Transcript,
    model_name: str = SENTIMENT_MODEL,
) -> Sentiment:
    """Extract per-turn sentiment, overall score, shift points, and frustration flag.

    All inference runs locally using a cached HuggingFace pipeline. Models are
    downloaded on first use and served from disk on subsequent calls.

    Args:
        transcript: The transcript produced by extract_transcript().
        model_name: HuggingFace model identifier for sentiment analysis.

    Returns:
        A populated :class:`~audiotrace.models.Sentiment`.
    """
    if not transcript.turns:
        return Sentiment()

    pipe = get_sentiment_pipeline(model_name)
    texts = [t.text for t in transcript.turns]
    results = pipe(texts, truncation=True, max_length=512)

    by_turn = [r["score"] if r["label"] == "POSITIVE" else -r["score"] for r in results]

    overall = sum(by_turn) / len(by_turn)
    shift_points = _find_shift_points(by_turn)
    caller_frustration = _detect_caller_frustration(transcript.turns, by_turn)

    return Sentiment(
        by_turn=by_turn,
        overall=overall,
        shift_points=shift_points,
        caller_frustration=caller_frustration,
    )


def _find_shift_points(scores: list[float]) -> list[int]:
    """Return turn indices where sentiment changes by more than SHIFT_THRESHOLD."""
    return [i for i in range(1, len(scores)) if abs(scores[i] - scores[i - 1]) > SHIFT_THRESHOLD]


def _detect_caller_frustration(turns: list[Turn], scores: list[float]) -> bool:
    """Return True when caller has FRUSTRATION_CONSECUTIVE consecutive negative turns."""
    consecutive = 0
    for turn, score in zip(turns, scores):
        if turn.speaker != "caller":
            continue
        if score < FRUSTRATION_THRESHOLD:
            consecutive += 1
            if consecutive >= FRUSTRATION_CONSECUTIVE:
                return True
        else:
            consecutive = 0
    return False
