"""Transcription and speaker diarization logic."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from audiotrace.models import Transcript, Turn

logger = logging.getLogger(__name__)

# Global cache for models to avoid redundant reloads/network checks during a process lifetime
_MODELS: dict[str, Any] = {}

# Default friendly speaker labels used when a speaker count is given but no
# explicit labels are passed. Two speakers map to an agent/customer support call.
DEFAULT_TWO_SPEAKER_LABELS = ("AI Agent", "Customer")


def clear_model_cache() -> None:
    """Clear the global model cache."""
    _MODELS.clear()


def get_whisper_model(model_name: str = "base", device: str | None = None) -> Any:
    """Load and cache a Whisper model."""
    import whisper  # type: ignore

    key = f"whisper:{model_name}:{device}"
    if key not in _MODELS:
        logger.info(f"Loading Whisper model: {model_name}")
        _MODELS[key] = whisper.load_model(model_name, device=device)
    return _MODELS[key]


def get_diarization_pipeline(
    model_name: str = "pyannote/speaker-diarization-3.1",
    use_auth_token: str | None = None,
) -> Any:
    """Load and cache a pyannote.audio diarization pipeline."""
    from pyannote.audio import Pipeline

    key = f"pyannote:{model_name}"
    if key not in _MODELS:
        try:
            # Note: from_pretrained checks local cache first.
            # Passing use_auth_token is required for gated models on first download.
            logger.info(f"Loading diarization pipeline: {model_name}")
            pipeline = Pipeline.from_pretrained(model_name, token=use_auth_token)
            if pipeline is not None:
                _MODELS[key] = pipeline
            else:
                return None
        except Exception as e:
            logger.warning(f"Could not load diarization pipeline {model_name}: {e}")
            return None
    return _MODELS[key]


def extract_transcript(
    audio_path: str | Path,
    hf_token: str | None = None,
    whisper_model: str = "base",
    diarization_model: str = "pyannote/speaker-diarization-3.1",
    num_speakers: int | None = None,
    speaker_labels: list[str] | None = None,
) -> Transcript:
    """Extract a structured transcript with speaker diarization.

    This uses OpenAI Whisper for transcription and pyannote.audio for diarization.
    All models run locally once weights are downloaded/cached.

    When diarization is unavailable (e.g. no token for the gated model) but
    ``num_speakers`` is given, speakers are assumed to alternate turn by turn so
    that role labels can still be assigned. Raw speaker ids — whether from real
    diarization or this fallback — are mapped to friendly labels in order of
    first appearance: ``speaker_labels`` if provided, otherwise the defaults
    (two speakers become "AI Agent" then "Customer").

    Args:
        audio_path: Path to the audio file.
        hf_token: Optional HuggingFace token for pyannote.audio gated models.
        whisper_model: Name or path of the Whisper model to use.
        diarization_model: Name or path of the pyannote pipeline to use.
        num_speakers: Expected number of speakers. Improves real diarization and
            enables role labelling when diarization is unavailable.
        speaker_labels: Optional custom labels to apply in order of appearance.

    Returns:
        A populated :class:`~audiotrace.models.Transcript`.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    # 1. Transcription with Whisper (Local execution)
    model = get_whisper_model(whisper_model)
    whisper_result = model.transcribe(str(path), verbose=False)

    full_text = whisper_result.get("text", "").strip()
    language = whisper_result.get("language", "en")
    segments = whisper_result.get("segments", [])

    # 2. Diarization with pyannote.audio (Local execution)
    pipeline = get_diarization_pipeline(diarization_model, use_auth_token=hf_token)

    if pipeline is not None:
        # 3. Alignment: map each Whisper segment to its majority speaker.
        diarization = (
            pipeline(str(path), num_speakers=num_speakers)
            if num_speakers is not None
            else pipeline(str(path))
        )
        turns = [
            Turn(
                speaker=_get_majority_speaker(diarization, seg["start"], seg["end"]),
                text=seg["text"].strip(),
                start_ms=int(seg["start"] * 1000),
                end_ms=int(seg["end"] * 1000),
            )
            for seg in segments
        ]
    else:
        # Fallback: with a known speaker count, assume speakers alternate turn by
        # turn; otherwise the speaker is unknown.
        turns = [
            Turn(
                speaker=(f"SPEAKER_{i % num_speakers:02d}" if num_speakers else "unknown"),
                text=seg["text"].strip(),
                start_ms=int(seg["start"] * 1000),
                end_ms=int(seg["end"] * 1000),
            )
            for i, seg in enumerate(segments)
        ]

    turns = _apply_speaker_roles(turns, num_speakers, speaker_labels)
    return Transcript(full_text=full_text, turns=turns, language=language)


def _default_role_labels(num_speakers: int) -> list[str]:
    """Default friendly labels for a known speaker count."""
    if num_speakers == 2:
        return list(DEFAULT_TWO_SPEAKER_LABELS)
    return [f"Speaker {i + 1}" for i in range(num_speakers)]


def _apply_speaker_roles(
    turns: list[Turn],
    num_speakers: int | None,
    speaker_labels: list[str] | None,
) -> list[Turn]:
    """Relabel raw diarization speakers with friendly role names.

    Raw speakers are mapped to labels in order of first appearance, cycling if
    there are more distinct speakers than labels. With no custom labels and no
    speaker count, turns are returned unchanged (raw ids preserved).
    """
    if speaker_labels:
        labels = speaker_labels
    elif num_speakers is not None:
        labels = _default_role_labels(num_speakers)
    else:
        return turns

    if not labels:
        return turns

    mapping: dict[str, str] = {}
    for turn in turns:
        if turn.speaker not in mapping:
            mapping[turn.speaker] = labels[len(mapping) % len(labels)]

    return [turn.model_copy(update={"speaker": mapping[turn.speaker]}) for turn in turns]


def _get_majority_speaker(diarization: Any, start: float, end: float) -> str:
    """Identify the speaker who talked the most during a given time range."""
    from pyannote.core import Segment  # type: ignore

    query = Segment(start, end)
    speakers = diarization.crop(query).labels()

    if not speakers:
        return "unknown"

    # Count duration for each speaker in the range
    speaker_durations: dict[str, float] = {}
    for segment, _, speaker in diarization.crop(query).itertracks(yield_label=True):
        intersection = segment & query
        speaker_durations[speaker] = speaker_durations.get(speaker, 0) + intersection.duration

    if not speaker_durations:
        return "unknown"

    return max(speaker_durations, key=speaker_durations.get)  # type: ignore
