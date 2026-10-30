"""Baseline a folder of calls, then gate a re-run against it — what CI does.

python examples/gate_directory.py [calls_dir]
"""

import shutil
import sys
import tempfile
from pathlib import Path

from _common import SAMPLE_CALL

import audiotrace


def analyze_dir(directory):
    return {p.stem: audiotrace.analyze(p, num_speakers=2) for p in sorted(directory.glob("*.mp3"))}


def main(calls_dir=None):
    with tempfile.TemporaryDirectory() as tmp:
        if calls_dir is None:
            calls_dir = Path(tmp) / "calls"
            calls_dir.mkdir()
            shutil.copy(SAMPLE_CALL, calls_dir / SAMPLE_CALL.name)
        calls_dir = Path(calls_dir)

        baseline_file = audiotrace.write_baseline(analyze_dir(calls_dir), Path(tmp) / "b.json")
        result = audiotrace.check(analyze_dir(calls_dir), audiotrace.load_baseline(baseline_file))
        print(audiotrace.format_result(result))
        return result


if __name__ == "__main__":
    sys.exit(0 if main(*sys.argv[1:2]).passed else 1)
