"""Extraction logic for various parts of the CallReport."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from audiotrace.models import MediaInfo


def extract_media_info(audio_path: str | Path) -> MediaInfo:
    """Extract media metadata using ffprobe.

    Args:
        audio_path: Path to the audio file.

    Returns:
        A populated :class:`~audiotrace.models.MediaInfo`.

    Raises:
        FileNotFoundError: If the audio file does not exist.
        RuntimeError: If ffprobe fails or is not installed.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr}") from e
    except FileNotFoundError as e:
        raise RuntimeError(
            "ffprobe not found. Please install FFmpeg (including ffprobe) on your system."
        ) from e

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    audio_stream: dict[str, object] = next(
        (s for s in streams if s.get("codec_type") == "audio"), {}
    )

    return MediaInfo(
        duration_ms=int(float(str(fmt.get("duration", 0))) * 1000),
        sample_rate_hz=int(str(audio_stream.get("sample_rate", 0))),
        channels=int(str(audio_stream.get("channels", 0))),
        codec=str(audio_stream.get("codec_name", "unknown")),
        file_size_bytes=int(str(fmt.get("size", 0))),
        file_format=str(fmt.get("format_name", "unknown")),
        bitrate_kbps=float(str(fmt.get("bit_rate", 0))) / 1000,
    )
