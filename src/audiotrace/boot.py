#!/usr/bin/env python3
"""A simple CLI entry point to run AudioTrace analysis on a file."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
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

# Per-speaker accent colors for the transcript / playback.
SPEAKER_STYLES = {"AI Agent": "bold cyan", "Customer": "bold green"}


def _speaker_style(speaker: str) -> str:
    return SPEAKER_STYLES.get(speaker, "bold yellow")


def _group_turns(
    turns: list[audiotrace.models.Turn],
) -> list[list[audiotrace.models.Turn]]:
    """Group consecutive turns from the same speaker (label printed once per group)."""
    groups: list[list[audiotrace.models.Turn]] = []
    for turn in turns:
        if groups and groups[-1][-1].speaker == turn.speaker:
            groups[-1].append(turn)
        else:
            groups.append([turn])
    return groups


def _play_audio(path: str | Path) -> subprocess.Popen[bytes] | None:
    """Start playing an audio file in the background; return the process or None.

    Tries macOS ``afplay`` first, then ``ffplay`` (bundled with FFmpeg).
    """
    players = (
        ["afplay"],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
    )
    for player in players:
        if shutil.which(player[0]):
            try:
                return subprocess.Popen(
                    [*player, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                return None
    return None


def _wait_until(start: float, target_s: float) -> None:
    """Sleep until ``target_s`` seconds have elapsed since ``start`` (monotonic clock)."""
    delay = start + target_s - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def _type_turn(turn: audiotrace.models.Turn, start: float, style: str) -> None:
    """Reveal a turn's words in sync with the audio.

    Uses each word's own timestamp when available (word-level transcription);
    otherwise spreads the words evenly across the turn's [start_ms, end_ms].
    """
    if turn.words:
        for word in turn.words:
            _wait_until(start, word.start_ms / 1000)
            console.print(f"[{style}]{word.text} [/]", end="")
            sys.stdout.flush()
        return

    tokens = turn.text.split()
    if not tokens:
        return
    begin = turn.start_ms / 1000
    duration = max((turn.end_ms - turn.start_ms) / 1000, 0.0)
    for i, token in enumerate(tokens):
        _wait_until(start, begin + duration * i / len(tokens))
        console.print(f"[{style}]{token} [/]", end="")
        sys.stdout.flush()


def _format_ts(ms: int) -> str:
    """Format milliseconds from the call start as M:SS."""
    total_s = int(ms / 1000)
    return f"{total_s // 60}:{total_s % 60:02d}"


def _group_confidence(group: list[audiotrace.models.Turn]) -> float:
    """Mean transcription confidence across the turns in a speaker group."""
    return sum(t.confidence for t in group) / len(group)


def play_conversation(report: audiotrace.models.CallReport, audio_path: str | Path | None) -> None:
    """Play the audio and reveal each word in sync with the speaker, by turn group."""
    console.print("\n[section]▶ Playing call[/]\n")
    proc = _play_audio(audio_path) if audio_path else None
    start = time.monotonic()

    for group in _group_turns(report.transcript.turns):
        speaker = group[0].speaker
        style = _speaker_style(speaker)
        _wait_until(start, group[0].start_ms / 1000)
        console.print(f"[dim]{_format_ts(group[0].start_ms)}[/] [{style}]{speaker}:[/] ", end="")
        sys.stdout.flush()
        for turn in group:
            _type_turn(turn, start, style)
        console.print(f"[dim]({_group_confidence(group):.0%} conf)[/]")

    if proc is not None:
        proc.wait()


def print_transcript(report: audiotrace.models.CallReport) -> None:
    """Print the transcript, one block per speaker turn (consecutive turns merged)."""
    console.print("\n[section]Transcript[/]")
    if not report.transcript.turns:
        console.print(f"[value]{report.transcript.full_text or '(Empty)'}[/]")
        return
    for group in _group_turns(report.transcript.turns):
        speaker = group[0].speaker
        style = _speaker_style(speaker)
        text = " ".join(t.text for t in group)
        ts = _format_ts(group[0].start_ms)
        conf = _group_confidence(group)
        console.print(
            f"[dim]{ts}[/] [{style}]{speaker}:[/] [value]{text}[/] [dim]({conf:.0%} conf)[/]"
        )


def _panel(table: Table, title: str, border: str) -> None:
    console.print(Panel(table, title=f"[section]{title}[/]", expand=False, border_style=border))


def print_summary(report: audiotrace.models.CallReport) -> None:
    """Print a colorful table for each section of the CallReport."""

    # Media
    if report.media:
        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_row("[key]Duration:[/]", f"{report.media.duration_ms}ms")
        t.add_row("[key]Codec:[/]", report.media.codec)
        t.add_row("[key]Format:[/]", report.media.file_format)
        t.add_row("[key]Sample Rate:[/]", f"{report.media.sample_rate_hz}Hz")
        t.add_row("[key]Channels:[/]", str(report.media.channels))
        t.add_row("[key]Bitrate:[/]", f"{report.media.bitrate_kbps:.2f} kbps")
        t.add_row("[key]File Size:[/]", f"{report.media.file_size_bytes} bytes")
        _panel(t, "Media", "blue")

    # Quality
    q = report.quality
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_row("[key]Overall score:[/]", f"{q.overall_score:.2f}")
    t.add_row("[key]Interruptions:[/]", str(q.interruptions))
    t.add_row("[key]Silence gaps:[/]", str(len(q.silence_gaps)))
    t.add_row("[key]Speaking pace:[/]", f"{q.speaking_pace_wpm:.0f} wpm")
    t.add_row("[key]Pitch variance:[/]", f"{q.pitch_variance:.1f} Hz")
    t.add_row("[key]Avg turn length:[/]", f"{q.turn_length_avg_ms:.0f}ms")
    _panel(t, "Quality", "cyan")

    # Sentiment
    s = report.sentiment
    frust = "red" if s.caller_frustration else "green"
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_row("[key]Overall:[/]", f"{s.overall:+.2f}")
    t.add_row("[key]Caller frustration:[/]", f"[{frust}]{s.caller_frustration}[/]")
    t.add_row("[key]Shift points:[/]", str(len(s.shift_points)))
    _panel(t, "Sentiment", "yellow")

    # Cost
    c = report.cost
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_row("[key]STT:[/]", f"${c.stt_usd:.4f}")
    t.add_row("[key]LLM:[/]", f"${c.llm_usd:.4f}")
    t.add_row("[key]TTS:[/]", f"${c.tts_usd:.4f}")
    t.add_row("[key]Telephony:[/]", f"${c.telephony_usd:.4f}")
    t.add_row("[key]Total:[/]", f"[success]${c.total_usd:.4f}[/]")
    _panel(t, "Cost", "green")

    # Latency (incl. agent-response waterfall)
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_row("[key]STT:[/]", f"{report.latency.stt_ms}ms")
    t.add_row("[key]Pipeline total:[/]", f"{report.latency.total_ms}ms")
    for span in report.latency.waterfall:
        t.add_row(f"[key]{span.name}:[/]", f"{span.duration_ms}ms @ {span.start_ms / 1000:0.1f}s")
    _panel(t, "Latency", "magenta")

    # Events
    e = report.events
    drop = f"{e.drop_off}" + (f" (turn {e.drop_off_turn})" if e.drop_off_turn is not None else "")
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_row("[key]Outcome:[/]", e.outcome)
    t.add_row("[key]Drop-off:[/]", drop)
    t.add_row("[key]Intent:[/]", e.intent_detected or "N/A")
    t.add_row("[key]Failure type:[/]", e.failure_type or "none")
    t.add_row("[key]Compliance:[/]", ", ".join(e.compliance_flags) or "none")
    _panel(t, "Events", "red")


def print_json(report: audiotrace.models.CallReport) -> None:
    """Print the full report as prettified, colorized JSON."""
    console.print("\n[section]Full Report (JSON)[/]")
    console.print_json(report.model_dump_json())


def print_report(
    report: audiotrace.models.CallReport,
    playback: bool = False,
    audio_path: str | Path | None = None,
    summary: bool = False,
) -> None:
    """Render the call, then the per-section summary, then JSON (unless summary)."""
    has_conversation = bool(report.transcript.full_text or report.transcript.turns)

    if has_conversation:
        if playback:
            play_conversation(report, audio_path)
        else:
            print_transcript(report)

    print_summary(report)
    if not summary:
        print_json(report)


def run_analysis(
    file_path: str | Path,
    playback: bool = False,
    skip_pyannote: bool = False,
    summary: bool = False,
) -> None:
    path = Path(file_path)
    if not path.exists():
        console.print(f"[error]Error: File not found: {path}[/]")
        return

    with console.status(f"[info]Analyzing {path.name}...[/]", spinner="dots"):
        try:
            report = audiotrace.analyze(path, num_speakers=2, diarize=not skip_pyannote)
            console.print(f"\n[success]✓ Analysis Complete:[/] [white]{path}[/]")
        except Exception as e:
            console.print(f"[error]Error during analysis: {e}[/]")
            return

    print_report(report, playback=playback, audio_path=path, summary=summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="AudioTrace CLI - Analyze audio files.")
    parser.add_argument(
        "file_path",
        type=str,
        nargs="?",
        default=str(DEFAULT_FIXTURE),
        help=f"Path to the audio file (default: {DEFAULT_FIXTURE})",
    )
    parser.add_argument(
        "-p",
        "--playback",
        action="store_true",
        help="Play the audio back while revealing the transcript word by word.",
    )
    parser.add_argument(
        "--skip-pyannote",
        action="store_true",
        help="Skip loading the pyannote diarization model; infer speakers by pitch.",
    )
    parser.add_argument(
        "-s",
        "--summary",
        action="store_true",
        help="Show per-section summary tables only; omit the raw JSON.",
    )

    args = parser.parse_args()

    # First analysis from CLI arg
    run_analysis(
        args.file_path,
        playback=args.playback,
        skip_pyannote=args.skip_pyannote,
        summary=args.summary,
    )

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
            run_analysis(
                user_input,
                playback=args.playback,
                skip_pyannote=args.skip_pyannote,
                summary=args.summary,
            )
        except (KeyboardInterrupt, EOFError):
            console.print("\n[info]Exiting.[/]")
            break


if __name__ == "__main__":
    main()
