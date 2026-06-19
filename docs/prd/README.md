# Product Requirements (PRDs)

One spec per feature/module. Before implementing a feature, read its PRD; if
none exists, write one first. Keep PRDs small and focused — they're the source
of truth Claude Code and contributors build against.

## Conventions

- File name: `NNNN-short-slug.md` (zero-padded, incrementing).
- Each PRD starts with a status header: `Draft | Approved | In progress | Shipped`.
- Link the PRD from [`../roadmap.md`](../roadmap.md) under the relevant phase.

## Index

| #                              | Title                               | Status |
|--------------------------------|-------------------------------------|--------|
| [0001](./0001-mediainfo.md)    | MediaInfo extraction                | Draft  |
| [0002](./0002-transcript.md)   | Transcript and diarization pipeline | Draft  |
| [0003](./0003-quality.md)      | Quality extraction pipeline         | Draft  |
| [0004](./0004-sentiment.md)    | Sentiment extraction pipeline       | Draft  |
| [0005](./0005-events.md)       | Events extraction pipeline          | Draft  |
| [0006](./0006-latency.md)      | Latency waterfall extraction        | Draft  |
