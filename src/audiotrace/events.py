"""Call-level event extraction: outcome, drop-off, intent, and compliance."""

from __future__ import annotations

import logging
import re
from typing import Any

from audiotrace.models import Events, Transcript, Turn

logger = logging.getLogger(__name__)

# A trailing silence at least this long marks an abrupt, dropped ending.
DROP_OFF_TRAILING_SILENCE_MS = 5000

# Local zero-shot classifier for caller intent.
INTENT_MODEL = "facebook/bart-large-mnli"
DEFAULT_INTENT_LABELS = (
    "billing",
    "technical support",
    "sales",
    "cancellation",
    "general inquiry",
)

# Substrings that satisfy a recording/consent disclosure.
CONSENT_KEYWORDS = ("record", "recorded", "recording", "consent", "monitored")

# Patterns whose presence in the transcript indicates exposed PII.
_PII_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
    re.compile(r"\b\d(?:[ -]?\d){12,15}\b"),  # 13-16 digit card number
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # email address
)

_MODELS: dict[str, Any] = {}


def clear_model_cache() -> None:
    """Clear the global model cache."""
    _MODELS.clear()


def get_zero_shot_pipeline(model_name: str = INTENT_MODEL) -> Any:
    """Load and cache a HuggingFace zero-shot-classification pipeline."""
    from transformers import pipeline

    if model_name not in _MODELS:
        logger.info("Loading intent model: %s", model_name)
        _MODELS[model_name] = pipeline("zero-shot-classification", model=model_name)
    return _MODELS[model_name]


def extract_events(
    transcript: Transcript,
    duration_ms: int,
    intent_labels: tuple[str, ...] = DEFAULT_INTENT_LABELS,
    requires_consent: bool = True,
    model_name: str = INTENT_MODEL,
) -> Events:
    """Derive call-level outcome signals from the transcript and audio.

    Intent classification runs locally via a cached zero-shot model; all other
    signals are rule-based over the transcript. Works fully offline after the
    intent model's first download.

    Args:
        transcript: The transcript produced by extract_transcript().
        duration_ms: Total duration of the call, from MediaInfo.
        intent_labels: Candidate intent labels for zero-shot classification.
        requires_consent: When True, flag calls lacking a consent disclosure.
        model_name: HuggingFace model identifier for intent classification.

    Returns:
        A populated :class:`~audiotrace.models.Events`.
    """
    if not transcript.turns:
        return Events(outcome="failed", failure_type="no_speech")

    drop_off, drop_off_turn = _detect_drop_off(transcript.turns, duration_ms)
    outcome = "dropped" if drop_off else "completed"
    intent = _classify_intent(transcript, intent_labels, model_name)
    compliance_flags = _check_compliance(transcript, requires_consent)

    return Events(
        outcome=outcome,
        drop_off=drop_off,
        drop_off_turn=drop_off_turn,
        intent_detected=intent,
        failure_type=None,
        compliance_flags=compliance_flags,
    )


def _detect_drop_off(turns: list[Turn], duration_ms: int) -> tuple[bool, int | None]:
    """Detect an abrupt ending: long trailing silence or a caller with no reply."""
    last_index = len(turns) - 1
    last = turns[last_index]

    if duration_ms - last.end_ms >= DROP_OFF_TRAILING_SILENCE_MS:
        return True, last_index
    if last.speaker == "caller":
        return True, last_index
    return False, None


def _classify_intent(
    transcript: Transcript,
    labels: tuple[str, ...],
    model_name: str,
) -> str:
    """Classify caller intent with a local zero-shot model, or "" when no text."""
    caller_text = " ".join(t.text for t in transcript.turns if t.speaker == "caller").strip()
    if not caller_text:
        caller_text = transcript.full_text.strip()
    if not caller_text:
        return ""

    pipe = get_zero_shot_pipeline(model_name)
    result = pipe(caller_text, list(labels))
    return str(result["labels"][0])


def _check_compliance(transcript: Transcript, requires_consent: bool) -> list[str]:
    """Flag a missing consent disclosure and any exposed PII in the transcript."""
    flags: list[str] = []

    text_lower = transcript.full_text.lower()
    if requires_consent and not any(k in text_lower for k in CONSENT_KEYWORDS):
        flags.append("missing_consent")

    if any(pattern.search(transcript.full_text) for pattern in _PII_PATTERNS):
        flags.append("pii_exposed")

    return flags
