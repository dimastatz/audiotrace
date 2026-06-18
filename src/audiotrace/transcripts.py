"""Transcription and speaker diarization logic."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from audiotrace.models import Transcript, Turn

logger = logging.getLogger(__name__)

# Global cache for models to avoid redundant reloads/network checks during a process lifetime
_MODELS: dict[str, Any] = {}


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
) -> Transcript:
    """Extract a structured transcript with speaker diarization.

    This uses OpenAI Whisper for transcription and pyannote.audio for diarization.
    All models run locally once weights are downloaded/cached.

    Args:
        audio_path: Path to the audio file.
        hf_token: Optional HuggingFace token for pyannote.audio gated models.
        whisper_model: Name or path of the Whisper model to use.
        diarization_model: Name or path of the pyannote pipeline to use.

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

    # Run diarization
    if pipeline is not None:
        diarization = pipeline(str(path))

        # 3. Alignment: map Whisper segments to Pyannote speaker turns
        turns: list[Turn] = []
        for segment in segments:
            start = segment["start"]
            end = segment["end"]
            text = segment["text"].strip()

            # Find the majority speaker for this segment
            speaker = _get_majority_speaker(diarization, start, end)

            turns.append(
                Turn(
                    speaker=speaker,
                    text=text,
                    start_ms=int(start * 1000),
                    end_ms=int(end * 1000),
                )
            )

        return Transcript(full_text=full_text, turns=turns, language=language)

    # Fallback if pipeline couldn't be loaded
    turns = [
        Turn(
            speaker="unknown",
            text=segment["text"].strip(),
            start_ms=int(segment["start"] * 1000),
            end_ms=int(segment["end"] * 1000),
        )
        for segment in segments
    ]
    return Transcript(full_text=full_text, turns=turns, language=language)


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
