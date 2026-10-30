"""Production replay (PRD 0011): rules, sources, dedupe, redaction, review."""

import json
import wave
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from audiotrace import replay
from audiotrace.models import CallReport, Events, MediaInfo, Quality, Sentiment, Transcript, Turn
from audiotrace.replay import (
    GCSSource,
    LocalSource,
    ProviderSource,
    ReplayError,
    Rule,
    S3Source,
    Store,
    case_id,
    load_rules,
    open_source,
    redact_audio,
    redact_transcript,
    signature,
)

yaml = pytest.importorskip("yaml")

SR = 16_000


def _wav(path: Path, seconds: float = 3.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(seconds * SR))
    pcm = (0.5 * np.sin(t * 0.05) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes(pcm.tobytes())
    return path


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path)) as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")


def _turn(speaker, text, start, end):
    return Turn(speaker=speaker, text=text, start_ms=start, end_ms=end)


PII_TRANSCRIPT = Transcript(
    full_text="...",
    turns=[
        _turn("agent", "This call is recorded. How can I help?", 0, 1000),
        _turn("caller", "Hi, my name is Dana Whitfield.", 1000, 1500),
        _turn("caller", "My card is 4111 1111 1111 1111.", 1500, 2500),
        _turn("agent", "Thanks, all done.", 2500, 3000),
    ],
)


def _report(score=0.9, frustrated=False, intent="billing", transcript=None):
    return CallReport(
        media=MediaInfo(
            duration_ms=3000,
            sample_rate_hz=SR,
            channels=1,
            codec="pcm",
            file_size_bytes=1,
            file_format="wav",
            bitrate_kbps=1,
        ),
        transcript=transcript or PII_TRANSCRIPT,
        quality=Quality(overall_score=score),
        sentiment=Sentiment(caller_frustration=frustrated),
        events=Events(intent_detected=intent),
    )


# --- rules ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "when, report, hit",
    [
        ("quality.overall_score < 0.6", _report(score=0.5), True),
        ("quality.overall_score < 0.6", _report(score=0.7), False),
        ("quality.overall_score >= 0.7", _report(score=0.7), True),
        ("sentiment.caller_frustration", _report(frustrated=True), True),
        ("sentiment.caller_frustration", _report(), False),
        ("events.compliance_flags", _report(), False),
        ("events.intent_detected == 'billing'", _report(), True),
        ('events.intent_detected != "billing"', _report(), False),
        ("sentiment.caller_frustration == true", _report(frustrated=True), True),
        ("media.duration_ms > 1000", _report(), True),
        ("media.duration_ms > 1000", CallReport(), False),
        ("events.drop_off_turn == null", _report(), True),
        ("events.drop_off_turn > 2", _report(), False),
    ],
)
def test_rule_matching(when, report, hit):
    assert Rule("r", when).matches(report) is hit


@pytest.mark.parametrize(
    "when, message",
    [
        ("quality.overal_score < 0.6", "unknown field 'quality.overal_score'"),
        ("quality.overall_score.x", "unknown field"),
        ("1bad", "can't parse"),
        ("quality.overall_score < low", "Not a number"),
    ],
)
def test_bad_rules_fail_clearly(when, message):
    with pytest.raises(ReplayError, match=message):
        Rule("r", when)


def test_rule_type_mismatch_errors():
    with pytest.raises(ReplayError, match="can't compare"):
        Rule("r", "events.intent_detected < 3").matches(_report())


def test_load_rules(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules:\n  - name: low-quality\n    when: quality.overall_score < 0.6\n", encoding="utf-8"
    )
    assert load_rules(path) == [Rule("low-quality", "quality.overall_score < 0.6")]
    path.write_text("rules: []\n", encoding="utf-8")
    with pytest.raises(ReplayError, match="non-empty 'rules'"):
        load_rules(path)
    path.write_text("rules:\n  - name: x\n", encoding="utf-8")
    with pytest.raises(ReplayError, match="needs 'name' and 'when'"):
        load_rules(path)


def test_signature_and_case_id():
    rule = Rule("low-quality", "quality.overall_score < 0.6")
    sig = signature(rule, _report())
    assert sig == "low-quality|-|billing"
    assert signature(rule, CallReport()) == "low-quality|-|-"
    assert case_id(sig).startswith("low-quality-billing-") and case_id(sig) == case_id(sig)


# --- redaction -------------------------------------------------------------------------


def test_redact_transcript_replaces_pii_and_name_turns():
    redacted, spans = redact_transcript(PII_TRANSCRIPT)
    texts = [t.text for t in redacted.turns]
    assert texts[1] == "[redacted: name]"
    assert texts[2] == "[redacted: card]"
    assert texts[0] == PII_TRANSCRIPT.turns[0].text
    assert spans == [(1000, 1500), (1500, 2500)]
    assert "4111" not in redacted.model_dump_json() and "Dana" not in redacted.model_dump_json()


def test_redaction_of_secrets_given_on_request():
    transcript = Transcript(
        turns=[
            _turn("agent", "And the three digit security code on the back?", 0, 1000),
            _turn("caller", "It's $737.", 1000, 2000),
            _turn("agent", "What's your PIN?", 2000, 3000),
            _turn("caller", "four four nine one", 3000, 4000),
            _turn("agent", "How much is it?", 4000, 5000),
            _turn("caller", "It's $737.", 5000, 6000),  # no secret was asked for
            _turn("agent", "Your security code please", 6000, 7000),
            _turn("caller", "That's $82.40", 7000, 8000),  # a price, not a code
        ]
    )
    redacted, spans = redact_transcript(transcript)
    assert [t.text for t in redacted.turns][1::2] == [
        "[redacted: secret]",
        "[redacted: secret]",
        "It's $737.",
        "That's $82.40",
    ]
    assert spans == [(1000, 2000), (3000, 4000)]


def test_redaction_ignores_flag_caller_pii_false_and_stopwords():
    from audiotrace.compliance import CompliancePolicy

    redacted, _ = redact_transcript(PII_TRANSCRIPT, CompliancePolicy(flag_caller_pii=False))
    assert redacted.turns[2].text == "[redacted: card]"
    calm = Transcript(turns=[_turn("caller", "It's Okay, thanks", 0, 10)])
    assert redact_transcript(calm)[1] == []


def test_redaction_of_full_text_only_transcripts():
    leaked = Transcript(full_text="my ssn is 123-45-6789")
    assert redact_transcript(leaked)[0].full_text == "[redacted]"
    clean = Transcript(full_text="hello")
    assert redact_transcript(clean)[0].full_text == "hello"


def test_redaction_refuses_when_pii_survives(monkeypatch):
    real = replay.find_compliance_issues
    calls = []

    def leaky(transcript, policy):
        calls.append(1)
        findings = real(transcript, policy)
        if len(calls) > 1:  # the post-redaction scan "still" finds PII
            return real(PII_TRANSCRIPT, policy)
        return findings

    monkeypatch.setattr(replay, "find_compliance_issues", leaky)
    with pytest.raises(ReplayError, match="still detectable"):
        redact_transcript(PII_TRANSCRIPT)


def test_redact_audio_silences_spans(tmp_path):
    src = _wav(tmp_path / "in.wav")
    dst = tmp_path / "out" / "red.wav"
    redact_audio(src, dst, [(1000, 2000)])
    pcm = _read(dst)
    assert pcm.size == 3 * SR
    assert not pcm[SR : 2 * SR].any()
    assert np.abs(pcm[: SR - 10]).max() > 1000


# --- sources ------------------------------------------------------------------------------


def test_local_source(tmp_path):
    _wav(tmp_path / "b.wav")
    _wav(tmp_path / "a.wav")
    (tmp_path / "notes.txt").write_text("x")
    source = LocalSource(tmp_path)
    assert list(source.ids()) == ["a.wav", "b.wav"]
    assert source.fetch("a.wav") == tmp_path / "a.wav"
    with pytest.raises(ReplayError, match="Not a directory"):
        LocalSource(tmp_path / "nope")


class FakeS3:
    def __init__(self, keys):
        self.keys = keys
        self.downloads = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        keys = self.keys

        class Paginator:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in keys[:1]]}
                yield {"Contents": [{"Key": k} for k in keys[1:]]}
                yield {}

        return Paginator()

    def download_file(self, bucket, key, path):
        self.downloads.append((bucket, key))
        Path(path).write_bytes(b"audio")


def test_s3_source(tmp_path):
    client = FakeS3(["calls/a.wav", "calls/readme.md", "calls/b.MP3"])
    source = S3Source("bkt", "calls/", client=client, download_dir=tmp_path)
    assert source.name == "s3://bkt/calls/"
    assert list(source.ids()) == ["calls/a.wav", "calls/b.MP3"]
    path = source.fetch("calls/a.wav")
    assert path == tmp_path / "calls_a.wav" and path.read_bytes() == b"audio"


def test_gcs_source(tmp_path):
    downloaded = []

    class Blob:
        def __init__(self, name):
            self.name = name

        def download_to_filename(self, path):
            downloaded.append(self.name)
            Path(path).write_bytes(b"audio")

    client = SimpleNamespace(
        list_blobs=lambda bucket, prefix: [Blob("p/a.ogg"), Blob("p/x.json")],
        bucket=lambda name: SimpleNamespace(blob=Blob),
    )
    source = GCSSource("bkt", "p/", client=client, download_dir=tmp_path)
    assert list(source.ids()) == ["p/a.ogg"]
    assert source.fetch("p/a.ogg").read_bytes() == b"audio" and downloaded == ["p/a.ogg"]


def test_cloud_sources_load_their_sdks(monkeypatch, tmp_path):
    made = {}
    boto3 = SimpleNamespace(client=lambda name: made.setdefault("s3", name))
    storage = SimpleNamespace(Client=lambda: made.setdefault("gcs", "client"))
    modules = {"boto3": boto3, "google.cloud.storage": storage}
    monkeypatch.setattr(replay.importlib, "import_module", modules.__getitem__)
    S3Source("b", download_dir=tmp_path)
    GCSSource("b")
    assert made == {"s3": "s3", "gcs": "client"}


def test_provider_source(tmp_path):
    adapter = SimpleNamespace(
        provider="vapi",
        list_calls=lambda since, limit: iter(["c1", "c2"][:limit]),
        fetch_call=lambda call_id: SimpleNamespace(audio=tmp_path / f"{call_id}.wav"),
    )
    source = ProviderSource(adapter, since=datetime(2026, 1, 1, tzinfo=timezone.utc), limit=1)
    assert source.name == "provider:vapi"
    assert list(source.ids()) == ["c1"]
    assert source.fetch("c1") == tmp_path / "c1.wav"


def test_open_source(monkeypatch, tmp_path):
    assert isinstance(open_source(str(tmp_path)), LocalSource)
    assert open_source(f"dir:{tmp_path}").directory == tmp_path
    monkeypatch.setattr(replay, "S3Source", lambda b, p: ("s3", b, p))
    monkeypatch.setattr(replay, "GCSSource", lambda b, p: ("gs", b, p))
    assert open_source("s3://bkt/some/prefix") == ("s3", "bkt", "some/prefix")
    assert open_source("gs://bkt") == ("gs", "bkt", "")
    monkeypatch.setenv("RETELL_API_KEY", "r")
    source = open_source("retell", limit=5)
    assert source.name == "provider:retell" and source.limit == 5


# --- store: ingest, dedupe, review ------------------------------------------------------------


LOW = Rule("low-quality", "quality.overall_score < 0.6")
FRUSTRATED = Rule("frustrated", "sentiment.caller_frustration")


def _analyzer(reports):
    def analyze(path):
        return reports[Path(path).name]

    return analyze


def test_ingest_dedupes_redacts_and_skips_seen(tmp_path):
    calls = tmp_path / "calls"
    for name in ("a.wav", "b.wav", "c.wav", "ok.wav"):
        _wav(calls / name)
    reports = {
        "a.wav": _report(score=0.4),
        "b.wav": _report(score=0.5),  # same signature as a.wav
        "c.wav": _report(score=0.9, frustrated=True, intent="sales"),
        "ok.wav": _report(score=0.95),
    }
    store = Store(tmp_path / "replay")
    source = LocalSource(calls)

    result = store.ingest(source, [LOW, FRUSTRATED], analyzer=_analyzer(reports))

    assert (result.seen, result.captured) == (4, 3)
    low_case = case_id("low-quality|-|billing")
    assert result.new_cases == [low_case, case_id("frustrated|-|sales")]
    assert result.updated_cases == [low_case]
    case = store.load_case(low_case)
    assert case["count"] == 2 and case["status"] == "pending"
    assert case["calls"] == [f"dir:{calls}#a.wav", f"dir:{calls}#b.wav"]
    assert case["redacted_turns"] == 2
    stored = (store.case_dir(low_case) / "report.json").read_text()
    assert "4111" not in stored and "Dana" not in stored
    pcm = _read(store.case_dir(low_case) / "audio.wav")
    assert not pcm[SR : int(2.5 * SR)].any()  # name + card turns silenced
    assert len(store.pending()) == 2

    # Re-running skips everything already seen; adding a duplicate call is idempotent.
    again = store.ingest(source, [LOW, FRUSTRATED], analyzer=_analyzer(reports))
    assert again.seen == 0
    store._capture(low_case, "", LOW, source, "a.wav", calls / "a.wav", reports["a.wav"], None)
    assert store.load_case(low_case)["count"] == 2


def test_ingest_refuses_cases_that_cannot_be_redacted(tmp_path, monkeypatch):
    _wav(tmp_path / "calls" / "a.wav")

    def refuse(*args, **kwargs):
        raise ReplayError("PII still detectable")

    monkeypatch.setattr(replay, "redact_transcript", refuse)
    store = Store(tmp_path / "replay")
    result = store.ingest(
        LocalSource(tmp_path / "calls"), [LOW], analyzer=_analyzer({"a.wav": _report(score=0.1)})
    )
    assert result.refused == ["a.wav"] and store.pending() == []
    assert not (tmp_path / "replay" / "pending").exists()


def test_approve_moves_case_into_the_suite(tmp_path):
    _wav(tmp_path / "calls" / "a.wav")
    store = Store(tmp_path / "replay")
    store.ingest(
        LocalSource(tmp_path / "calls"), [LOW], analyzer=_analyzer({"a.wav": _report(score=0.1)})
    )
    case = case_id("low-quality|-|billing")

    wav = store.approve(case, reviewer="dana")

    assert wav == tmp_path / "replay" / "suite" / f"{case}.wav" and wav.exists()
    baseline = json.loads((tmp_path / "replay" / "suite" / "baseline.json").read_text())
    assert list(baseline) == [case]
    approved = yaml.safe_load((store.case_dir(case, "approved") / "case.yaml").read_text())
    assert approved["status"] == "approved" and approved["reviewer"] == "dana"
    assert store.pending() == []

    from audiotrace.check import load_baseline

    assert load_baseline(tmp_path / "replay" / "suite" / "baseline.json")[case].quality


def test_second_approval_extends_the_baseline_and_discard_deletes(tmp_path):
    for name in ("a.wav", "b.wav", "c.wav"):
        _wav(tmp_path / "calls" / name)
    reports = {
        "a.wav": _report(score=0.1),
        "b.wav": _report(score=0.9, frustrated=True),
        "c.wav": _report(score=0.2, intent="sales"),
    }
    store = Store(tmp_path / "replay")
    store.ingest(LocalSource(tmp_path / "calls"), [LOW, FRUSTRATED], analyzer=_analyzer(reports))
    low, frustrated, sales = (
        case_id("low-quality|-|billing"),
        case_id("frustrated|-|billing"),
        case_id("low-quality|-|sales"),
    )
    store.approve(low, "r")
    store.approve(frustrated, "r")
    baseline = json.loads((tmp_path / "replay" / "suite" / "baseline.json").read_text())
    assert set(baseline) == {low, frustrated}
    store.discard(sales)
    assert store.pending() == []
    with pytest.raises(ReplayError, match="No pending case"):
        store.discard(sales)


def test_empty_store():
    assert Store("/nonexistent/replay-store").pending() == []


def test_default_analyzer(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(
        "audiotrace.core.analyze",
        lambda path, num_speakers: seen.update(path=path, n=num_speakers) or CallReport(),
    )
    replay.default_analyzer(tmp_path / "x.wav")
    assert seen == {"path": tmp_path / "x.wav", "n": 2}
