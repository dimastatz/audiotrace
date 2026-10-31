# Product Requirements (PRDs)

One spec per feature/module. Before implementing a feature, read its PRD; if
none exists, write one first. Keep PRDs small and focused — they're the source
of truth Claude Code and contributors build against.

## Conventions

- File name: `NNNN-short-slug.md` (zero-padded, incrementing).
- Each PRD starts with a status header: `Draft | Approved | In progress | Shipped`.
- Link the PRD from [`../roadmap.md`](../roadmap.md) under the relevant phase.

## Index

| #                                 | Title                               | Status      |
|-----------------------------------|-------------------------------------|-------------|
| [0001](./0001-mediainfo.md)       | MediaInfo extraction                | Shipped     |
| [0002](./0002-transcript.md)      | Transcript and diarization pipeline | Shipped     |
| [0003](./0003-quality.md)         | Quality extraction pipeline         | Shipped     |
| [0004](./0004-sentiment.md)       | Sentiment extraction pipeline       | Shipped     |
| [0005](./0005-events.md)          | Events extraction pipeline          | Shipped     |
| [0006](./0006-latency.md)         | Latency waterfall extraction        | Shipped     |
| [0007](./0007-report.md)          | Report output (JSON + HTML summary) | Shipped     |
| [0008](./0008-regression-gate.md) | Baseline + regression gate (CI)     | Shipped     |
| [0009](./0009-drift-gating.md)    | Drift gating (provenance + PSI/KL)  | Shipped     |
| [0010](./0010-simulated-callers.md) | Simulated callers (pre-release)   | In progress |
| [0011](./0011-production-replay.md) | Production replay (regressions)   | Draft       |
| [0012](./0012-provider-adapters.md) | Provider adapters                 | Shipped       |
| [0013](./0013-compliance-detection.md) | Compliance detection (PII, consent) | Shipped  |
| [0014](./0014-webhook-adapter.md)   | Custom webhook adapter            | Draft       |
| [0015](./0015-docs-site.md)         | Docs site and examples            | Draft       |
