import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audiotrace.models import Turn
from audiotrace.transcripts import (
    _apply_speaker_roles,
    _default_role_labels,
    _get_majority_speaker,
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


def _setup_whisper(segments, text="hello", language="en"):
    mock_model = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_model.transcribe.return_value = {
        "text": text,
        "language": language,
        "segments": segments,
    }


def test_fallback_num_speakers_assigns_alternating_roles():
    _setup_whisper(
        [
            {"start": 0.0, "end": 1.0, "text": "Hello, this is support."},
            {"start": 1.0, "end": 2.0, "text": "Hi, I need a room."},
            {"start": 2.0, "end": 3.0, "text": "Sure, what dates?"},
        ]
    )
    mock_pyannote_audio.Pipeline.from_pretrained.return_value = None

    transcript = extract_transcript(FIXTURE, num_speakers=2)

    assert [t.speaker for t in transcript.turns] == ["AI Agent", "Customer", "AI Agent"]


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
