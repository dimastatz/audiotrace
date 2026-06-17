"""Quality signal extraction: silence gaps, interruptions, pace, and pitch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audiotrace.models import Gap, Quality, Transcript, Turn

SILENCE_THRESHOLD_MS = 2000
SILENCE_TOP_DB = 30.0
IDEAL_WPM_LOW = 110.0
IDEAL_WPM_HIGH = 170.0
LOW_PITCH_VARIANCE_HZ = 5.0


def extract_quality(
    audio_path: str | Path,
    transcript: Transcript,
    duration_ms: int,
) -> Quality:
    """Extract conversational and acoustic quality signals for a call.

    Args:
        audio_path: Path to the audio file.
        transcript: The transcript produced by :func:`audiotrace.transcripts.extract_transcript`.
        duration_ms: Total duration of the call, from :class:`~audiotrace.models.MediaInfo`.

    Returns:
        A populated :class:`~audiotrace.models.Quality`.

    Raises:
        FileNotFoundError: If the audio file does not exist.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    import librosa

    y, sr = librosa.load(str(path), sr=None, mono=True)

    silence_gaps = _detect_silence_gaps(y, sr, duration_ms)
    interruptions = _count_interruptions(transcript.turns)
    speaking_pace_wpm = _speaking_pace_wpm(transcript.full_text, duration_ms)
    pitch_variance = _pitch_variance(y, sr)
    turn_length_avg_ms = _avg_turn_length_ms(transcript.turns)

    overall_score = _score_quality(
        duration_ms=duration_ms,
        silence_gaps=silence_gaps,
        interruptions=interruptions,
        speaking_pace_wpm=speaking_pace_wpm,
        pitch_variance=pitch_variance,
    )

    return Quality(
        overall_score=overall_score,
        interruptions=interruptions,
        silence_gaps=silence_gaps,
        speaking_pace_wpm=speaking_pace_wpm,
        pitch_variance=pitch_variance,
        turn_length_avg_ms=turn_length_avg_ms,
    )


def _detect_silence_gaps(
    y: Any,
    sr: float,
    duration_ms: int,
    threshold_ms: int = SILENCE_THRESHOLD_MS,
    top_db: float = SILENCE_TOP_DB,
) -> list[Gap]:
    """Find stretches of silence longer than ``threshold_ms`` using RMS energy."""
    if len(y) == 0 or sr <= 0:
        return []

    import librosa

    intervals = librosa.effects.split(y, top_db=top_db)

    if len(intervals) == 0:
        return [Gap(start_ms=0, end_ms=duration_ms)] if duration_ms >= threshold_ms else []

    gaps: list[Gap] = []
    prev_end_sample = 0
    for start_sample, end_sample in intervals:
        gap_start_ms = int(prev_end_sample / sr * 1000)
        gap_end_ms = int(start_sample / sr * 1000)
        if gap_end_ms - gap_start_ms >= threshold_ms:
            gaps.append(Gap(start_ms=gap_start_ms, end_ms=gap_end_ms))
        prev_end_sample = end_sample

    tail_start_ms = int(prev_end_sample / sr * 1000)
    if duration_ms - tail_start_ms >= threshold_ms:
        gaps.append(Gap(start_ms=tail_start_ms, end_ms=duration_ms))

    return gaps


def _count_interruptions(turns: list[Turn]) -> int:
    """Count speaker turns that start before the previous (different) speaker finished."""
    count = 0
    for prev, curr in zip(turns, turns[1:]):
        if curr.speaker != prev.speaker and curr.start_ms < prev.end_ms:
            count += 1
    return count


def _speaking_pace_wpm(full_text: str, duration_ms: int) -> float:
    """Compute words-per-minute from transcript text and total call duration."""
    if duration_ms <= 0:
        return 0.0
    minutes = duration_ms / 60_000
    return len(full_text.split()) / minutes


def _avg_turn_length_ms(turns: list[Turn]) -> float:
    """Compute the average duration of a speaker turn, in milliseconds."""
    if not turns:
        return 0.0
    return sum(t.end_ms - t.start_ms for t in turns) / len(turns)


def _pitch_variance(y: Any, sr: float) -> float:
    """Measure pitch modulation (std. dev. of voiced f0) using librosa's PYIN."""
    if len(y) == 0 or sr <= 0:
        return 0.0

    import librosa
    import numpy as np

    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=float(librosa.note_to_hz("C2")),
        fmax=float(librosa.note_to_hz("C7")),
        sr=sr,
    )

    voiced_f0 = f0[voiced_flag] if voiced_flag is not None else f0
    voiced_f0 = voiced_f0[~np.isnan(voiced_f0)]
    if voiced_f0.size == 0:
        return 0.0

    return float(np.std(voiced_f0))


def _score_quality(
    duration_ms: int,
    silence_gaps: list[Gap],
    interruptions: int,
    speaking_pace_wpm: float,
    pitch_variance: float,
) -> float:
    """Heuristic 0.0-1.0 quality score derived from the other quality signals."""
    score = 1.0

    if duration_ms > 0:
        silence_ms = sum(g.end_ms - g.start_ms for g in silence_gaps)
        score -= min(silence_ms / duration_ms, 0.4)

    score -= min(interruptions * 0.05, 0.3)

    if speaking_pace_wpm > 0:
        if speaking_pace_wpm < IDEAL_WPM_LOW:
            score -= min((IDEAL_WPM_LOW - speaking_pace_wpm) / IDEAL_WPM_LOW, 0.2)
        elif speaking_pace_wpm > IDEAL_WPM_HIGH:
            score -= min((speaking_pace_wpm - IDEAL_WPM_HIGH) / IDEAL_WPM_HIGH, 0.2)

    if pitch_variance < LOW_PITCH_VARIANCE_HZ:
        score -= 0.1

    return max(0.0, min(1.0, score))
