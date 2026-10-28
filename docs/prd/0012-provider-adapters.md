# PRD 0012 — Provider adapters

**Status:** Draft
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

## Open questions

- Should provider-reported cost and transcripts populate `CallReport.cost` /
  `transcript`, or stay in metadata alongside AudioTrace's own estimates? The
  first is a `models.py` contract change.
- Where are downloaded recordings cached, and for how long?
- Plain HTTP client vs. each provider's SDK (fewer dependencies vs. less code)?
- Is Deepgram/ElevenLabs support worth a full adapter, or just a pricing /
  usage import?

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
