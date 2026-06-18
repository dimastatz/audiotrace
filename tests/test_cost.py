import pytest

from audiotrace.cost import (
    DEFAULT_PRICING,
    PricingTable,
    _speaker_char_counts,
    extract_cost,
)
from audiotrace.models import MediaInfo, Transcript, Turn


def _media(duration_ms: int = 60_000) -> MediaInfo:
    return MediaInfo(
        duration_ms=duration_ms,
        sample_rate_hz=16000,
        channels=1,
        codec="mp3",
        file_size_bytes=1000,
        file_format="mp3",
        bitrate_kbps=128.0,
    )


def _turn(speaker: str, text: str) -> Turn:
    return Turn(speaker=speaker, text=text, start_ms=0, end_ms=1000)


# --- PricingTable defaults ---


def test_default_pricing_aws_transcribe_rate():
    assert DEFAULT_PRICING.stt_per_minute_usd == pytest.approx(0.024)


def test_default_pricing_aws_polly_neural_rate():
    assert DEFAULT_PRICING.tts_per_million_chars_usd == pytest.approx(16.0)


def test_default_pricing_openai_gpt4o_mini_input():
    assert DEFAULT_PRICING.llm_input_per_million_tokens_usd == pytest.approx(0.15)


def test_default_pricing_openai_gpt4o_mini_output():
    assert DEFAULT_PRICING.llm_output_per_million_tokens_usd == pytest.approx(0.60)


def test_default_pricing_telephony_zero():
    assert DEFAULT_PRICING.telephony_per_minute_usd == 0.0


# --- STT cost ---


def test_stt_cost_one_minute():
    media = _media(duration_ms=60_000)
    cost = extract_cost(media, Transcript(), DEFAULT_PRICING)
    assert cost.stt_usd == pytest.approx(0.024, rel=1e-4)


def test_stt_cost_thirty_seconds():
    media = _media(duration_ms=30_000)
    cost = extract_cost(media, Transcript(), DEFAULT_PRICING)
    assert cost.stt_usd == pytest.approx(0.012, rel=1e-4)


def test_stt_cost_uses_custom_rate():
    pricing = PricingTable(stt_per_minute_usd=0.10)
    cost = extract_cost(_media(60_000), Transcript(), pricing)
    assert cost.stt_usd == pytest.approx(0.10, rel=1e-4)


# --- TTS cost ---


def test_tts_cost_uses_agent_chars():
    transcript = Transcript(
        full_text="hi hello",
        turns=[
            _turn("agent", "hi"),  # 2 chars
            _turn("caller", "hello"),  # 5 chars — excluded from TTS
        ],
    )
    cost = extract_cost(_media(), transcript, DEFAULT_PRICING)
    expected = 2 / 1_000_000 * DEFAULT_PRICING.tts_per_million_chars_usd
    assert cost.tts_usd == pytest.approx(expected)


def test_tts_cost_falls_back_to_half_split_when_speakers_unknown():
    # "hello world" = 11 chars → even split gives agent 5 chars, caller 6 chars
    transcript = Transcript(
        full_text="hello world",
        turns=[_turn("unknown", "hello world")],
    )
    cost = extract_cost(_media(), transcript, DEFAULT_PRICING)
    expected = (len("hello world") // 2) / 1_000_000 * DEFAULT_PRICING.tts_per_million_chars_usd
    assert cost.tts_usd == pytest.approx(expected)


def test_tts_cost_uses_custom_rate():
    transcript = Transcript(turns=[_turn("agent", "x" * 1_000_000)])
    pricing = PricingTable(tts_per_million_chars_usd=4.0)
    cost = extract_cost(_media(), transcript, pricing)
    assert cost.tts_usd == pytest.approx(4.0, rel=1e-4)


# --- LLM cost ---


def test_llm_cost_caller_is_input_agent_is_output():
    # 4000 caller chars → 1000 tokens input; 2000 agent chars → 500 tokens output
    transcript = Transcript(
        turns=[
            _turn("caller", "a" * 4000),
            _turn("agent", "b" * 2000),
        ]
    )
    p = DEFAULT_PRICING
    expected = (
        1000 / 1_000_000 * p.llm_input_per_million_tokens_usd
        + 500 / 1_000_000 * p.llm_output_per_million_tokens_usd
    )
    cost = extract_cost(_media(), transcript, p)
    assert cost.llm_usd == pytest.approx(expected)


def test_llm_cost_unknown_speakers_uses_half_split():
    transcript = Transcript(
        full_text="x" * 8000,
        turns=[_turn("unknown", "x" * 8000)],
    )
    # 4000 agent chars → 1000 tokens out; 4000 caller chars → 1000 tokens in
    p = DEFAULT_PRICING
    expected = (
        1000 / 1_000_000 * p.llm_input_per_million_tokens_usd
        + 1000 / 1_000_000 * p.llm_output_per_million_tokens_usd
    )
    cost = extract_cost(_media(), transcript, p)
    assert cost.llm_usd == pytest.approx(expected)


# --- Telephony cost ---


def test_telephony_zero_by_default():
    cost = extract_cost(_media(60_000), Transcript())
    assert cost.telephony_usd == 0.0


def test_telephony_cost_custom_rate():
    pricing = PricingTable(telephony_per_minute_usd=0.013)
    cost = extract_cost(_media(60_000), Transcript(), pricing)
    assert cost.telephony_usd == pytest.approx(0.013, rel=1e-4)


# --- total_usd ---


def test_total_is_sum_of_parts():
    cost = extract_cost(_media(60_000), Transcript(), DEFAULT_PRICING)
    assert cost.total_usd == pytest.approx(
        cost.stt_usd + cost.tts_usd + cost.llm_usd + cost.telephony_usd,
        rel=1e-4,
    )


def test_none_pricing_uses_defaults():
    c1 = extract_cost(_media(), Transcript())
    c2 = extract_cost(_media(), Transcript(), DEFAULT_PRICING)
    assert c1.stt_usd == c2.stt_usd
    assert c1.total_usd == c2.total_usd


# --- _speaker_char_counts ---


def test_speaker_char_counts_known_labels():
    transcript = Transcript(
        turns=[
            _turn("agent", "hello"),  # 5
            _turn("caller", "world"),  # 5
        ]
    )
    agent, caller = _speaker_char_counts(transcript)
    assert agent == 5
    assert caller == 5


def test_speaker_char_counts_unknown_labels_even_split():
    transcript = Transcript(
        full_text="ab",
        turns=[_turn("unknown", "ab")],
    )
    agent, caller = _speaker_char_counts(transcript)
    assert agent + caller == 2


def test_speaker_char_counts_odd_length_full_text():
    transcript = Transcript(
        full_text="abc",
        turns=[_turn("unknown", "abc")],
    )
    agent, caller = _speaker_char_counts(transcript)
    assert agent + caller == 3
