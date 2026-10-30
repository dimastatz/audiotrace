"""Shared bits for the examples: the bundled call recording."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# A 64-second synthetic hotel-booking call (see tests/fixtures/README.md).
SAMPLE_CALL = ROOT / "tests" / "fixtures" / "paradise_hotel_booking_60s.mp3"
