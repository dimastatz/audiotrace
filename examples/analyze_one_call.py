"""Analyze one call and print the highlights.

python examples/analyze_one_call.py [path/to/call.wav]
"""

import sys

from _common import SAMPLE_CALL

import audiotrace


def main(audio=SAMPLE_CALL):
    report = audiotrace.analyze(audio, num_speakers=2)

    for turn in report.transcript.turns:
        print(f"[{turn.start_ms / 1000:6.1f}s] {turn.speaker}: {turn.text}")
    print()
    print(f"quality score      {report.quality.overall_score:.2f}")
    print(f"sentiment          {report.sentiment.overall:+.2f}")
    print(f"caller frustrated  {report.sentiment.caller_frustration}")
    gaps = [span.duration_ms for span in report.latency.waterfall]
    print(f"agent response ms  {gaps}")
    print(f"outcome / intent   {report.events.outcome} / {report.events.intent_detected}")
    print(f"compliance         {report.events.compliance_flags or 'none'}")
    print(f"estimated cost     ${report.cost.total_usd:.4f}")
    return report


if __name__ == "__main__":
    main(*sys.argv[1:2])
