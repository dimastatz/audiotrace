"""Integrity checks for the golden call set (tests/fixtures/golden).

These don't run the models — they make sure the scenarios, the rendered calls,
and the committed baseline stay in step when someone edits one of them.
"""

from pathlib import Path

import pytest

from audiotrace.check import load_baseline
from audiotrace.events import CONSENT_KEYWORDS, DEFAULT_INTENT_LABELS

yaml = pytest.importorskip("yaml")

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
if not GOLDEN.is_dir():  # excluded from the sdist
    pytest.skip("golden call set not present", allow_module_level=True)

SCENARIOS = sorted((GOLDEN / "scenarios").glob("*.yaml"))
EXPECT_KEYS = {"consent", "pii", "frustration", "interruptions", "slow_agent", "drop_off"}
LINES = {"clean", "phone", "noisy"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_golden_set_has_at_least_twenty_calls():
    # PRD 0009 Part B needs ~20+ calls for a stable distributional check.
    assert len(SCENARIOS) >= 20


def test_every_scenario_has_a_call_and_vice_versa():
    calls = {p.stem for p in (GOLDEN / "calls").glob("*.opus")}
    assert calls == {p.stem for p in SCENARIOS}


def test_calls_are_small_opus_files():
    for call in (GOLDEN / "calls").glob("*.opus"):
        assert 50_000 < call.stat().st_size < 500_000, call.name


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_is_well_formed(path):
    scenario = _load(path)
    assert scenario["intent"] in DEFAULT_INTENT_LABELS
    assert scenario.get("line", "clean") in LINES
    assert set(scenario["expect"]) == EXPECT_KEYS
    for role in ("agent", "caller"):
        assert scenario[role]["voice"][:2] in {"af", "am", "bf", "bm"}
    for turn in scenario["turns"]:
        assert len(set(turn) & {"agent", "caller"}) == 1, turn


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_consent_expectation_matches_script(path):
    # Guards edits: a "no disclosure" call must not mention any consent keyword.
    scenario = _load(path)
    text = " ".join(t.get("agent") or t["caller"] for t in scenario["turns"]).lower()
    mentions = any(k in text for k in CONSENT_KEYWORDS)
    assert mentions == scenario["expect"]["consent"]


def test_baseline_covers_every_call_with_provenance():
    baseline = load_baseline(GOLDEN / "baseline.json")
    assert set(baseline) == {p.stem for p in SCENARIOS}
    for report in baseline.values():
        assert report.provenance is not None
