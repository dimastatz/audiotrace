# PRD 0015 — Docs site and examples

**Status:** Draft
**Owner:** Dima Statz
**Related:** [roadmap Phase 3](../roadmap.md),
[articles](../articles/)

## Summary

All user documentation lives in one long `README.md`. It mixes working
features with planned ones (the provider-adapter example is illustrative only),
has no API reference, and has no runnable examples. The article series explains
the "why" well, but a developer evaluating AudioTrace can't quickly find how
to do one specific thing.

This PRD covers a hosted docs site and an `examples/` folder.

## Goals

- **Docs site** with:
  - Getting started — install (including FFmpeg and the HF token for
    diarization), analyze a first call, read the report.
  - Guides — regression gate in CI, the GitHub Action, tuning tolerances,
    pricing tables, speaker labels without diarization.
  - `CallReport` reference — every field, its unit, and how it's computed.
  - API reference generated from docstrings (`analyze()`, `check`,
    `report`, CLI).
  - A clear "planned vs. shipped" status for each feature.
- **`examples/`** — small runnable scripts and a sample workflow, each using
  the bundled golden call, e.g. analyze one call, compare two calls, gate a
  directory in CI, custom pricing.
- **Built and published from CI** on every merge to `main`, so docs can't fall
  behind the code.
- **Examples tested in CI** so they can't break silently.
- README shortened to an overview that links to the site.

## Non-goals

- **Versioned docs per release** — one "latest" version until there's a need.
- **Translations.**
- **Moving PRDs, vision docs, or articles** to the site — they stay in
  `docs/` as contributor material.

## Open questions

- Tooling — MkDocs (Material) + mkdocstrings, or Sphinx?
- Hosting — GitHub Pages or Read the Docs, and on what domain?
- Should examples run in the regular test suite (slower, model downloads) or
  in a separate CI job?

## Acceptance criteria

- The site builds in CI without warnings and publishes on merge to `main`.
- Every public function and every `CallReport` field appears in the reference.
- Each example in `examples/` runs in CI against the bundled golden call.
- The README links to the site and no longer presents planned features as
  available.
- `./scripts/test_local.sh test` still passes with coverage ≥ 95%.
