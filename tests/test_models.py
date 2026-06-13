from audiotrace import CallReport, MediaInfo, Transcript, Turn


def test_callreport_defaults():
    report = CallReport()
    assert report.quality.overall_score == 0.0
    assert report.events.outcome == "completed"
    assert report.events.drop_off_turn is None
    assert report.transcript.turns == []
    assert report.media is None


def test_callreport_media():
    media = MediaInfo(
        duration_ms=1000,
        sample_rate_hz=44100,
        channels=2,
        codec="mp3",
        file_size_bytes=1024,
        file_format="mp3",
        bitrate_kbps=128.0,
    )
    report = CallReport(media=media)
    assert report.media.duration_ms == 1000
    assert report.media.codec == "mp3"


def test_callreport_roundtrip():
    report = CallReport(
        transcript=Transcript(
            full_text="hello",
            turns=[Turn(speaker="agent", text="hello", start_ms=0, end_ms=500)],
        )
    )
    restored = CallReport.model_validate(report.model_dump())
    assert restored.transcript.turns[0].speaker == "agent"
    assert restored.transcript.full_text == "hello"
