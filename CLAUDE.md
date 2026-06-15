# AudioTrace — Claude Code guide

AudioTrace is an open-source Python library that turns a raw voice-agent call
recording into a structured, queryable `CallReport` (transcript, quality,
sentiment, latency, cost, events). It is the shared signal-extraction layer
that voice-AI teams otherwise rebuild from scratch.

Status: early. The public data contract exists; the extraction pipeline is a
stub. Most work right now is building that pipeline and provider adapters.

## Repository layout

```
src/audiotrace/        # the library (src layout)
  __init__.py          # public API: analyze(), batch(), models, __version__
  core.py              # analyze() / batch() entry points
  extractors.py        # FFmpeg/ffprobe extraction logic
  models.py            # Pydantic CallReport and sub-models — the stable contract
tests/                 # pytest suite
docs/
  vision/              # why this exists (product vision, problem statement)
  prd/                 # what we build — one spec per feature, see docs/prd/README.md
  roadmap.md           # when — phases and ordering
docker/                # Dockerfiles for testing and production
scripts/               # Automation scripts
run.sh                 # Local CLI runner
.github/workflows/     # CI
```

## Commands

```bash
# Setup
pip install -e ".[dev]"   # install library + dev tooling

# Validation (Definition of Done)
./scripts/test_local.sh test  # format, lint, type-check, and test (100% coverage)

# Running locally
./run.sh [file_path]      # analyze a file interactively

# Reproduce CI locally (mirrors GitHub Actions exactly):
docker build -f docker/Dockerfile.test -t audiotrace-test .
docker run --rm audiotrace-test  # Runs ./scripts/test_local.sh no-venv
```

## Working agreements

- **Read the PRD before building a feature.** Specs live in `docs/prd/`;
  priorities and ordering in `docs/roadmap.md`. If a feature has no PRD, write
  one (or ask) before implementing.
- **`models.py` is a public contract.** Changing field names/shapes is a
  breaking change — call it out and update the README's CallReport tree to match.
- **The library targets Python 3.9+** (ruff/mypy are pinned to `py39`), even
  though CI runs on a single 3.12 image. Avoid 3.10+-only syntax.
- **FFmpeg is a system dependency.** It's installed in the test image; assume it
  exists at runtime, don't reimplement audio decoding.
- **Definition of Done: Keep CI green.** Before finishing any change, you **must** run `./scripts/test_local.sh test`. This script handles formatting, linting, type-checking, and testing. Direct use of `pytest` is discouraged for final validation. Test coverage must stay ≥ 95% (enforced by the script and `pyproject.toml`) — new code needs tests.
