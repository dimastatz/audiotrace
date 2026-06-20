#!/usr/bin/env python3
"""A simple CLI entry point to run AudioTrace analysis on a file."""

import argparse
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

import audiotrace

DEFAULT_FIXTURE = Path("tests/fixtures/paradise_hotel_booking_60s.mp3")

# Custom theme for consistent coloring
theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "section": "bold magenta",
        "key": "blue",
        "value": "white",
    }
)

console = Console(theme=theme)


def print_report(report: audiotrace.models.CallReport) -> None:
    """Print the CallReport in a beautiful, structured format."""

    # 1. Media Info Panel
    if report.media:
        media_table = Table(show_header=False, box=None, padding=(0, 1))
        media_table.add_row("[key]Duration:[/]", f"{report.media.duration_ms}ms")
        media_table.add_row("[key]Codec:[/]", report.media.codec)
        media_table.add_row("[key]Format:[/]", report.media.file_format)
        media_table.add_row("[key]Sample Rate:[/]", f"{report.media.sample_rate_hz}Hz")
        media_table.add_row("[key]Channels:[/]", str(report.media.channels))
        media_table.add_row("[key]Bitrate:[/]", f"{report.media.bitrate_kbps:.2f} kbps")
        media_table.add_row("[key]File Size:[/]", f"{report.media.file_size_bytes} bytes")

        console.print(
            Panel(
                media_table, title="[section]Media Metadata[/]", expand=False, border_style="blue"
            )
        )

    # 2. Main Analysis Summary Table
    main_table = Table(
        title="\n[section]Analysis Summary[/]", show_header=True, header_style="bold cyan"
    )
    main_table.add_column("Section")
    main_table.add_column("Highlights")

    # Quality
    main_table.add_row(
        "Quality",
        f"Score: {report.quality.overall_score:.2f} | "
        f"Interruptions: {report.quality.interruptions}",
    )

    # Sentiment
    sentiment_color = "red" if report.sentiment.caller_frustration else "green"
    main_table.add_row(
        "Sentiment",
        f"Overall: {report.sentiment.overall:.2f} | "
        f"Frustration: [{sentiment_color}]{report.sentiment.caller_frustration}[/]",
    )

    # Latency
    main_table.add_row(
        "Latency",
        f"Total: {report.latency.total_ms}ms "
        f"(STT: {report.latency.stt_ms}ms | LLM: {report.latency.llm_full_response_ms}ms)",
    )

    # Cost
    main_table.add_row("Cost", f"Total: $[success]{report.cost.total_usd:.4f}[/]")

    # Events
    main_table.add_row(
        "Events",
        f"Outcome: {report.events.outcome} | Intent: {report.events.intent_detected or 'N/A'}",
    )

    console.print(main_table)

    # 3. Transcript Preview
    if report.transcript.full_text or report.transcript.turns:
        console.print("\n[section]Transcript Preview[/]")
        if not report.transcript.turns:
            console.print(f"[value]{report.transcript.full_text or '(Empty)'}[/]")
        else:
            for turn in report.transcript.turns[:5]:  # Show first 5 turns
                console.print(f"[key]{turn.speaker}:[/] [value]{turn.text}[/]")
            if len(report.transcript.turns) > 5:
                console.print(f"... and {len(report.transcript.turns) - 5} more turns.")

    # 4. Full Report as prettified, colorized JSON
    console.print("\n[section]Full Report (JSON)[/]")
    console.print_json(report.model_dump_json())


def run_analysis(file_path: str | Path) -> None:
    path = Path(file_path)
    if not path.exists():
        console.print(f"[error]Error: File not found: {path}[/]")
        return

    with console.status(f"[info]Analyzing {path.name}...[/]", spinner="dots"):
        try:
            report = audiotrace.analyze(path)
            console.print(f"\n[success]✓ Analysis Complete:[/] [white]{path}[/]")
            print_report(report)
        except Exception as e:
            console.print(f"[error]Error during analysis: {e}[/]")


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
            console.print("\n" + "━" * console.width)
            user_input = console.input(
                "[bold cyan]Enter path to another audio file (or 'q' to quit): [/]"
            ).strip()
            if user_input.lower() in ("q", "quit", "exit"):
                console.print("[info]Exiting.[/]")
                break
            if not user_input:
                continue
            run_analysis(user_input)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[info]Exiting.[/]")
            break


if __name__ == "__main__":
    main()
