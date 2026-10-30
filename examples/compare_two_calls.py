"""Compare two calls metric by metric (e.g. before and after a prompt change).

python examples/compare_two_calls.py before.wav after.wav
"""

import sys

from _common import SAMPLE_CALL

import audiotrace


def main(before=SAMPLE_CALL, after=SAMPLE_CALL):
    base = audiotrace.analyze(before, num_speakers=2)
    current = audiotrace.analyze(after, num_speakers=2)
    deltas = audiotrace.diff(base, current)
    for delta in deltas:
        mark = "worse" if delta.regressed else ""
        print(f"{delta.label:28} {delta.before:>10g} → {delta.after:<10g} {mark}")
    return deltas


if __name__ == "__main__":
    main(*sys.argv[1:3])
