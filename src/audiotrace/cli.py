"""``audiotrace`` console script — regression gating over a folder of recordings.

    audiotrace baseline <calls_dir> -o baseline.json
    audiotrace check    <calls_dir> -b baseline.json [--report DIR]
    audiotrace simulate <scenarios_dir> --target mock [-b baseline.json]
    audiotrace simulate --init [scenarios_dir]

``baseline`` analyzes every recording in ``calls_dir`` and writes a committed
baseline. ``check`` re-analyzes, compares each call against the baseline, writes
a per-call HTML+JSON report, and exits non-zero when a metric drifts past its
tolerance (see :mod:`audiotrace.check`). ``simulate`` places scripted synthetic
calls against an agent and fails when a scenario's task isn't completed (see
:mod:`audiotrace.simulate`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import audiotrace
from audiotrace.check import check, format_result, load_baseline, write_baseline
from audiotrace.models import CallReport

# Extensions FFmpeg-readable enough to treat as call recordings.
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".opus"}


def _analyze_dir(calls_dir: str) -> dict[str, CallReport]:
    """Analyze every recording in a directory, keyed by file stem."""
    directory = Path(calls_dir)
    if not directory.is_dir():
        raise SystemExit(f"Not a directory: {directory}")
    reports: dict[str, CallReport] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() in AUDIO_EXTS:
            print(f"Analyzing {path.name} ...", file=sys.stderr)
            reports[path.stem] = audiotrace.analyze(path, num_speakers=2)
    if not reports:
        raise SystemExit(f"No recordings found in {directory}")
    return reports


def _baseline_cmd(args: argparse.Namespace) -> int:
    reports = _analyze_dir(args.calls_dir)
    out = write_baseline(reports, args.output)
    print(f"Wrote baseline for {len(reports)} call(s) → {out}")
    return 0


def _check_cmd(args: argparse.Namespace) -> int:
    baseline = load_baseline(args.baseline)
    current = _analyze_dir(args.calls_dir)

    if args.report:
        for call_id, report in current.items():
            audiotrace.write_report(
                report, args.report, baseline=baseline.get(call_id), stem=call_id
            )
        print(f"Wrote reports → {args.report}")

    result = check(current, baseline)
    print(format_result(result))
    return 0 if result.passed else 1


def _simulate_cmd(args: argparse.Namespace) -> int:
    from audiotrace import simulate as sim

    if args.init:
        written = sim.init_scenarios(args.scenarios_dir)
        for path in written:
            print(f"Wrote {path}")
        print(f"Next: audiotrace simulate {args.scenarios_dir} --target mock")
        return 0

    from audiotrace.simulate_backends import (
        ClaudeCaller,
        ClaudeJudge,
        KokoroSpeech,
        WhisperListener,
    )

    try:
        suite = sim.load_suite(args.scenarios_dir)
        speech = KokoroSpeech()
        factory = (
            sim.mock_target_factory(speech)
            if args.target == "mock"
            else sim.load_target_factory(args.target)
        )
        simulator = sim.Simulator(
            caller=ClaudeCaller(model=args.caller_model),
            speech=speech,
            listener=WhisperListener(),
            judge=ClaudeJudge(model=args.judge_model) if suite.needs_judge() else None,
        )
        reports = sim.run_suite(suite, simulator, factory, args.output)
    except sim.SimulationError as exc:
        raise SystemExit(f"audiotrace simulate: {exc}") from exc

    for name, report in reports.items():
        audiotrace.write_report(report, args.output, stem=sim.safe_name(name))
    print(f"Wrote recordings and reports → {args.output}")
    if args.write_baseline:
        print(f"Wrote baseline → {write_baseline(reports, args.write_baseline)}")

    print(sim.format_verdicts(reports))
    passed = not sim.failed_scenarios(reports)
    if args.baseline:
        result = check(reports, load_baseline(args.baseline))
        print(format_result(result))
        passed = passed and result.passed
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audiotrace",
        description="Regression-gate your voice agent against a committed baseline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    base = sub.add_parser("baseline", help="Analyze a folder of calls and write a baseline.")
    base.add_argument("calls_dir", help="Directory of call recordings.")
    base.add_argument("-o", "--output", default="baseline.json", help="Baseline file to write.")
    base.set_defaults(func=_baseline_cmd)

    chk = sub.add_parser("check", help="Gate a folder of calls against a baseline.")
    chk.add_argument("calls_dir", help="Directory of call recordings.")
    chk.add_argument("-b", "--baseline", default="baseline.json", help="Baseline file to read.")
    chk.add_argument("--report", metavar="DIR", default=None, help="Write per-call reports here.")
    chk.set_defaults(func=_check_cmd)

    simu = sub.add_parser("simulate", help="Place simulated calls against an agent.")
    simu.add_argument(
        "scenarios_dir", nargs="?", default="scenarios", help="Directory of scenario YAML files."
    )
    simu.add_argument("--init", action="store_true", help="Write example scenarios and exit.")
    simu.add_argument(
        "--target", default="mock", help="'mock' (each scenario's mock script) or module:factory."
    )
    simu.add_argument(
        "-o", "--output", default="simulations", help="Directory for recordings and reports."
    )
    simu.add_argument("-b", "--baseline", default=None, help="Also gate against this baseline.")
    simu.add_argument("--write-baseline", metavar="FILE", default=None, help="Write a baseline.")
    simu.add_argument("--caller-model", default="claude-opus-5-5", help="Claude model for callers.")
    simu.add_argument("--judge-model", default="claude-opus-5-5", help="Claude model for judging.")
    simu.set_defaults(func=_simulate_cmd)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
