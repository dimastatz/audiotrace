# Status

What ships today and what doesn't. Specs live in
[`docs/prd/`](https://github.com/dimastatz/audiotrace/tree/main/docs/prd).

| Feature | Status |
|---|---|
| `analyze()`: media, transcript + diarization, quality, sentiment, cost, events | ✅ Shipped |
| Agent response latency waterfall | ✅ Shipped |
| LLM / TTS stage timings (`llm_first_token_ms`, `tts_ms`) | ⏳ Not measurable from audio; reserved for provider data |
| HTML + JSON reports, regression gate, GitHub Action | ✅ Shipped |
| Extraction-stack provenance, run-level PSI drift gate | ✅ Shipped |
| Compliance: agent disclosure window, PII (US/UK/EU), masked located findings | ✅ Shipped |
| Compliance: names / NER | ❌ Not planned for now (rules only) |
| Provider adapters: Vapi, Retell, Twilio | ✅ Shipped — tested against documented API shapes, not live accounts |
| Provider adapters: Deepgram, ElevenLabs | ❌ Not planned as adapters |
| Custom webhook adapter + `audiotrace serve` | ✅ Shipped |
| Simulated callers: framework, mock and Vapi targets, Action input | ✅ Shipped — Vapi target not yet run against a live assistant |
| Simulated callers: Retell and SIP targets | ⛔ Blocked (Retell needs its WebRTC client; SIP needs a SIP/RTP stack) |
| Production replay: ingest, rules, dedupe, redaction, review | ✅ Shipped |
| Production replay: automatic scenario replay against a new agent | ⏳ Not yet |
| Caller frustration accuracy | ⚠️ Over-triggers: the sentiment model scores neutral questions as negative |
