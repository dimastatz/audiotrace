from pathlib import Path

import pytest

import audiotrace


def test_version_exposed():
    assert isinstance(audiotrace.__version__, str)


def test_analyze_media_info():
    fixture_path = Path(__file__).parent / "fixtures" / "premier_phone_call_30s.mp3"
    report = audiotrace.analyze(fixture_path)

    assert report.media is not None
    assert report.media.codec == "mp3"
    # Allow 100ms tolerance for different FFmpeg versions (PRD requirement)
    assert abs(report.media.duration_ms - 30012) <= 100
    assert report.media.sample_rate_hz == 48000
    assert report.media.channels == 2
    assert report.media.file_format == "mp3"


def test_analyze_file_not_found():
    with pytest.raises(FileNotFoundError):
        audiotrace.analyze("non_existent_file.wav")


def test_analyze_ffprobe_error(tmp_path):
    invalid_file = tmp_path / "invalid.wav"
    invalid_file.write_text("not an audio file")
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        audiotrace.analyze(invalid_file)


def test_batch_not_implemented():
    with pytest.raises(NotImplementedError):
        audiotrace.batch(["call1.wav", "call2.wav"])
