from pathlib import Path
from unittest.mock import patch

import pytest

import audiotrace
from audiotrace.models import Cost, Quality, Sentiment, Transcript


def test_version_exposed():
    assert isinstance(audiotrace.__version__, str)


def test_pricing_table_exported():
    from audiotrace import PricingTable

    p = PricingTable(stt_per_minute_usd=0.05)
    assert p.stt_per_minute_usd == 0.05


@patch("audiotrace.core.extract_cost")
@patch("audiotrace.core.extract_sentiment")
@patch("audiotrace.core.extract_quality")
@patch("audiotrace.core.extract_transcript")
def test_analyze_media_info(
    mock_extract_transcript, mock_extract_quality, mock_extract_sentiment, mock_extract_cost
):
    mock_extract_transcript.return_value = Transcript()
    mock_extract_quality.return_value = Quality()
    mock_extract_sentiment.return_value = Sentiment()
    mock_extract_cost.return_value = Cost()

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
    assert report.quality is not None
    assert report.sentiment is not None
    assert report.cost is not None
    mock_extract_quality.assert_called_once_with(
        fixture_path, mock_extract_transcript.return_value, report.media.duration_ms
    )
    mock_extract_sentiment.assert_called_once_with(mock_extract_transcript.return_value)
    mock_extract_cost.assert_called_once_with(
        report.media, mock_extract_transcript.return_value, None
    )


@patch("audiotrace.core.extract_cost")
@patch("audiotrace.core.extract_sentiment")
@patch("audiotrace.core.extract_quality")
@patch("audiotrace.core.extract_transcript")
def test_analyze_file_not_found(
    mock_extract_transcript, mock_extract_quality, mock_extract_sentiment, mock_extract_cost
):
    with pytest.raises(FileNotFoundError):
        audiotrace.analyze("non_existent_file.wav")


@patch("audiotrace.core.extract_cost")
@patch("audiotrace.core.extract_sentiment")
@patch("audiotrace.core.extract_quality")
@patch("audiotrace.core.extract_transcript")
def test_analyze_ffprobe_error(
    mock_extract_transcript,
    mock_extract_quality,
    mock_extract_sentiment,
    mock_extract_cost,
    tmp_path,
):
    invalid_file = tmp_path / "invalid.wav"
    invalid_file.write_text("not an audio file")
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        audiotrace.analyze(invalid_file)
