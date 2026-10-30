"""Estimate call cost with your own provider rates.

python examples/custom_pricing.py [path/to/call.wav]
"""

import sys

from _common import SAMPLE_CALL

import audiotrace

# Example rates; replace with your contracts.
PRICING = audiotrace.PricingTable(
    stt_per_minute_usd=0.0043,
    tts_per_million_chars_usd=30.0,
    llm_input_per_million_tokens_usd=3.0,
    llm_output_per_million_tokens_usd=15.0,
    telephony_per_minute_usd=0.014,
)


def main(audio=SAMPLE_CALL):
    report = audiotrace.analyze(audio, num_speakers=2, pricing=PRICING)
    cost = report.cost
    print(
        f"STT ${cost.stt_usd:.4f}  LLM ${cost.llm_usd:.4f}  TTS ${cost.tts_usd:.4f}  "
        f"telephony ${cost.telephony_usd:.4f}  total ${cost.total_usd:.4f}"
    )
    return cost


if __name__ == "__main__":
    main(*sys.argv[1:2])
