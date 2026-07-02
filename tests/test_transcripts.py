import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from audiotrace.models import Turn
from audiotrace.transcripts import (
    MIN_DIARIZATION_CONFIDENCE,
    _apply_speaker_roles,
    _cluster_confidence,
    _cluster_pitches,
    _default_role_labels,
    _get_majority_speaker,
    _kmeans_1d,
    _make_turn,
    _segment_confidence,
    _segment_pitches,
    _segment_words,
    clear_model_cache,
    extract_transcript,
)

FIXTURE = Path(__file__).parent / "fixtures" / "paradise_hotel_booking_60s.mp3"

# Mock modules before importing the module under test if necessary,
# or just mock them when needed.
mock_whisper = MagicMock()
mock_pyannote = MagicMock()
mock_pyannote_audio = MagicMock()
mock_pyannote_core = MagicMock()


@pytest.fixture(autouse=True)
def mock_heavy_deps():
    clear_model_cache()
    with patch.dict(
        sys.modules,
        {
            "whisper": mock_whisper,
            "pyannote": mock_pyannote,
            "pyannote.audio": mock_pyannote_audio,
            "pyannote.core": mock_pyannote_core,
        },
    ):
        yield


def test_extract_transcript_success():
    # Setup Whisper mock
    mock_model = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_model.transcribe.return_value = {
        "text": "Hello world",
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "Hello"},
            {"start": 1.0, "end": 2.0, "text": "world"},
        ],
    }

    # Setup Pyannote mock
    mock_pipeline_class = mock_pyannote_audio.Pipeline
    mock_pipeline = MagicMock()
    mock_pipeline_class.from_pretrained.return_value = mock_pipeline
    mock_diarization = MagicMock()
    mock_pipeline.return_value = mock_diarization

    fixture_path = Path(__file__).parent / "fixtures" / "paradise_hotel_booking_60s.mp3"

    with patch("audiotrace.transcripts._get_majority_speaker") as mock_majority:
        mock_majority.side_effect = ["SPEAKER_00", "SPEAKER_01"]

        transcript = extract_transcript(fixture_path, hf_token="fake_token")

        assert transcript.full_text == "Hello world"
        assert transcript.language == "en"
        assert len(transcript.turns) == 2
        assert transcript.turns[0].speaker == "SPEAKER_00"
        assert transcript.turns[0].text == "Hello"
        assert transcript.turns[1].speaker == "SPEAKER_01"
        assert transcript.turns[1].text == "world"


def test_extract_transcript_file_not_found():
    with pytest.raises(FileNotFoundError):
        extract_transcript("non_existent.wav")


def test_extract_transcript_no_hf_token():
    # Whisper mock
    mock_model = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_model.transcribe.return_value = {
        "text": "Hello",
        "language": "en",
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
    }

    # Pyannote mock returns None (e.g. no token)
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    fixture_path = Path(__file__).parent / "fixtures" / "paradise_hotel_booking_60s.mp3"
    transcript = extract_transcript(fixture_path)

    assert transcript.full_text == "Hello"
    assert len(transcript.turns) == 1
    assert transcript.turns[0].speaker == "unknown"


def test_get_majority_speaker():
    mock_diarization = MagicMock()
    mock_crop = MagicMock()
    mock_diarization.crop.return_value = mock_crop

    # Mock segment and intersection
    mock_segment = MagicMock()
    mock_segment.duration = 1.0
    mock_intersection = MagicMock()
    mock_intersection.duration = 1.0
    mock_segment.__and__.return_value = mock_intersection

    # Case 1: Multiple speakers, one dominant
    mock_crop.labels.return_value = ["SPEAKER_00", "SPEAKER_01"]
    # itertracks should yield (segment, track, label)
    mock_crop.itertracks.return_value = [
        (mock_segment, "A", "SPEAKER_00"),
        (mock_segment, "B", "SPEAKER_01"),
        (mock_segment, "C", "SPEAKER_00"),
    ]

    speaker = _get_majority_speaker(mock_diarization, 0.0, 2.0)
    assert speaker == "SPEAKER_00"

    # Case 2: No speakers
    mock_crop.labels.return_value = []
    speaker = _get_majority_speaker(mock_diarization, 0.0, 1.0)
    assert speaker == "unknown"

    # Case 3: Labels present but no tracks yielded
    mock_crop.labels.return_value = ["SPEAKER_00"]
    mock_crop.itertracks.return_value = []
    assert _get_majority_speaker(mock_diarization, 0.0, 1.0) == "unknown"


def _setup_whisper(segments, text="hello", language="en"):
    mock_model = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_model.transcribe.return_value = {
        "text": text,
        "language": language,
        "segments": segments,
    }


def test_fallback_groups_segments_by_pitch():
    _setup_whisper(
        [
            {"start": 0.0, "end": 2.0, "text": "Thank you for calling."},
            {"start": 2.0, "end": 4.0, "text": "How can I help you today?"},
            {"start": 4.0, "end": 6.0, "text": "Hi, I need a room."},
        ]
    )
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    # Agent's two sentences share a high pitch; the customer's is lower. They
    # must group by speaker, not alternate per sentence.
    with patch("audiotrace.transcripts._segment_pitches", return_value=[210.0, 205.0, 110.0]):
        transcript = extract_transcript(FIXTURE, num_speakers=2)

    assert [t.speaker for t in transcript.turns] == ["AI Agent", "AI Agent", "Customer"]


def test_diarize_false_skips_pyannote():
    _setup_whisper(
        [
            {"start": 0.0, "end": 2.0, "text": "Hello there."},
            {"start": 2.0, "end": 4.0, "text": "Hi, I need a room."},
        ]
    )
    # A pipeline WOULD load, but diarize=False must skip pyannote entirely.
    mock_pyannote_audio.Pipeline.from_pretrained.reset_mock()
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = MagicMock()

    with patch("audiotrace.transcripts._segment_pitches", return_value=[210.0, 110.0]):
        transcript = extract_transcript(FIXTURE, num_speakers=2, diarize=False)

    mock_pyannote_audio.Pipeline.from_pretrained.assert_not_called()
    assert [t.speaker for t in transcript.turns] == ["AI Agent", "Customer"]


def test_cluster_pitches_two_groups():
    clusters = _cluster_pitches([200.0, 205.0, 110.0, 115.0], 2)
    assert clusters[0] == clusters[1]
    assert clusters[2] == clusters[3]
    assert clusters[0] != clusters[2]


def test_cluster_pitches_none_inherits_previous():
    clusters = _cluster_pitches([200.0, None, 110.0], 2)
    assert clusters[1] == clusters[0]


def test_cluster_pitches_insufficient_distinct_pitch():
    assert _cluster_pitches([200.0, 200.0], 2) == [0, 0]


def test_cluster_pitches_single_speaker():
    assert _cluster_pitches([200.0, 110.0], 1) == [0, 0]


def test_cluster_pitches_all_unvoiced():
    assert _cluster_pitches([None, None], 2) == [0, 0]


def test_cluster_confidence_well_separated():
    # Two clear pitch bands with an empty valley between them -> high confidence.
    pitches = [200.0, 205.0, 110.0, 115.0]
    conf = _cluster_confidence(pitches, _cluster_pitches(pitches, 2))
    assert conf == 1.0


def test_cluster_confidence_overlapping_is_low():
    # One continuous blob k-means splits down the middle: no real gap -> low.
    pitches = [200.0, 205.0, 210.0, 215.0, 220.0, 225.0]
    conf = _cluster_confidence(pitches, _cluster_pitches(pitches, 2))
    assert conf < MIN_DIARIZATION_CONFIDENCE


def test_cluster_confidence_single_cluster_is_zero():
    assert _cluster_confidence([200.0, 205.0], [0, 0]) == 0.0


def test_fallback_collapses_when_voices_too_similar():
    _setup_whisper(
        [
            {"start": 0.0, "end": 2.0, "text": "Hello there."},
            {"start": 2.0, "end": 4.0, "text": "Hi, I need a room."},
            {"start": 4.0, "end": 6.0, "text": "Of course, what dates?"},
            {"start": 6.0, "end": 8.0, "text": "This weekend if possible."},
            {"start": 8.0, "end": 10.0, "text": "Let me check for you."},
            {"start": 10.0, "end": 12.0, "text": "Thanks so much."},
        ]
    )
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    # One continuous pitch blob (no valley): can't tell the speakers apart.
    pitches = [200.0, 205.0, 210.0, 215.0, 220.0, 225.0]
    with patch("audiotrace.transcripts._segment_pitches", return_value=pitches):
        transcript = extract_transcript(FIXTURE, num_speakers=2)

    # Everyone collapses to one speaker, and the result is flagged low-confidence.
    assert len({t.speaker for t in transcript.turns}) == 1
    assert transcript.diarization_confidence < MIN_DIARIZATION_CONFIDENCE


def test_fallback_reports_high_confidence_when_separated():
    _setup_whisper(
        [
            {"start": 0.0, "end": 2.0, "text": "Hello there."},
            {"start": 2.0, "end": 4.0, "text": "Hi, I need a room."},
        ]
    )
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    with patch("audiotrace.transcripts._segment_pitches", return_value=[210.0, 110.0]):
        transcript = extract_transcript(FIXTURE, num_speakers=2)

    assert [t.speaker for t in transcript.turns] == ["AI Agent", "Customer"]
    assert transcript.diarization_confidence == 1.0


def test_diarization_confidence_none_for_real_pipeline():
    _setup_whisper([{"start": 0.0, "end": 2.0, "text": "Hello there."}])
    diarization = MagicMock()
    diarization.crop.return_value.labels.return_value = ["SPEAKER_00"]
    diarization.crop.return_value.itertracks.return_value = []
    pipeline = MagicMock(return_value=diarization)
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = pipeline

    transcript = extract_transcript(FIXTURE, hf_token="t", num_speakers=2)

    assert transcript.diarization_confidence is None


def test_kmeans_1d_separates_two_groups():
    lo, hi = sorted(_kmeans_1d([100.0, 105.0, 300.0, 305.0], 2))
    assert 95 <= lo <= 110
    assert 295 <= hi <= 310


def test_kmeans_1d_respects_iteration_cap():
    # iters=1 forces the loop to exit by exhaustion (no convergence break).
    centers = _kmeans_1d([100.0, 102.0, 300.0], 2, iters=1)
    assert sorted(centers) == [101.0, 300.0]


def test_segment_words_extracts_timings():
    seg = {
        "words": [
            {"word": " Hello", "start": 0.0, "end": 0.5},
            {"word": " world", "start": 0.5, "end": 1.0},
        ]
    }
    words = _segment_words(seg)
    assert [(w.text, w.start_ms, w.end_ms) for w in words] == [
        ("Hello", 0, 500),
        ("world", 500, 1000),
    ]


def test_segment_words_empty_when_absent():
    assert _segment_words({"text": "hi"}) == []


def test_make_turn_includes_words():
    seg = {
        "text": " Hello world ",
        "start": 0.0,
        "end": 1.0,
        "words": [
            {"word": " Hello", "start": 0.0, "end": 0.5},
            {"word": " world", "start": 0.5, "end": 1.0},
        ],
    }
    turn = _make_turn(seg, "AI Agent")
    assert turn.speaker == "AI Agent"
    assert turn.text == "Hello world"
    assert (turn.start_ms, turn.end_ms) == (0, 1000)
    assert [w.text for w in turn.words] == ["Hello", "world"]


def test_segment_confidence_mean_word_probability():
    seg = {
        "words": [
            {"word": " Hello", "probability": 0.9},
            {"word": " world", "probability": 0.7},
        ]
    }
    assert _segment_confidence(seg) == pytest.approx(0.8)


def test_segment_confidence_avg_logprob_fallback():
    import math

    seg = {"avg_logprob": math.log(0.5)}
    assert _segment_confidence(seg) == pytest.approx(0.5)


def test_segment_confidence_absent_is_zero():
    assert _segment_confidence({"text": "hi"}) == 0.0


def test_make_turn_includes_confidence():
    seg = {
        "text": "hi",
        "start": 0.0,
        "end": 1.0,
        "words": [{"word": " hi", "start": 0.0, "end": 1.0, "probability": 0.95}],
    }
    assert _make_turn(seg, "AI Agent").confidence == pytest.approx(0.95)


def test_extract_transcript_populates_word_timings():
    _setup_whisper(
        [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "Hello world",
                "words": [
                    {"word": " Hello", "start": 0.0, "end": 0.5},
                    {"word": " world", "start": 0.5, "end": 1.0},
                ],
            }
        ]
    )
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    transcript = extract_transcript(FIXTURE)

    assert [w.text for w in transcript.turns[0].words] == ["Hello", "world"]


def test_segment_pitches_median_and_unvoiced_and_empty():
    mock_librosa = MagicMock()
    mock_librosa.load.return_value = (np.ones(60, dtype=float), 10)
    mock_librosa.pyin.side_effect = [
        (np.array([100.0, 200.0, 300.0]), np.array([True, True, True]), None),
        (np.array([np.nan, np.nan]), np.array([False, False]), None),
    ]
    segments = [
        {"start": 0.0, "end": 2.0, "text": "a"},  # voiced -> median 200
        {"start": 2.0, "end": 4.0, "text": "b"},  # all NaN -> None
        {"start": 4.0, "end": 4.0, "text": "c"},  # empty clip -> None
    ]
    with patch.dict(sys.modules, {"librosa": mock_librosa}):
        pitches = _segment_pitches(Path("x.wav"), segments)

    assert pitches == [200.0, None, None]


def test_fallback_without_num_speakers_stays_unknown():
    _setup_whisper([{"start": 0.0, "end": 1.0, "text": "Hello"}])
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    transcript = extract_transcript(FIXTURE)

    assert transcript.turns[0].speaker == "unknown"


def test_diarization_maps_raw_speakers_to_roles():
    _setup_whisper(
        [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 1.0, "end": 2.0, "text": "B"},
        ]
    )
    mock_pipeline = MagicMock()
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = mock_pipeline
    mock_pipeline.return_value = MagicMock()

    with patch("audiotrace.transcripts._get_majority_speaker") as mock_majority:
        # First-heard raw speaker -> "AI Agent", second -> "Customer".
        mock_majority.side_effect = ["SPEAKER_01", "SPEAKER_00"]
        transcript = extract_transcript(FIXTURE, hf_token="t", num_speakers=2)

    assert [t.speaker for t in transcript.turns] == ["AI Agent", "Customer"]


def test_num_speakers_is_passed_to_pipeline():
    _setup_whisper([{"start": 0.0, "end": 1.0, "text": "A"}])
    mock_pipeline = MagicMock()
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = mock_pipeline
    mock_pipeline.return_value = MagicMock()

    with patch("audiotrace.transcripts._get_majority_speaker", return_value="SPEAKER_00"):
        extract_transcript(FIXTURE, hf_token="t", num_speakers=2)

    _, kwargs = mock_pipeline.call_args
    assert kwargs.get("num_speakers") == 2


def test_custom_speaker_labels_applied():
    _setup_whisper(
        [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 1.0, "end": 2.0, "text": "B"},
        ]
    )
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    transcript = extract_transcript(FIXTURE, num_speakers=2, speaker_labels=["Bot", "Human"])

    assert [t.speaker for t in transcript.turns] == ["Bot", "Human"]


def test_default_role_labels_two():
    assert _default_role_labels(2) == ["AI Agent", "Customer"]


def test_default_role_labels_other_count():
    assert _default_role_labels(3) == ["Speaker 1", "Speaker 2", "Speaker 3"]


def test_apply_speaker_roles_noop_without_hints():
    turns = [Turn(speaker="SPEAKER_00", text="x", start_ms=0, end_ms=1)]
    out = _apply_speaker_roles(turns, None, None)
    assert out[0].speaker == "SPEAKER_00"


def test_apply_speaker_roles_empty_default_is_noop():
    # num_speakers=0 yields an empty default label list -> turns unchanged.
    turns = [Turn(speaker="SPEAKER_00", text="x", start_ms=0, end_ms=1)]
    out = _apply_speaker_roles(turns, 0, None)
    assert out[0].speaker == "SPEAKER_00"
