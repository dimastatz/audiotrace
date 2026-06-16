#!/usr/bin/env python3
"""A simple CLI entry point to run AudioTrace analysis on a file."""

import argparse
import json
import logging
from pathlib import Path

from rich.console import Console

import audiotrace

DEFAULT_FIXTURE = Path("tests/fixtures/premier_phone_call_30s.mp3")

# Setup logging to avoid cluttering stdout
logging.basicConfig(level=logging.WARNING)

console = Console()


def print_report_json(report: audiotrace.models.CallReport) -> None:
    """Print the CallReport as prettified JSON."""
    # Convert Pydantic model to dict, then to pretty JSON string
    report_dict = report.model_dump()
    print(json.dumps(report_dict, indent=2))


def run_analysis(file_path: str | Path) -> None:
    path = Path(file_path)
    if not path.exists():
        console.print(f"[bold red]Error:[/] File not found: {path}", style="red")
        return

    try:
        # We don't use console.status here to keep stdout clean for JSON
        report = audiotrace.analyze(path)
        print_report_json(report)
    except Exception as e:
        console.print(f"[bold red]Error during analysis:[/] {e}", style="red")


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

    # Run analysis
    run_analysis(args.file_path)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
