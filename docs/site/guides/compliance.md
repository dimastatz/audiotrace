# Compliance checks

Every report checks two things, locally, with rules:

- **Recording disclosure** — the *agent* must mention recording, monitoring or
  consent within the first 30 seconds. A caller asking "is this recorded?"
  doesn't count.
- **Exposed PII** — card numbers (Luhn-checked), SSNs, phone numbers, emails,
  dates of birth, street addresses, account numbers; UK (`ni_number`,
  `postcode`) and EU (`iban`) presets.

Transcripts write numbers the way people say them, so text is normalized
first: "four one one one", "double five", "jo dot lee at example dot com".
Common speech-recognition damage is handled where the turn makes the context
explicit (a valid card number inside a longer digit run after "card", a
10-digit SSN after "social security", "name at domain com" without the "dot").

## Findings

```python
for f in report.events.compliance_findings:
    print(f.type, f.pii_type, f.speaker, f.role, f.turn_index, f.start_ms, f.detail)
# pii card Customer caller 3 41000 ******************11
```

`detail` holds the matched value **masked** (last two characters kept), so a
report never repeats the PII it found. `events.compliance_flags` keeps the
summary (`missing_consent`, `pii_exposed`), which the regression gate counts.
The HTML report links each finding to its turn.

## Policies

```python
from audiotrace import CompliancePolicy, analyze

policy = CompliancePolicy(consent_window_ms=15_000, regions=("us", "uk"),
                          disabled_pii=("address",), flag_caller_pii=False)
report = analyze("call.wav", num_speakers=2, compliance_policy=policy)
```

Or as YAML for the CLI (`audiotrace baseline|check --policy policy.yaml`):

```yaml
consent_window_ms: 15000        # null = anywhere in the call
consent_keywords: [record, recorded, recording, monitored, consent]
regions: [us, uk]               # us | uk | eu
disabled_pii: [address]
flag_caller_pii: false          # only flag PII the agent says
```

## Limits

Rules only, no named-entity model: names are not detected, addresses only as
"number + street suffix", dates of birth only next to "born" / "date of birth"
/ "birthday". AudioTrace flags signals; it does not certify HIPAA, PCI-DSS or
GDPR compliance.
