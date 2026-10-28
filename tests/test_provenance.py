from importlib import metadata
from unittest.mock import patch

import audiotrace
from audiotrace.events import INTENT_MODEL
from audiotrace.models import CallReport, Provenance
from audiotrace.provenance import (
    ProvenanceChange,
    _version,
    collect_provenance,
    provenance_changes,
)
from audiotrace.sentiment import SENTIMENT_MODEL
from audiotrace.transcripts import WHISPER_MODEL


def _stack(**overrides: str) -> Provenance:
    fields = {
        "audiotrace_version": "1.2.3",
        "whisper_model": "base",
        "diarization": "pitch",
        "sentiment_model": "sst-2",
        "intent_model": "bart",
        "python_version": "3.12.0",
        "whisper_version": "20240930",
        "pyannote_version": "3.3.2",
        "librosa_version": "0.10.2",
        "transformers_version": "4.44.0",
        "torch_version": "2.4.0",
    }
    fields.update(overrides)
    return Provenance(**fields)


# --- collect_provenance ---


def test_collect_provenance_records_models_and_diarization():
    prov = collect_provenance("pitch")
    assert prov.whisper_model == WHISPER_MODEL
    assert prov.sentiment_model == SENTIMENT_MODEL
    assert prov.intent_model == INTENT_MODEL
    assert prov.diarization == "pitch"
    assert prov.python_version


def test_collect_provenance_custom_whisper_model():
    assert collect_provenance("none", whisper_model="small").whisper_model == "small"


def test_collect_provenance_records_installed_versions():
    prov = collect_provenance("none")
    assert prov.audiotrace_version == audiotrace.__version__
    assert prov.librosa_version == metadata.version("librosa")


def test_version_missing_package_is_empty():
    assert _version("definitely-not-an-installed-package-xyz") == ""


def test_collect_provenance_tolerates_missing_packages():
    with patch("audiotrace.provenance._version", return_value=""):
        prov = collect_provenance("none")
    assert prov.torch_version == ""
    assert prov.whisper_model == WHISPER_MODEL


# --- provenance_changes ---


def test_no_changes_when_stacks_match():
    a = CallReport(provenance=_stack())
    b = CallReport(provenance=_stack())
    assert provenance_changes(a, b) == []


def test_no_changes_when_both_unrecorded():
    assert provenance_changes(CallReport(), CallReport()) == []


def test_changes_list_each_differing_field():
    base = CallReport(provenance=_stack())
    cur = CallReport(provenance=_stack(whisper_model="small", torch_version="2.5.0"))
    assert provenance_changes(base, cur) == [
        ProvenanceChange("whisper_model", "base", "small"),
        ProvenanceChange("torch_version", "2.4.0", "2.5.0"),
    ]


def test_unrecorded_baseline_is_a_change():
    changes = provenance_changes(CallReport(), CallReport(provenance=_stack()))
    assert changes == [ProvenanceChange("provenance", "unrecorded", "recorded")]


def test_unrecorded_current_is_a_change():
    changes = provenance_changes(CallReport(provenance=_stack()), CallReport())
    assert changes == [ProvenanceChange("provenance", "recorded", "unrecorded")]


# --- model contract ---


def test_callreport_provenance_defaults_to_none():
    assert CallReport().provenance is None


def test_callreport_provenance_round_trip():
    report = CallReport(provenance=_stack())
    restored = CallReport.model_validate(report.model_dump())
    assert restored.provenance == report.provenance


def test_old_report_json_without_provenance_still_loads():
    data = CallReport().model_dump()
    del data["provenance"]
    assert CallReport.model_validate(data).provenance is None
