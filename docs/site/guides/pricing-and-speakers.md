# Pricing and speaker labels

## Cost estimates

`report.cost` is an **estimate** from list prices, not a bill:

- STT from call duration (default: AWS Transcribe streaming),
- TTS from the agent's characters (default: AWS Polly Neural),
- LLM from caller characters in and agent characters out at ~4 characters per
  token (default: GPT-4o mini),
- telephony per minute (default 0).

Use your own rates:

```python
from audiotrace import PricingTable, analyze

pricing = PricingTable(stt_per_minute_usd=0.0043, tts_per_million_chars_usd=30.0,
                       llm_input_per_million_tokens_usd=3.0,
                       llm_output_per_million_tokens_usd=15.0,
                       telephony_per_minute_usd=0.014)
report = analyze("call.wav", num_speakers=2, pricing=pricing)
```

Provider adapters return the provider's own cost as
`metadata["provider_cost_usd"]` when the provider reports it.

## Speaker labels

The agent/caller roles drive latency, frustration, drop-off, intent and the
cost split. AudioTrace recognises these labels (case-insensitive): agent —
`agent`, `AI Agent`, `assistant`, `bot`; caller — `caller`, `Customer`, `user`.

- `num_speakers=2` labels speakers `AI Agent` then `Customer` in order of
  appearance (the agent usually speaks first).
- `speaker_labels=["agent", "caller"]` sets your own, in order of appearance.
- Without `HF_TOKEN`, or with `diarize=False`, speakers are separated by voice
  pitch. `transcript.diarization_confidence` (0–1) says how separable the
  voices were; below 0.5 the call is treated as one speaker rather than
  guessing.
