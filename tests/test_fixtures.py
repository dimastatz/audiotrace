def test_golden_call_audio_available(golden_call_audio):
    assert golden_call_audio.suffix == ".mp3"
    # Sanity check it's the real ~1MB clip, not an empty/truncated file.
    assert golden_call_audio.stat().st_size > 100_000
