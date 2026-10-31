# Providers and webhooks

## Provider adapters

```python
import audiotrace
from audiotrace.adapters import VapiAdapter   # also RetellAdapter, TwilioAdapter

adapter = VapiAdapter()                      # VAPI_API_KEY from the environment
call = adapter.fetch_call("abc123")          # downloads once, then reuses the cache
report = audiotrace.analyze(call.audio, call.metadata, num_speakers=2)

for call_id in adapter.list_calls(limit=20):   # newest first
    ...
```

| Provider | Class | Credentials | Call ids |
|---|---|---|---|
| Vapi | `VapiAdapter` | `VAPI_API_KEY` | call ids |
| Retell | `RetellAdapter` | `RETELL_API_KEY` | call ids |
| Twilio | `TwilioAdapter` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Recording SIDs (`RE…`) |

`call.metadata` has the same keys for every provider — `call_id`, `provider`,
`agent_id`, `agent_version`, `started_at`, `ended_reason`, `provider_cost_usd`
— with `None` where a provider doesn't report one. Provider cost stays in
metadata; the report's `cost` is AudioTrace's own estimate.

Recordings are cached under `~/.cache/audiotrace/recordings/<provider>/` (or
`$AUDIOTRACE_CACHE`) until you delete them; `fetch_call(..., refresh=True)`
downloads again. Adapters use plain HTTPS from the standard library.

From the CLI:

```bash
audiotrace check --provider retell --since 2026-10-01 --limit 50 -b baseline.json
audiotrace baseline --provider vapi --call-id abc --call-id def -o baseline.json
```

!!! note
    The adapters follow each provider's API reference and are tested against
    those response shapes, not live accounts yet. Please open an issue if a
    field comes back different.

## Custom stacks: webhook mapping

Self-hosted LiveKit or Pipecat, your own SIP stack: map your end-of-call event.

```yaml
# mapping.yaml
provider: livekit
recording_headers:
  Authorization: Bearer ${RECORDINGS_TOKEN}          # read from the environment
fields:
  recording_url: $.data.recording.files[0].location   # required
  call_id: $.data.id                                  # required
  agent_version: $.data.metadata.agent_version        # optional
```

```python
from audiotrace.adapters import CustomAdapter

call = CustomAdapter.from_yaml("mapping.yaml").parse(event_json)
```

Paths are a JSONPath subset (`$.a.b[0].c`); from code a field can also be a
function of the payload.

### Built-in receiver

```bash
AUDIOTRACE_WEBHOOK_SECRET=... audiotrace serve --mapping mapping.yaml --out reports/ --port 8080
```

Senders sign the raw body: header `X-AudioTrace-Signature: sha256=<hex
HMAC-SHA256>`. The receiver answers `202` once the signature checks out and the
required fields map (`401`, `400`, `422`, `413` otherwise), then downloads,
analyzes and writes `<call_id>.json` / `.html` in a background worker. It binds
to `127.0.0.1` by default — put it behind your own HTTPS proxy. One worker, no
retries: for volume, call `CustomAdapter.parse()` from your own service.
