"""The examples stay runnable: execute each with analyze() stubbed (fast).

The real run against the bundled call, with models, is the separate CI
`examples` job (`python examples/run_all.py`).
"""

import importlib
import runpy
import sys
from pathlib import Path

import pytest

from audiotrace.models import CallReport, Cost, Quality, Transcript, Turn

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

REPORT = CallReport(
    transcript=Transcript(
        full_text="hi there",
        turns=[Turn(speaker="AI Agent", text="hi there", start_ms=0, end_ms=900)],
    ),
    quality=Quality(overall_score=0.8),
    cost=Cost(total_usd=0.01),
)


@pytest.fixture(autouse=True)
def examples_path(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    calls = []

    def fake_analyze(audio, *args, **kwargs):
        calls.append((Path(audio).name, kwargs))
        return REPORT

    monkeypatch.setattr("audiotrace.analyze", fake_analyze)
    yield calls
    for name in list(sys.modules):
        if name in {p.stem for p in EXAMPLES.glob("*.py")}:
            del sys.modules[name]


def test_every_example_is_covered():
    assert {p.stem for p in EXAMPLES.glob("*.py")} == {
        "_common",
        "analyze_one_call",
        "compare_two_calls",
        "custom_pricing",
        "gate_directory",
        "run_all",
    }


def test_sample_call_exists():
    common = importlib.import_module("_common")
    assert common.SAMPLE_CALL.exists()


def test_run_all(examples_path, capsys):
    runpy.run_path(str(EXAMPLES / "run_all.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "All examples ran." in out
    assert "quality score      0.80" in out
    assert "PASS — 1 call(s) checked" in out
    assert any("pricing" in kwargs for _, kwargs in examples_path)


def test_examples_accept_a_path(examples_path):
    importlib.import_module("analyze_one_call").main("other.wav")
    importlib.import_module("custom_pricing").main("other.wav")
    importlib.import_module("compare_two_calls").main("a.wav", "b.wav")
    assert [name for name, _ in examples_path] == ["other.wav", "other.wav", "a.wav", "b.wav"]


def test_gate_directory_on_a_given_folder(tmp_path, examples_path):
    (tmp_path / "x.mp3").write_bytes(b"")
    assert importlib.import_module("gate_directory").main(tmp_path).passed


@pytest.mark.parametrize("name", ["analyze_one_call", "custom_pricing", "gate_directory"])
def test_scripts_run_as_main(name, monkeypatch):
    monkeypatch.setattr(sys, "argv", [name])
    try:
        runpy.run_path(str(EXAMPLES / f"{name}.py"), run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 0
