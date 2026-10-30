# PRD 0013 — Compliance flag detection (PII, consent)

**Status:** Shipped
**Owner:** Dima Statz
**Related:** [roadmap Phase 3](../roadmap.md),
[PRD 0005 (events)](./0005-events.md),
[PRD 0011 (production replay)](./0011-production-replay.md)

## Summary

A first version already shipped as part of [PRD 0005](./0005-events.md):
`events._check_compliance` adds `missing_consent` when no recording disclosure
keyword appears anywhere in the transcript, and `pii_exposed` when a regex
matches a US SSN, a 13–16 digit card number, or an email address.

That is enough for a demo but not for anyone who relies on it:

- **Consent** passes if the word "record" appears anywhere — including the
  caller saying it, or the agent saying it at minute 9.
- **PII** misses phone numbers, names, addresses, dates of birth, account
  numbers, and numbers spoken as words ("four one one one…"), which is how
  they appear in transcripts.
- Flags are **bare strings** — no turn, timestamp, or matched type, so
  nobody can check or act on them.
- Rules are **US-centric and hard-coded**.

This PRD defines what "compliance detection done" means for the Phase 3
roadmap item.

## Goals

- **Consent rule that matches real requirements** — the disclosure must be
  spoken by the agent within a configurable window (e.g. the first N seconds or
  first agent turn).
- **Broader PII coverage** — phone numbers, card numbers (with Luhn check),
  SSNs, emails, dates of birth, street addresses, account numbers; including
  spoken-digit forms.
- **Who exposed it** — distinguish the caller giving PII (often expected) from
  the agent reading it back or asking for it when it shouldn't.
- **Locations** — each finding records the turn index, time range, and PII
  type so the report can point at it.
- **Configurable policies** — enable/disable rules, consent keywords and window,
  and region presets, from code or YAML.
- **Report** — compliance findings shown in the HTML report with links to the
  turns.
- **Reusable for redaction** — the same detector supplies the spans that
  [production replay](./0011-production-replay.md) redacts.

## Non-goals

- **Legal advice or certification** (HIPAA, PCI-DSS, GDPR). AudioTrace flags
  signals; it does not certify compliance.
- **Redacting audio or transcripts** — that belongs to production replay.
- **Sending data to a hosted PII service by default.** Detection runs locally.

## Decisions

Resolved 2026-10-30 (were open questions; chosen as the conservative option,
reversible in review):

- **Contract: additive.** `compliance_flags: list[str]` is unchanged and still
  holds `missing_consent` / `pii_exposed`. The located findings are a new
  `Events.compliance_findings: list[ComplianceFinding]` (type, pii_type,
  masked detail, speaker, role, turn index, time range).
- **Rules only, no NER model.** Keeps the install light and the results
  deterministic. Names are therefore not detected; addresses are matched by a
  number + street-suffix pattern, dates of birth only next to "born" / "date of
  birth" / "birthday".
- **Regions: US (default), UK, EU.** Presets add SSN + phone (US), National
  Insurance number + postcode + phone (UK), IBAN + phone (EU) on top of the
  universal types (card, email, date of birth, address, account).
- **Gate behaviour unchanged.** The regression gate still counts
  `compliance_flags` with zero tolerance; findings add detail, not new gate
  semantics.

## Implementation notes

- `audiotrace.compliance`: `CompliancePolicy` (code or YAML via
  `load_policy`, CLI `--policy`), `find_compliance_issues()`, `normalize()`
  (spoken digits, "double"/"triple", spoken email), Luhn check, masking.
- Consent must be in an *agent* turn starting inside `consent_window_ms`
  (default 30 s; `null` = anywhere). If no turn has a recognizable agent label,
  any speaker counts, since roles are unknown.
- Masked values keep only the last two characters, so reports never repeat
  the PII they found. Production replay can reuse the turn/time ranges for
  redaction.
- Recognition damage is handled where the context is explicit: a Luhn-valid
  card number inside a longer digit run when the turn mentions a card, a
  10-digit SSN when it mentions "social security", "name at domain com"
  without the "dot". On the golden set that takes PII from 18/20 to 20/20
  with no false positives. The flip side: a long number read out right after
  "card" is flagged even if it isn't a valid card on its own.

## Acceptance criteria

- `missing_consent` is raised when the disclosure is absent from the agent's
  turns in the configured window, even if the caller says "record".
- Each supported PII type is detected in both digit and spoken-word forms
  in tests, and card numbers that fail a Luhn check are ignored.
- Every finding carries a turn index, time range, PII type, and speaker.
- Existing `compliance_flags` values keep working for current users unless a
  breaking change is explicitly approved.
- `./scripts/test_local.sh test` passes with coverage ≥ 95%.
