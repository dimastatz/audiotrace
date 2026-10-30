# Python API

Generated from the docstrings.

## Analysis

::: audiotrace.analyze

::: audiotrace.PricingTable

## Reports

::: audiotrace.write_report

::: audiotrace.render_json

::: audiotrace.render_html

::: audiotrace.summarize

::: audiotrace.diff

## Regression gate

::: audiotrace.check.check

::: audiotrace.CheckResult

::: audiotrace.Threshold

::: audiotrace.write_baseline

::: audiotrace.load_baseline

::: audiotrace.format_result

::: audiotrace.drift.drift

## Provenance

::: audiotrace.collect_provenance

::: audiotrace.provenance_changes

## Compliance

::: audiotrace.CompliancePolicy

::: audiotrace.find_compliance_issues

::: audiotrace.load_policy

## Provider adapters

::: audiotrace.adapters
    options:
      members: [BaseAdapter, VapiAdapter, RetellAdapter, TwilioAdapter, CustomAdapter, ProviderCall, get_adapter, fetch_calls, AdapterError]

## Webhook receiver

::: audiotrace.webhook
    options:
      members: [WebhookApp, make_server, serve, sign, verify]

## Simulated callers

::: audiotrace.simulate
    options:
      members: [Scenario, Persona, NoiseProfile, SuccessCriteria, Simulator, Target, MockTarget, load_suite, run_suite, evaluate]

::: audiotrace.simulate_targets
    options:
      members: [VapiTarget, resolve_target]

## Production replay

::: audiotrace.replay
    options:
      members: [Rule, load_rules, Store, open_source, redact_transcript, redact_audio]
