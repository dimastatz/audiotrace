# AudioTrace pilot agreement

*A short, plain-English agreement for a paid design-partner pilot. Fill the
brackets, delete this line, and it's ready to sign. Not legal advice — have
counsel review before relying on it.*

**Between:** AudioTrace ("Provider", contact dima.statz@gmail.com)
**And:** `[Customer legal name]` ("Customer")
**Effective date:** `[date]`

## 1. What Provider does

Provider sets up and operates the AudioTrace regression gate + quality dashboard
for up to `[N]` of Customer's voice agents:

- Turn Customer's golden call recordings into a committed baseline.
- Gate changes in Customer's CI against that baseline (quality, sentiment,
  latency, drop-off, compliance) and deliver per-call + run-over-run reports.
- Maintain it during the term — tune tolerances, add fixtures, respond to drift.
- Support via `[email / shared Slack]`, best-effort, within `[1 business day]`.

## 2. Term & cancellation

Month-to-month, starting on the effective date. Either party may cancel with
`[14]` days' written notice, effective at the end of the current paid month.

## 3. Fee

**`$[750]` per month**, invoiced monthly in advance via Stripe, due net `[15]`
days. Fees are non-refundable for a month already started.

## 4. Data

- Customer provides call recordings and grants Provider the right to process
  them solely to deliver the services.
- Provider deletes Customer recordings and derived data within `[30]` days of
  the term ending, or sooner on written request.
- Each party keeps the other's non-public information confidential and uses it
  only for this pilot.

## 5. Intellectual property

- The AudioTrace library is and remains MIT-licensed; nothing here changes that.
- Customer owns its recordings and the reports Provider generates from them.
- Provider owns the tooling, methods, and any improvements to AudioTrace.

## 6. Early-access reality

The service is provided **"as is"** during the pilot. Provider makes no
warranties. Each party's total liability under this agreement is capped at the
fees paid in the `[3]` months before the claim. Neither party is liable for
indirect or consequential damages. Nothing here is exclusive — either party may
work with anyone.

## 7. Governing law

`[State / country]`, without regard to conflict-of-laws rules.

---

**Provider** — AudioTrace  &nbsp;&nbsp; Signature: ____________  Date: ______

**Customer** — `[name, title]`  &nbsp;&nbsp; Signature: ____________  Date: ______
