from audiotrace.latency import RESPONSE_NOISE_FLOOR_MS, extract_waterfall
from audiotrace.models import Transcript, Turn


def _turn(speaker: str, start_ms: int, end_ms: int) -> Turn:
    return Turn(speaker=speaker, text="x", start_ms=start_ms, end_ms=end_ms)


def test_empty_transcript_returns_no_spans():
    assert extract_waterfall(Transcript()) == []


def test_unknown_speakers_produce_no_spans():
    transcript = Transcript(
        turns=[
            _turn("unknown", 0, 1000),
            _turn("unknown", 3000, 4000),
        ]
    )
    assert extract_waterfall(transcript) == []


def test_caller_to_agent_gap_above_floor_emits_span():
    transcript = Transcript(
        turns=[
            _turn("caller", 0, 1000),
            _turn("agent", 2500, 3500),  # 1500ms gap
        ]
    )
    spans = extract_waterfall(transcript)
    assert len(spans) == 1
    assert spans[0].name == "agent_response"
    assert spans[0].start_ms == 1000
    assert spans[0].duration_ms == 1500


def test_gap_exactly_at_floor_is_omitted():
    transcript = Transcript(
        turns=[
            _turn("caller", 0, 1000),
            _turn("agent", 1000 + RESPONSE_NOISE_FLOOR_MS, 4000),
        ]
    )
    assert extract_waterfall(transcript) == []


def test_gap_below_floor_is_omitted():
    transcript = Transcript(
        turns=[
            _turn("caller", 0, 1000),
            _turn("agent", 1100, 2000),  # 100ms gap
        ]
    )
    assert extract_waterfall(transcript) == []


def test_overlapping_barge_in_is_omitted():
    transcript = Transcript(
        turns=[
            _turn("caller", 0, 2000),
            _turn("agent", 1500, 3000),  # negative gap (overlap)
        ]
    )
    assert extract_waterfall(transcript) == []


def test_agent_to_caller_transition_is_ignored():
    transcript = Transcript(
        turns=[
            _turn("agent", 0, 1000),
            _turn("caller", 3000, 4000),
        ]
    )
    assert extract_waterfall(transcript) == []


def test_same_speaker_transition_is_ignored():
    transcript = Transcript(
        turns=[
            _turn("caller", 0, 1000),
            _turn("caller", 3000, 4000),
        ]
    )
    assert extract_waterfall(transcript) == []


def test_multiple_gaps_are_chronological():
    transcript = Transcript(
        turns=[
            _turn("caller", 0, 1000),
            _turn("agent", 3000, 4000),  # 2000ms gap, start 1000
            _turn("caller", 4000, 5000),
            _turn("agent", 6000, 7000),  # 1000ms gap, start 5000
        ]
    )
    spans = extract_waterfall(transcript)
    assert [(s.start_ms, s.duration_ms) for s in spans] == [(1000, 2000), (5000, 1000)]
