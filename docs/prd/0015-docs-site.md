# PRD 0015 — Docs site and examples

**Status:** Shipped (publishing needs GitHub Pages enabled; see below)
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

## Decisions

Resolved 2026-10-30 (were open questions; reversible in review):

- **MkDocs Material + mkdocstrings**: Markdown like the rest of `docs/`, API
  reference from the Google-style docstrings, `mkdocs build --strict`. Note:
  Material for MkDocs reaches end of life on 2027-05-05; its successor,
  Zensical, reads the same `mkdocs.yml`, so migrating later is cheap.
- **GitHub Pages**, deployed by `.github/workflows/docs.yml` on every push to
  `main`, at `https://dimastatz.github.io/audiotrace/` (no custom domain yet).
- **Examples run in a separate CI job** (`examples` in `ci.yml`, real models
  against the bundled call). The unit suite also executes every example with
  `analyze()` stubbed, so wiring breaks fail fast.

## Implementation notes

- Site sources in `docs/site/` (PRDs, vision and articles stay in `docs/`):
  home, getting started, six guides, `CallReport` / Python API / CLI
  references, and a Status page (shipped vs. not).
- `tests/test_docs.py` fails when a `CallReport` field, a public API name, or
  a nav page is missing from the site.
- `examples/`: `analyze_one_call.py`, `compare_two_calls.py`,
  `gate_directory.py`, `custom_pricing.py`, `run_all.py`.
- README: links the site, and no longer shows planned values as real
  (`llm_first_token_ms: 420`, "STT → LLM → TTS breakdown"); the long
  per-field quick start moved to the reference.
- **One-time repo setting:** Settings → Pages → Source: *GitHub Actions*.
  Until then the deploy job fails; the build job still validates every PR.

## Acceptance criteria

- The site builds in CI without warnings and publishes on merge to `main`.
- Every public function and every `CallReport` field appears in the reference.
- Each example in `examples/` runs in CI against the bundled golden call.
- The README links to the site and no longer presents planned features as
  available.
- `./scripts/test_local.sh test` still passes with coverage ≥ 95%.
