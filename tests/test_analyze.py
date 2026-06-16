from pathlib import Path
from unittest.mock import patch

import pytest

import audiotrace
from audiotrace.models import Transcript


def test_version_exposed():
    assert isinstance(audiotrace.__version__, str)


@patch("audiotrace.core.extract_transcript")
def test_analyze_media_info(mock_extract_transcript):
    # Mock extract_transcript to return an empty Transcript
    mock_extract_transcript.return_value = Transcript()

    fixture_path = Path(__file__).parent / "fixtures" / "premier_phone_call_30s.mp3"
    report = audiotrace.analyze(fixture_path)

    assert report.media is not None
    assert report.media.codec == "mp3"
    # Allow 100ms tolerance for different FFmpeg versions (PRD requirement)
    assert abs(report.media.duration_ms - 30012) <= 100
    assert report.media.sample_rate_hz == 48000
    assert report.media.channels == 2
    assert report.media.file_format == "mp3"
    assert report.transcript is not None


@patch("audiotrace.core.extract_transcript")
def test_analyze_file_not_found(mock_extract_transcript):
    with pytest.raises(FileNotFoundError):
        audiotrace.analyze("non_existent_file.wav")


@patch("audiotrace.core.extract_transcript")
def test_analyze_ffprobe_error(mock_extract_transcript, tmp_path):
    invalid_file = tmp_path / "invalid.wav"
    invalid_file.write_text("not an audio file")
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        audiotrace.analyze(invalid_file)
