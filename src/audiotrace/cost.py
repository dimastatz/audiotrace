"""Call cost attribution from audio duration and transcript character counts."""

from __future__ import annotations

from dataclasses import dataclass, field

from audiotrace.models import Cost, MediaInfo, Transcript

# AWS Transcribe — standard streaming (us-east-1), per minute
_AWS_TRANSCRIBE_PER_MINUTE = 0.024

# AWS Polly — Neural TTS, per million characters
_AWS_POLLY_NEURAL_PER_MILLION_CHARS = 16.0

# OpenAI GPT-4o mini — per million tokens
_OPENAI_GPT4O_MINI_INPUT_PER_MILLION = 0.15
_OPENAI_GPT4O_MINI_OUTPUT_PER_MILLION = 0.60

# Rough character-to-token ratio used for LLM cost estimation
_CHARS_PER_TOKEN = 4


@dataclass
class PricingTable:
    """Per-unit pricing rates used to estimate call cost.

    All rates are in USD. Defaults match AWS Transcribe (STT), AWS Polly
    Neural (TTS), and OpenAI GPT-4o mini (LLM) public list prices.
    Telephony defaults to 0 — supply your own provider rate if needed.
    """

    stt_per_minute_usd: float = field(default=_AWS_TRANSCRIBE_PER_MINUTE)
    tts_per_million_chars_usd: float = field(default=_AWS_POLLY_NEURAL_PER_MILLION_CHARS)
    llm_input_per_million_tokens_usd: float = field(default=_OPENAI_GPT4O_MINI_INPUT_PER_MILLION)
    llm_output_per_million_tokens_usd: float = field(default=_OPENAI_GPT4O_MINI_OUTPUT_PER_MILLION)
    telephony_per_minute_usd: float = field(default=0.0)


DEFAULT_PRICING = PricingTable()


def extract_cost(
    media: MediaInfo,
    transcript: Transcript,
    pricing: PricingTable | None = None,
) -> Cost:
    """Estimate call cost from audio duration and transcript character counts.

    STT cost is derived from call duration.
    TTS cost is derived from agent-turn character count (synthesized speech).
    LLM cost is estimated from caller-turn characters (input) and agent-turn
    characters (output) using a chars-per-token approximation.
    When speaker labels are unavailable the full transcript is split evenly.

    Args:
        media: Populated MediaInfo from extract_media_info().
        transcript: Populated Transcript from extract_transcript().
        pricing: Custom rates to override defaults. None uses DEFAULT_PRICING.

    Returns:
        A populated :class:`~audiotrace.models.Cost`.
    """
    p = pricing if pricing is not None else DEFAULT_PRICING
    duration_minutes = media.duration_ms / 60_000

    stt_usd = duration_minutes * p.stt_per_minute_usd
    telephony_usd = duration_minutes * p.telephony_per_minute_usd

    agent_chars, caller_chars = _speaker_char_counts(transcript)
    tts_chars = agent_chars if agent_chars > 0 else len(transcript.full_text)
    tts_usd = tts_chars / 1_000_000 * p.tts_per_million_chars_usd

    llm_input_tokens = caller_chars / _CHARS_PER_TOKEN
    llm_output_tokens = agent_chars / _CHARS_PER_TOKEN
    llm_usd = (
        llm_input_tokens / 1_000_000 * p.llm_input_per_million_tokens_usd
        + llm_output_tokens / 1_000_000 * p.llm_output_per_million_tokens_usd
    )

    total_usd = stt_usd + tts_usd + llm_usd + telephony_usd

    return Cost(
        stt_usd=round(stt_usd, 6),
        tts_usd=round(tts_usd, 6),
        llm_usd=round(llm_usd, 6),
        telephony_usd=round(telephony_usd, 6),
        total_usd=round(total_usd, 6),
    )


def _speaker_char_counts(transcript: Transcript) -> tuple[int, int]:
    """Return (agent_chars, caller_chars), falling back to even split if labels unknown."""
    agent_chars = sum(len(t.text) for t in transcript.turns if t.speaker == "agent")
    caller_chars = sum(len(t.text) for t in transcript.turns if t.speaker == "caller")

    if agent_chars == 0 and caller_chars == 0:
        total = len(transcript.full_text)
        agent_chars = total // 2
        caller_chars = total - agent_chars

    return agent_chars, caller_chars
