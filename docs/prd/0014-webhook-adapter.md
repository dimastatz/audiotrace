# PRD 0014 — Custom webhook adapter

**Status:** Draft
**Owner:** Dima Statz
**Related:** [roadmap Phase 3](../roadmap.md),
[PRD 0012 (provider adapters)](./0012-provider-adapters.md),
[PRD 0011 (production replay)](./0011-production-replay.md)

## Summary

Teams on custom stacks (self-hosted LiveKit or Pipecat, their own SIP, or a
provider with no adapter yet) can't use [provider adapters](./0012-provider-adapters.md).
They already emit an "end of call" event with a recording URL and some
metadata — but the shape is theirs.

The custom webhook adapter accepts those events, maps any payload shape to the
normalized adapter output, and runs `analyze()` on the recording. The README
lists it as `CustomAdapter` (TBD).

## Goals

- **`CustomAdapter`** — same interface as [PRD 0012](./0012-provider-adapters.md)'s
  `BaseAdapter`, configured with a field mapping instead of an API client:

  ```yaml
  recording_url: $.data.recording.url
  call_id: $.data.id
  agent_version: $.data.metadata.agent_version
  started_at: $.data.started_at
  ```

- **`parse(payload) -> ProviderCall`** — download the recording from the
  mapped URL, return audio + normalized metadata.
- **Optional receiver** — `audiotrace serve` runs a small HTTP endpoint that
  accepts webhook POSTs, verifies a shared-secret signature, and writes a
  report per call to a directory (or hands it to
  [production replay](./0011-production-replay.md)).
- **Library-first** — teams with an existing web service call
  `CustomAdapter.parse()` from their own handler instead of running the
  receiver.

## Non-goals

- **A hosted endpoint.** AudioTrace doesn't run infrastructure for users.
- **A job queue, retries, or scale-out.** The receiver handles modest volume;
  heavy users call the library from their own workers.
- **Recordings that need custom auth flows** beyond a static header/token.

## Open questions

- Is the built-in receiver worth shipping at all, or is `parse()` plus an
  example handler enough?
- Field mapping syntax — JSONPath, dotted paths, or a Python callable?
- Should `analyze()` run synchronously in the request, or should the receiver
  answer immediately and analyze in the background?

## Acceptance criteria

- `CustomAdapter.parse()` maps sample payloads from at least two different
  shapes to the normalized metadata keys from PRD 0012.
- Missing mapped fields produce clear errors; optional ones are skipped.
- If the receiver ships: requests with a bad or missing signature are
  rejected, and a valid request produces a report file.
- No network calls in tests (recording download mocked).
- `./scripts/test_local.sh test` passes with coverage ≥ 95%.
