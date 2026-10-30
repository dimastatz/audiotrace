"""Call-level event extraction: outcome, drop-off, intent, and compliance."""

from __future__ import annotations

import logging
from typing import Any

from audiotrace.compliance import (
    CompliancePolicy,
    compliance_flags,
    find_compliance_issues,
)
from audiotrace.models import Events, Transcript, Turn
from audiotrace.transcripts import speaker_role

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
    compliance_policy: CompliancePolicy | None = None,
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
            Ignored when ``compliance_policy`` is given.
        model_name: HuggingFace model identifier for intent classification.
        compliance_policy: Consent and PII rules (see :mod:`audiotrace.compliance`).

    Returns:
        A populated :class:`~audiotrace.models.Events`.
    """
    if not transcript.turns:
        return Events(outcome="failed", failure_type="no_speech")

    drop_off, drop_off_turn = _detect_drop_off(transcript.turns, duration_ms)
    outcome = "dropped" if drop_off else "completed"
    intent = _classify_intent(transcript, intent_labels, model_name)
    policy = compliance_policy or CompliancePolicy(requires_consent=requires_consent)
    findings = find_compliance_issues(transcript, policy)

    return Events(
        outcome=outcome,
        drop_off=drop_off,
        drop_off_turn=drop_off_turn,
        intent_detected=intent,
        failure_type=None,
        compliance_flags=compliance_flags(findings),
        compliance_findings=findings,
    )


def _detect_drop_off(turns: list[Turn], duration_ms: int) -> tuple[bool, int | None]:
    """Detect an abrupt ending: long trailing silence or a caller with no reply."""
    last_index = len(turns) - 1
    last = turns[last_index]

    if duration_ms - last.end_ms >= DROP_OFF_TRAILING_SILENCE_MS:
        return True, last_index
    if speaker_role(last.speaker) == "caller":
        return True, last_index
    return False, None


def _classify_intent(
    transcript: Transcript,
    labels: tuple[str, ...],
    model_name: str,
) -> str:
    """Classify caller intent with a local zero-shot model, or "" when no text."""
    caller_text = " ".join(
        t.text for t in transcript.turns if speaker_role(t.speaker) == "caller"
    ).strip()
    if not caller_text:
        caller_text = transcript.full_text.strip()
    if not caller_text:
        return ""

    pipe = get_zero_shot_pipeline(model_name)
    result = pipe(caller_text, list(labels))
    return str(result["labels"][0])
