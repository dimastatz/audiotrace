# Production replay

Turn failing production calls into regression tests, with PII removed before
anything is stored.

```yaml
# rules.yaml
rules:
  - name: low-quality
    when: quality.overall_score < 0.6
  - name: frustrated-caller
    when: sentiment.caller_frustration
  - name: compliance
    when: events.compliance_flags
```

```bash
pip install "audiotrace[replay]"      # only for S3 / GCS sources
audiotrace replay ingest --source s3://my-bucket/calls --rules rules.yaml
audiotrace replay review
audiotrace replay approve <case> --reviewer dana
audiotrace check replay/suite -b replay/suite/baseline.json
```

## Pipeline

1. **Ingest** from a directory, `s3://bucket/prefix`, `gs://bucket/prefix`, or
   a provider (`vapi`, `retell`, `twilio` with `--since` / `--limit`). Only
   calls not seen before are analyzed (`replay/state.json`).
2. **Rules**: `<field.path>` (true when set) or `<field.path> <op> <literal>`
   with `< <= > >= == !=` and numbers, `true`/`false`, `null`, or quoted
   strings. Paths are checked against the [CallReport](../reference/callreport.md)
   schema when the rules load.
3. **Dedupe**: calls failing the same way (rule + failure type + intent) become
   one case with a count.
4. **Redact**: every turn with detected PII, a self-introduced name ("my name
   is …"), or a short number given right after a request for a security code,
   CVV or PIN is replaced and its audio silenced. The result is scanned again;
   a case that still shows PII is refused.
5. **Review**: cases wait in `replay/pending/`. `approve` copies the redacted
   recording to `replay/suite/` and its report into
   `replay/suite/baseline.json`; `discard` deletes it.

Point the regression gate or the GitHub Action's `calls` input at
`replay/suite` to re-check approved cases on every release.

## Limits

Redaction is only as good as the detector: names mentioned in passing and PII
forms it doesn't know survive. Re-analysis catches *measurement* drift; turning
a case into a simulated-caller scenario that replays it against a new agent
isn't automated yet.
