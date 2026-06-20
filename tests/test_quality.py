import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from audiotrace.models import Transcript, Turn
from audiotrace.quality import (
    _avg_turn_length_ms,
    _count_interruptions,
    _detect_silence_gaps,
    _pitch_variance,
    _score_quality,
    _speaking_pace_wpm,
    extract_quality,
)

mock_librosa = MagicMock()

FIXTURE = Path(__file__).parent / "fixtures" / "paradise_hotel_booking_60s.mp3"


@pytest.fixture(autouse=True)
def mock_heavy_deps():
    mock_librosa.reset_mock(return_value=True, side_effect=True)
    with patch.dict(sys.modules, {"librosa": mock_librosa}):
        yield


def test_extract_quality_file_not_found():
    with pytest.raises(FileNotFoundError):
        extract_quality("non_existent.wav", Transcript(), duration_ms=1000)


def test_extract_quality_success():
    sr = 100
    y = np.zeros(sr * 10)  # 10s of "audio"
    mock_librosa.load.return_value = (y, sr)
    mock_librosa.effects.split.return_value = np.array([[0, sr * 10]])
    mock_librosa.note_to_hz.side_effect = lambda note: {"C2": 65.0, "C7": 2093.0}[note]
    mock_librosa.pyin.return_value = (
        np.array([100.0, 110.0, 120.0]),
        np.array([True, True, True]),
        np.array([0.9, 0.9, 0.9]),
    )

    transcript = Transcript(
        full_text="hello there how are you doing today",
        turns=[
            Turn(speaker="agent", text="hello there", start_ms=0, end_ms=1000),
            Turn(speaker="caller", text="how are you", start_ms=1500, end_ms=2500),
        ],
    )

    quality = extract_quality(FIXTURE, transcript, duration_ms=10_000)

    assert quality.silence_gaps == []
    assert quality.interruptions == 0
    assert quality.turn_length_avg_ms == 1000.0
    assert quality.speaking_pace_wpm == pytest.approx(42.0)
    assert quality.pitch_variance == pytest.approx(np.std([100.0, 110.0, 120.0]))
    assert 0.0 <= quality.overall_score <= 1.0


def test_detect_silence_gaps_no_intervals_entire_clip_silent():
    mock_librosa.effects.split.return_value = np.array([])
    gaps = _detect_silence_gaps(np.zeros(10), sr=10, duration_ms=3000)
    assert len(gaps) == 1
    assert (gaps[0].start_ms, gaps[0].end_ms) == (0, 3000)


def test_detect_silence_gaps_no_intervals_short_clip():
    mock_librosa.effects.split.return_value = np.array([])
    gaps = _detect_silence_gaps(np.zeros(10), sr=10, duration_ms=500)
    assert gaps == []


def test_detect_silence_gaps_empty_audio():
    assert _detect_silence_gaps(np.array([]), sr=100, duration_ms=1000) == []


def test_detect_silence_gaps_zero_sample_rate():
    assert _detect_silence_gaps(np.zeros(10), sr=0, duration_ms=1000) == []


def test_detect_silence_gaps_leading_and_trailing():
    sr = 1000
    # Speech from 3s-5s within a 10s clip: leading 3s gap, trailing 5s gap.
    mock_librosa.effects.split.return_value = np.array([[3000, 5000]])
    gaps = _detect_silence_gaps(np.zeros(sr * 10), sr=sr, duration_ms=10_000)

    assert len(gaps) == 2
    assert (gaps[0].start_ms, gaps[0].end_ms) == (0, 3000)
    assert (gaps[1].start_ms, gaps[1].end_ms) == (5000, 10_000)


def test_detect_silence_gaps_below_threshold_ignored():
    sr = 1000
    mock_librosa.effects.split.return_value = np.array([[0, 1000], [1500, 10_000]])
    gaps = _detect_silence_gaps(np.zeros(sr * 10), sr=sr, duration_ms=10_000)
    assert gaps == []


def test_count_interruptions():
    turns = [
        Turn(speaker="agent", text="a", start_ms=0, end_ms=1000),
        Turn(speaker="caller", text="b", start_ms=900, end_ms=2000),  # interrupts agent
        Turn(speaker="agent", text="c", start_ms=2000, end_ms=3000),  # no overlap
        Turn(speaker="agent", text="d", start_ms=2900, end_ms=3900),  # same speaker, ignored
    ]
    assert _count_interruptions(turns) == 1


def test_count_interruptions_no_turns():
    assert _count_interruptions([]) == 0


def test_speaking_pace_wpm_zero_duration():
    assert _speaking_pace_wpm("hello world", duration_ms=0) == 0.0


def test_speaking_pace_wpm():
    assert _speaking_pace_wpm("one two three four", duration_ms=60_000) == 4.0


def test_avg_turn_length_ms_no_turns():
    assert _avg_turn_length_ms([]) == 0.0


def test_avg_turn_length_ms():
    turns = [
        Turn(speaker="agent", text="a", start_ms=0, end_ms=1000),
        Turn(speaker="caller", text="b", start_ms=1000, end_ms=4000),
    ]
    assert _avg_turn_length_ms(turns) == 2000.0


def test_pitch_variance_empty_audio():
    assert _pitch_variance(np.array([]), sr=100) == 0.0


def test_pitch_variance_zero_sample_rate():
    assert _pitch_variance(np.zeros(10), sr=0) == 0.0


def test_pitch_variance_all_unvoiced():
    mock_librosa.note_to_hz.side_effect = lambda note: {"C2": 65.0, "C7": 2093.0}[note]
    mock_librosa.pyin.return_value = (
        np.array([np.nan, np.nan]),
        np.array([False, False]),
        np.array([0.0, 0.0]),
    )
    assert _pitch_variance(np.zeros(10), sr=100) == 0.0


def test_pitch_variance_voiced_flag_none():
    mock_librosa.note_to_hz.side_effect = lambda note: {"C2": 65.0, "C7": 2093.0}[note]
    mock_librosa.pyin.return_value = (np.array([100.0, 200.0]), None, np.array([0.9, 0.9]))
    assert _pitch_variance(np.zeros(10), sr=100) == pytest.approx(np.std([100.0, 200.0]))


def test_score_quality_perfect():
    score = _score_quality(
        duration_ms=10_000,
        silence_gaps=[],
        interruptions=0,
        speaking_pace_wpm=140.0,
        pitch_variance=20.0,
    )
    assert score == 1.0


def test_score_quality_zero_duration():
    score = _score_quality(
        duration_ms=0,
        silence_gaps=[],
        interruptions=0,
        speaking_pace_wpm=0.0,
        pitch_variance=0.0,
    )
    assert score == pytest.approx(0.9)


def test_score_quality_penalizes_all_factors():
    from audiotrace.models import Gap

    score = _score_quality(
        duration_ms=10_000,
        silence_gaps=[Gap(start_ms=0, end_ms=10_000)],
        interruptions=10,
        speaking_pace_wpm=300.0,
        pitch_variance=1.0,
    )
    assert score == 0.0


def test_score_quality_slow_pace_penalty():
    score = _score_quality(
        duration_ms=10_000,
        silence_gaps=[],
        interruptions=0,
        speaking_pace_wpm=50.0,
        pitch_variance=20.0,
    )
    assert 0.0 < score < 1.0
