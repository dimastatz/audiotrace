# CLI

Every command prints `--help`. Exit status is non-zero when a gate fails.

| Command | What it does |
|---|---|
| `audiotrace baseline <dir> -o baseline.json` | Analyze every recording in a folder and write a baseline |
| `audiotrace check <dir> -b baseline.json [--report DIR]` | Re-analyze and gate against the baseline (per-call tolerances + run-level drift) |
| `audiotrace baseline\|check --provider vapi\|retell\|twilio [--call-id ID ...] [--since DATE] [--limit N]` | Same, with calls pulled from a provider |
| `... --policy policy.yaml` | Compliance policy for `baseline` / `check` / `replay ingest` |
| `audiotrace simulate --init [dir]` | Write example scenarios and a custom persona |
| `audiotrace simulate <dir> --target mock\|vapi:<id>\|module:factory [-o DIR] [-b FILE] [--write-baseline FILE]` | Run simulated callers; fails when a task isn't completed |
| `audiotrace serve --mapping mapping.yaml --out DIR [--host H] [--port P]` | Webhook receiver (secret in `$AUDIOTRACE_WEBHOOK_SECRET`) |
| `audiotrace replay ingest --source SRC --rules rules.yaml [--store DIR]` | Capture failing calls as redacted cases |
| `audiotrace replay review` / `approve CASE --reviewer NAME` / `discard CASE` | Review the pending queue |

Environment variables: `HF_TOKEN` (pyannote), `ANTHROPIC_API_KEY`
(simulated callers), `VAPI_API_KEY`, `RETELL_API_KEY`, `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `AUDIOTRACE_CACHE`, `AUDIOTRACE_WEBHOOK_SECRET`.
