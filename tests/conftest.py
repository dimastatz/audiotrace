from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def golden_call_audio() -> Path:
    """Path to the ~64s golden customer-service call recording.

    See tests/fixtures/README.md for provenance.
    """
    path = FIXTURES_DIR / "paradise_hotel_booking_60s.mp3"
    assert path.exists(), f"golden audio fixture missing: {path}"
    return path
