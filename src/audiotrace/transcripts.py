"""Transcription and speaker diarization logic."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from audiotrace.models import Transcript, Turn, Word

logger = logging.getLogger(__name__)

# Global cache for models to avoid redundant reloads/network checks during a process lifetime
_MODELS: dict[str, Any] = {}

# Default friendly speaker labels used when a speaker count is given but no
# explicit labels are passed. Two speakers map to an agent/customer support call.
DEFAULT_TWO_SPEAKER_LABELS = ("AI Agent", "Customer")

# Pitch range (Hz) for per-segment fundamental-frequency estimation used by the
# no-diarization fallback. Spans typical adult speech (~C2 to C7).
PITCH_FMIN_HZ = 65.0
PITCH_FMAX_HZ = 2093.0


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
    diarize: bool = True,
) -> Transcript:
    """Extract a structured transcript with speaker diarization.

    This uses OpenAI Whisper for transcription and pyannote.audio for diarization.
    All models run locally once weights are downloaded/cached.

    When diarization is unavailable (e.g. no token for the gated model) but
    ``num_speakers`` is given, speakers are inferred by clustering each Whisper
    segment by its voice pitch, so a speaker's consecutive sentences stay grouped
    together rather than alternating per sentence. Raw speaker ids — whether from
    real diarization or this fallback — are mapped to friendly labels in order of
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
        diarize: When False, skip loading the pyannote diarization model and
            infer speakers by pitch instead (useful offline or for a fast demo).

    Returns:
        A populated :class:`~audiotrace.models.Transcript`.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    # 1. Transcription with Whisper (Local execution)
    model = get_whisper_model(whisper_model)
    whisper_result = model.transcribe(str(path), verbose=False, word_timestamps=True)

    full_text = whisper_result.get("text", "").strip()
    language = whisper_result.get("language", "en")
    segments = whisper_result.get("segments", [])

    # 2. Diarization with pyannote.audio (Local execution), unless skipped.
    pipeline = (
        get_diarization_pipeline(diarization_model, use_auth_token=hf_token) if diarize else None
    )

    if pipeline is not None:
        # 3. Alignment: map each Whisper segment to its majority speaker.
        diarization = (
            pipeline(str(path), num_speakers=num_speakers)
            if num_speakers is not None
            else pipeline(str(path))
        )
        turns = [
            _make_turn(seg, _get_majority_speaker(diarization, seg["start"], seg["end"]))
            for seg in segments
        ]
    elif num_speakers:
        # No diarization model: cluster Whisper segments by voice pitch so a
        # speaker's consecutive sentences stay together, then label by role.
        clusters = _cluster_pitches(_segment_pitches(path, segments), num_speakers)
        turns = [
            _make_turn(seg, f"SPEAKER_{cluster:02d}") for seg, cluster in zip(segments, clusters)
        ]
    else:
        # No diarization and no speaker count: speakers are unknown.
        turns = [_make_turn(seg, "unknown") for seg in segments]

    turns = _apply_speaker_roles(turns, num_speakers, speaker_labels)
    return Transcript(full_text=full_text, turns=turns, language=language)


def _make_turn(seg: Any, speaker: str) -> Turn:
    """Build a Turn (with word-level timing and confidence) from a Whisper segment."""
    return Turn(
        speaker=speaker,
        text=seg["text"].strip(),
        start_ms=int(seg["start"] * 1000),
        end_ms=int(seg["end"] * 1000),
        confidence=_segment_confidence(seg),
        words=_segment_words(seg),
    )


def _segment_confidence(seg: Any) -> float:
    """Transcription confidence (0-1) for a segment: mean word probability, or
    exp(avg_logprob) as a fallback."""
    probs = [float(w["probability"]) for w in seg.get("words") or [] if "probability" in w]
    if probs:
        return sum(probs) / len(probs)
    if "avg_logprob" in seg:
        return min(1.0, math.exp(float(seg["avg_logprob"])))
    return 0.0


def _segment_words(seg: Any) -> list[Word]:
    """Extract word-level timings from a Whisper segment (empty if unavailable)."""
    words: list[Word] = []
    for word in seg.get("words") or []:
        words.append(
            Word(
                text=str(word["word"]).strip(),
                start_ms=int(word["start"] * 1000),
                end_ms=int(word["end"] * 1000),
            )
        )
    return words


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


def _segment_pitches(path: Path, segments: Any) -> list[float | None]:
    """Median voiced pitch (Hz) for each Whisper segment, or None if unvoiced."""
    import librosa
    import numpy as np

    y, sr = librosa.load(str(path), sr=None, mono=True)

    pitches: list[float | None] = []
    for seg in segments:
        clip = y[int(seg["start"] * sr) : int(seg["end"] * sr)]
        if clip.size == 0:
            pitches.append(None)
            continue
        f0, voiced_flag, _ = librosa.pyin(clip, fmin=PITCH_FMIN_HZ, fmax=PITCH_FMAX_HZ, sr=sr)
        voiced = f0[voiced_flag] if voiced_flag is not None else f0
        voiced = voiced[~np.isnan(voiced)]
        pitches.append(float(np.median(voiced)) if voiced.size else None)
    return pitches


def _cluster_pitches(pitches: list[float | None], num_speakers: int) -> list[int]:
    """Group segments into ``num_speakers`` clusters by pitch (1-D k-means).

    Segments with no measurable pitch inherit the previous segment's cluster.
    Returns one cluster index per segment.
    """
    valid = [p for p in pitches if p is not None]
    if num_speakers < 2 or len(set(valid)) < 2:
        return [0] * len(pitches)

    centers = _kmeans_1d(valid, min(num_speakers, len(set(valid))))

    clusters: list[int] = []
    last = 0
    for p in pitches:
        if p is not None:
            last = min(range(len(centers)), key=lambda c: abs(p - centers[c]))
        clusters.append(last)
    return clusters


def _kmeans_1d(values: list[float], k: int, iters: int = 25) -> list[float]:
    """Deterministic 1-D k-means returning ``k`` cluster centers."""
    data = sorted(values)
    centers = [data[min(int((i + 0.5) / k * len(data)), len(data) - 1)] for i in range(k)]
    for _ in range(iters):
        buckets: list[list[float]] = [[] for _ in range(k)]
        for v in data:
            buckets[min(range(k), key=lambda c: abs(v - centers[c]))].append(v)
        updated = [sum(b) / len(b) if b else centers[i] for i, b in enumerate(buckets)]
        if updated == centers:
            break
        centers = updated
    return centers


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
