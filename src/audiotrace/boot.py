#!/usr/bin/env python3
"""A simple CLI entry point to run AudioTrace analysis on a file."""

import argparse
import sys
from pathlib import Path
from pprint import pprint

import audiotrace

DEFAULT_FIXTURE = Path("tests/fixtures/premier_phone_call_30s.mp3")


def run_analysis(file_path: str | Path) -> None:
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        return

    print(f"\nAnalyzing: {path}...")
    try:
        report = audiotrace.analyze(path)
        print("\n--- Analysis Result ---")
        pprint(report.model_dump(exclude_none=True), indent=2)
    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)


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
    
    # First analysis from CLI arg
    run_analysis(args.file_path)

    # Interactive loop
    while True:
        try:
            print("\n" + "="*40)
            user_input = input("Enter path to another audio file (or 'q' to quit): ").strip()
            if user_input.lower() in ("q", "quit", "exit"):
                print("Exiting.")
                break
            if not user_input:
                continue
            run_analysis(user_input)
        except KeyboardInterrupt:
            print("\nExiting.")
            break


if __name__ == "__main__":
    main()
