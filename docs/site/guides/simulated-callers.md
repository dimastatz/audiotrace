# Simulated callers

Test an agent *before* release by having AudioTrace call it. Claude plays the
caller, Kokoro voices it locally, the call is recorded and analyzed like any
other, and each scenario gets a task-completion verdict.

```bash
pip install "audiotrace[simulate]"     # Python 3.10–3.12; macOS: brew install espeak-ng
export ANTHROPIC_API_KEY=...
audiotrace simulate --init scenarios   # example scenarios + a custom persona
audiotrace simulate scenarios --target mock
```

## Scenarios

```yaml
name: reschedule-appointment
goal: Move my Tuesday 3pm appointment to Thursday morning.
persona: interrupter        # neutral | frustrated | heavy_accent | interrupter | silent | your own
noise: cafe                 # clean | cafe | street | car | bad_line | your own
max_turns: 12
hints:
  - Your name is Sam Rivera.
success:
  outcome: completed
  intent: general inquiry
  must_mention: ["Thursday"]
  judge: The agent confirmed a specific new time on Thursday morning.   # optional, graded by Claude
```

`outcome`, `intent` and `must_mention` are checked by rules against the
report; `judge` (optional) is a free-text criterion Claude grades from the
transcript. Every set criterion must hold.

Custom personas go in `personas/*.yaml` (`name`, `style`, Kokoro `voice`,
`speed`, `barge_in`, `response_delay_ms`); custom noise in `noise/*.yaml`
(`kind: white | pink | brown | file`, `file`, `snr_db`, `band`).

## Targets

| `--target` | What it calls |
|---|---|
| `mock` | the scenario's `mock:` script (greeting, replies, reply delay) — no agent needed |
| `vapi:<assistant_id>` | a Vapi assistant over Vapi's WebSocket transport (`VAPI_API_KEY`) |
| `my_module:make_target` | your own: a function taking a scenario and returning an object with `start(scenario)`, `respond(caller_audio, caller_text)`, `close()` |

Retell and SIP targets aren't available yet (Retell web calls only connect
through Retell's WebRTC client; SIP needs a SIP/RTP stack).

## Results and gating

Each call is saved as stereo WAV (caller left, agent right) with JSON + HTML
reports in `--output` (default `simulations/`); `report.simulation` holds the
verdict. The command exits non-zero when any scenario fails. Reports are keyed
by scenario name, so a normal baseline gates them too:

```bash
audiotrace simulate scenarios --target vapi:asst_123 --write-baseline sim-baseline.json
audiotrace simulate scenarios --target vapi:asst_123 -b sim-baseline.json
```

In the GitHub Action:

```yaml
      - uses: dimastatz/audiotrace@main   # use a release that includes `scenarios`
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          VAPI_API_KEY: ${{ secrets.VAPI_API_KEY }}
        with:
          scenarios: tests/scenarios
          target: vapi:${{ vars.STAGING_ASSISTANT_ID }}
```

The caller and judge default to `claude-opus-5-5` (`--caller-model`,
`--judge-model` to change).
