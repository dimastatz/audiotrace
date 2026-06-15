#!/usr/bin/env python3
"""A simple CLI entry point to run AudioTrace analysis on a file."""

import argparse
import sys
from pathlib import Path
from pprint import pprint

import audiotrace

DEFAULT_FIXTURE = Path("tests/fixtures/premier_phone_call_30s.mp3")


def main() -> None:
    parser = argparse.ArgumentParser(description="AudioTrace CLI - Analyze audio files.")
    parser.add_argument(
        "file_path",
        type=str,
        nargs="?",
        default=str(DEFAULT_FIXTURE),
        help=f"Path to the audio file (default: {DEFAULT_FIXTURE})",
    )

    args = parser.parse_args()
    path = Path(args.file_path)

    if not path.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing: {path}...")
    try:
        # Ensure we use the absolute path if needed, though analyze() handles both
        report = audiotrace.analyze(path)
        print("\n--- Analysis Result ---")
        pprint(report.model_dump(exclude_none=True), indent=2)
    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
