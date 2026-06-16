# AudioTrace Roadmap

High-level milestones and ordering. Each item links to its spec in
[`docs/prd/`](./prd/README.md). Granular tasks live in GitHub Issues, not here —
this file answers *what's next and in what order*.

## Phase 0 — Foundation (current)

- [x] Repo scaffolding: packaging, `src/` layout, tests, CI, Docker
- [x] Public data contract: `CallReport` Pydantic models
- [ ] Core `analyze()` pipeline (MediaInfo) — [PRD 0001](./prd/0001-core-analyze.md)

## Phase 1 — Single-call analysis

- [ ] Core `analyze()` full extractors (Whisper, Librosa)
- [ ] Transcription + speaker diarization (Whisper + pyannote) — [PRD 0002](./prd/0002-transcript.md)
- [ ] Quality signals (silence gaps, interruptions, pace, pitch — Librosa)
- [ ] Latency waterfall extraction
- [ ] Cost attribution model

## Phase 2 — Providers & Intelligence

- [ ] Provider adapters: Vapi, Retell, Twilio, Deepgram, ElevenLabs
- [ ] Sentiment & intent detection (Transformers)

## Phase 3 — Compliance & polish

- [ ] Compliance flag detection (PII, consent gaps)
- [ ] Custom webhook adapter
- [ ] Docs site + examples
