# PRD 0012 — Provider adapters

**Status:** Shipped (Vapi, Retell, Twilio); Deepgram/ElevenLabs not planned as adapters
**Owner:** Dima Statz
**Related:** [roadmap Phase 2](../roadmap.md),
[PRD 0010 (simulated callers)](./0010-simulated-callers.md),
[PRD 0011 (production replay)](./0011-production-replay.md),
[PRD 0014 (custom webhook adapter)](./0014-webhook-adapter.md)

## Summary

Today `analyze()` only takes a local audio file, and `metadata={"provider": …}`
is a free-form tag. Every team has to write its own glue to download the
recording from Vapi, Retell, or Twilio, and the report ignores data the provider
already has — real per-component cost, call IDs, agent version, end reason,
provider-side transcripts.

Provider adapters fetch a call from a provider's API and turn it into
`analyze()` input: a local recording plus normalized metadata. The README
already advertises the API (`from audiotrace.adapters import VapiAdapter`) and
the `audiotrace[vapi|retell|twilio|elevenlabs|deepgram]` extras; both are
placeholders.

## Goals

- **Common interface** — `audiotrace.adapters.BaseAdapter` with:
  - `fetch_call(call_id) -> ProviderCall` (`audio: Path`, `metadata: dict`)
  - `list_calls(since=..., limit=...) -> Iterator[str]` (call IDs), used by
    [production replay](./0011-production-replay.md)
- **Adapters, in order:** Vapi, Retell (voice-agent platforms; most target
  users), Twilio (telephony recordings), then Deepgram and ElevenLabs (STT/TTS
  providers — mainly for usage/cost data rather than recordings).
- **Normalized metadata** — the same keys from every adapter where available:
  `call_id`, `provider`, `agent_id`, `agent_version`, `started_at`,
  `ended_reason`, `provider_cost_usd`.
- **CLI support** — `audiotrace check` / `baseline` can pull calls by ID from
  a provider, not just from a local directory.
- **Extras stay optional** — each adapter's SDK installs only with its extra;
  importing `audiotrace` without extras keeps working.
- README "Provider support" table moves from TBD to real status per adapter.

## Non-goals

- **Placing calls.** Outbound/simulated calls are
  [PRD 0010](./0010-simulated-callers.md); adapters here only read.
- **Real-time streaming** of live calls.
- **Writing back** to providers (tags, annotations).
- **Replacing AudioTrace's own analysis** with provider transcripts or scores.

## Decisions

Resolved 2026-10-30 (were open questions; conservative choices, reversible in
review):

- **Provider cost and transcripts stay in metadata.** `ProviderCall.metadata`
  carries `provider_cost_usd` etc.; `CallReport` is unchanged (no contract
  change), and AudioTrace's own transcript and cost estimate stay the source
  of truth in reports.
- **Cache:** `~/.cache/audiotrace/recordings/<provider>/<call_id>.<ext>`
  (`$AUDIOTRACE_CACHE` or `cache_dir=` overrides), kept until deleted;
  `fetch_call(..., refresh=True)` re-downloads. Downloads are written to a
  `.part` file and renamed, so a failed download never leaves a broken file.
- **Plain HTTP (urllib), no SDKs.** No new dependencies; the `vapi`, `retell`,
  `twilio`, `elevenlabs`, `deepgram` extras become no-op aliases.
- **Deepgram / ElevenLabs: no adapter.** They don't hold call recordings; if
  needed later, a usage/pricing import into `PricingTable` is enough.

## Implementation notes

- `audiotrace.adapters`: `BaseAdapter` (`fetch_call`, `list_calls`),
  `VapiAdapter`, `RetellAdapter`, `TwilioAdapter`, `get_adapter`,
  `fetch_calls`, `ProviderCall`, `AdapterError`, `METADATA_KEYS`.
- Endpoints, from the providers' API references (checked 2026-10-30):
  Vapi `GET /call/{id}`, `GET /call?createdAtGt&createdAtLt&limit` (paged
  backwards by creation time, assuming newest-first order); Retell
  `GET /v2/get-call/{id}`, `POST /v3/list-calls` (`items`, `has_more`,
  `pagination_key`; cost in cents); Twilio Recording resource,
  `Recordings.json?DateCreated>=&PageSize`, media at `<uri>.wav` with Basic
  auth.
- Vapi recording URL preference: `artifact.recording.mono.combinedUrl`, then
  `stereoUrl`, then the deprecated `artifact.recordingUrl` /
  `stereoRecordingUrl` / top-level `recordingUrl`.
- CLI: `audiotrace baseline|check --provider vapi|retell|twilio` with
  `--call-id` (repeatable) or `--since` / `--limit`; reports keyed by call id.
- **Not verified against live accounts yet** — tests use the documented
  response shapes.

## Acceptance criteria

- `BaseAdapter` and the Vapi and Retell adapters exist, each covered by tests
  against recorded/mocked API responses — no network calls in CI.
- `fetch_call` returns a recording that `analyze()` accepts and metadata with
  the normalized keys.
- Missing credentials and unknown call IDs raise clear errors.
- `import audiotrace` works with no extras installed.
- README install, quick start, and "Provider support" sections match what
  shipped.
- `./scripts/test_local.sh test` passes with coverage ≥ 95%.
