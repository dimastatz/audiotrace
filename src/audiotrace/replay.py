"""Production replay: turn failing production calls into regression tests (PRD 0011).

    ingest → analyze() → match rules → dedupe → redact → pending → review → suite

* **Sources** list recordings not seen before: a local directory, S3, GCS, or
  a provider adapter (Vapi, Retell, Twilio). Seen ids are kept in the store's
  ``state.json``, so re-running ingestion skips them.
* **Rules** (YAML) name a failure and a ``when`` expression over
  ``CallReport`` fields, e.g. ``quality.overall_score < 0.6``.
* **Dedupe**: calls with the same signature (rule + failure type + intent)
  become one case with an occurrence count.
* **Redaction** happens before anything is written: every turn with detected
  PII (or a self-introduced name) has its text replaced and its audio
  silenced, then the redacted transcript is scanned again — a case that still
  shows PII is not stored. Unredacted audio never lands in the store.
* **Review**: cases wait in ``pending/``; ``approve`` copies the redacted
  recording into ``suite/`` (a calls directory the regression gate and the
  GitHub Action can use) and adds its report to ``suite/baseline.json``;
  ``discard`` deletes the case.

Store layout::

    <store>/state.json                  seen source ids
    <store>/pending/<case>/case.yaml    rule, signature, count, call ids, status
    <store>/pending/<case>/audio.wav    redacted recording (first occurrence)
    <store>/pending/<case>/report.json  redacted CallReport
    <store>/suite/<case>.wav            approved cases
    <store>/suite/baseline.json
"""

from __future__ import annotations

import hashlib
import importlib
import json
import operator
import re
import shutil
import tempfile
import typing
import wave
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np
from pydantic import BaseModel

from audiotrace.compliance import CompliancePolicy, find_compliance_issues
from audiotrace.models import CallReport, Transcript, Turn

# --- Rules -------------------------------------------------------------------------


class ReplayError(Exception):
    """A bad rule, source, store, or a case that could not be safely stored."""


_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
}
_EXPR = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(?:(<=|>=|==|!=|<|>)\s*(.+?))?\s*$")


def _literal(text: str) -> Any:
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    try:
        return float(text)
    except ValueError:
        raise ReplayError(f"Not a number, boolean, null, or quoted string: {text!r}") from None


@dataclass(frozen=True)
class Rule:
    """``when`` is ``<field.path>`` (truthy) or ``<field.path> <op> <literal>``."""

    name: str
    when: str
    path: tuple[str, ...] = field(init=False)
    op: str | None = field(init=False)
    value: Any = field(init=False)

    def __post_init__(self) -> None:
        match = _EXPR.match(self.when)
        if not match:
            raise ReplayError(f"Rule {self.name!r}: can't parse {self.when!r}")
        path, op, raw = match.groups()
        parts = tuple(path.split("."))
        _validate_path(parts, self.name)  # fail early on unknown fields
        object.__setattr__(self, "path", parts)
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "value", _literal(raw) if op else None)

    def matches(self, report: CallReport) -> bool:
        actual = _resolve(report, self.path, self.name)
        if self.op is None:
            return bool(actual)
        if actual is None or self.value is None:
            return _OPS[self.op](actual, self.value) if self.op in ("==", "!=") else False
        try:
            return _OPS[self.op](actual, self.value)
        except TypeError as exc:
            raise ReplayError(f"Rule {self.name!r}: can't compare {actual!r} {self.op}") from exc


def _validate_path(path: tuple[str, ...], rule: str) -> None:
    """Check ``path`` against the CallReport schema (through Optional sections)."""
    model: Any = CallReport
    for i, part in enumerate(path):
        info = model.model_fields.get(part) if model is not None else None
        if info is None:
            raise ReplayError(f"Rule {rule!r}: unknown field {'.'.join(path[: i + 1])!r}")
        candidates = [info.annotation, *typing.get_args(info.annotation)]
        model = next(
            (c for c in candidates if isinstance(c, type) and issubclass(c, BaseModel)), None
        )


def _resolve(report: CallReport, path: tuple[str, ...], rule: str) -> Any:
    node: Any = report
    for part in path:
        if node is None:
            return None  # an optional section (e.g. media) is missing
        node = getattr(node, part)
    return node


def load_rules(path: str | Path) -> list[Rule]:
    """Load ``rules: [{name, when}, ...]`` from YAML."""
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    items = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ReplayError(f"{path}: expected a non-empty 'rules' list")
    rules = []
    for item in items:
        if not isinstance(item, dict) or "name" not in item or "when" not in item:
            raise ReplayError(f"{path}: each rule needs 'name' and 'when': {item!r}")
        rules.append(Rule(str(item["name"]), str(item["when"])))
    return rules


def signature(rule: Rule, report: CallReport) -> str:
    """Calls that fail the same way share a signature (and so a case)."""
    return "|".join(
        [rule.name, report.events.failure_type or "-", report.events.intent_detected or "-"]
    )


def case_id(sig: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", sig.lower()).strip("-")[:48]
    return f"{slug}-{hashlib.sha1(sig.encode()).hexdigest()[:8]}"


# --- Sources -------------------------------------------------------------------------


class Source(Protocol):
    name: str

    def ids(self) -> Iterator[str]: ...

    def fetch(self, source_id: str) -> Path: ...


AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".webm")


class LocalSource:
    """Recordings in a directory (ids are file names)."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.name = f"dir:{self.directory}"
        if not self.directory.is_dir():
            raise ReplayError(f"Not a directory: {self.directory}")

    def ids(self) -> Iterator[str]:
        for path in sorted(self.directory.iterdir()):
            if path.suffix.lower() in AUDIO_EXTS:
                yield path.name

    def fetch(self, source_id: str) -> Path:
        return self.directory / source_id


class _BucketSource:
    """Shared download logic for object stores (ids are object keys)."""

    scheme = ""

    def __init__(self, bucket: str, prefix: str, download_dir: Path | None) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self.name = f"{self.scheme}://{bucket}/{prefix}"
        self.download_dir = download_dir or Path(tempfile.mkdtemp(prefix="audiotrace-replay-"))

    def _local(self, key: str) -> Path:
        path = self.download_dir / re.sub(r"[^\w.-]+", "_", key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class S3Source(_BucketSource):
    """Objects under ``s3://bucket/prefix`` (needs boto3; credentials from the usual
    AWS chain)."""

    scheme = "s3"

    def __init__(
        self, bucket: str, prefix: str = "", client: Any = None, download_dir: Path | None = None
    ) -> None:
        super().__init__(bucket, prefix, download_dir)
        self._client = client or importlib.import_module("boto3").client("s3")

    def ids(self) -> Iterator[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                if str(obj["Key"]).lower().endswith(AUDIO_EXTS):
                    yield str(obj["Key"])

    def fetch(self, source_id: str) -> Path:
        path = self._local(source_id)
        self._client.download_file(self.bucket, source_id, str(path))
        return path


class GCSSource(_BucketSource):
    """Objects under ``gs://bucket/prefix`` (needs google-cloud-storage)."""

    scheme = "gs"

    def __init__(
        self, bucket: str, prefix: str = "", client: Any = None, download_dir: Path | None = None
    ) -> None:
        super().__init__(bucket, prefix, download_dir)
        if client is None:
            storage = importlib.import_module("google.cloud.storage")
            client = storage.Client()
        self._client = client

    def ids(self) -> Iterator[str]:
        for blob in self._client.list_blobs(self.bucket, prefix=self.prefix):
            if str(blob.name).lower().endswith(AUDIO_EXTS):
                yield str(blob.name)

    def fetch(self, source_id: str) -> Path:
        path = self._local(source_id)
        self._client.bucket(self.bucket).blob(source_id).download_to_filename(str(path))
        return path


class ProviderSource:
    """Recent calls from a provider adapter (ids are provider call ids)."""

    def __init__(self, adapter: Any, since: datetime | None = None, limit: int = 100) -> None:
        self.adapter = adapter
        self.since = since
        self.limit = limit
        self.name = f"provider:{adapter.provider}"

    def ids(self) -> Iterator[str]:
        yield from self.adapter.list_calls(since=self.since, limit=self.limit)

    def fetch(self, source_id: str) -> Path:
        return Path(self.adapter.fetch_call(source_id).audio)


def open_source(spec: str, since: datetime | None = None, limit: int = 100) -> Source:
    """``dir:PATH`` (or a bare path), ``s3://bucket/prefix``, ``gs://bucket/prefix``,
    or a provider name (``vapi``, ``retell``, ``twilio``)."""
    if spec.startswith(("s3://", "gs://")):
        bucket, _, prefix = spec[5:].partition("/")
        return S3Source(bucket, prefix) if spec.startswith("s3://") else GCSSource(bucket, prefix)
    if spec in ("vapi", "retell", "twilio"):
        from audiotrace.adapters import get_adapter

        return ProviderSource(get_adapter(spec), since=since, limit=limit)
    return LocalSource(spec[4:] if spec.startswith("dir:") else spec)


# --- Redaction -------------------------------------------------------------------------

# People introducing themselves; names aren't otherwise detectable without NER.
_NAME = re.compile(
    r"\b(?:my name is|my name's|this is|i am|i'm|it's|it is|speaking with)\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
)
_NAME_STOPWORDS = {"Okay", "Sure", "Yes", "No", "Hi", "Hello", "Thanks", "Great", "Fine", "Just"}


# A short number given right after someone asks for a secret (card security
# code, PIN, one-time code): the digits alone don't look like PII.
_SECRET_REQUEST = re.compile(
    r"security code|\bcvv\b|\bcvc\b|\bpin\b|passcode|verification code|one[- ]time code",
    re.I,
)
_SHORT_NUMBER = re.compile(r"(?<![\d.,])\$?\d(?:[ -]?\d){2,5}(?![\d.,]\d)")


def _answers_secret(previous: str, text: str) -> bool:
    from audiotrace.compliance import normalize

    return bool(_SECRET_REQUEST.search(previous) and _SHORT_NUMBER.search(normalize(text)))


def _has_name(text: str) -> bool:
    return any(m.group(1).split()[0] not in _NAME_STOPWORDS for m in _NAME.finditer(text))


def redact_transcript(
    transcript: Transcript, policy: CompliancePolicy | None = None
) -> tuple[Transcript, list[tuple[int, int]]]:
    """Replace every turn holding PII (or a self-introduced name) with a marker.

    Returns the redacted transcript and the (start_ms, end_ms) spans to silence
    in the audio. Raises :class:`ReplayError` if PII is still detectable after.
    """
    policy = (policy or CompliancePolicy()).model_copy(update={"flag_caller_pii": True})
    findings = [f for f in find_compliance_issues(transcript, policy) if f.type == "pii"]
    flagged: dict[int, set[str]] = {}
    for finding in findings:
        if finding.turn_index is not None:
            flagged.setdefault(finding.turn_index, set()).add(finding.pii_type or "pii")
    for i, turn in enumerate(transcript.turns):
        if _has_name(turn.text):
            flagged.setdefault(i, set()).add("name")
        if i and _answers_secret(transcript.turns[i - 1].text, turn.text):
            flagged.setdefault(i, set()).add("secret")

    turns: list[Turn] = []
    spans: list[tuple[int, int]] = []
    for i, turn in enumerate(transcript.turns):
        if i in flagged:
            kinds = ", ".join(sorted(flagged[i]))
            turns.append(turn.model_copy(update={"text": f"[redacted: {kinds}]", "words": []}))
            spans.append((turn.start_ms, turn.end_ms))
        else:
            turns.append(turn)
    if transcript.turns:
        full_text = " ".join(t.text for t in turns)
    elif findings or _has_name(transcript.full_text):
        full_text = "[redacted]"
    else:
        full_text = transcript.full_text
    redacted = transcript.model_copy(update={"turns": turns, "full_text": full_text})

    leftover = [f for f in find_compliance_issues(redacted, policy) if f.type == "pii"]
    if leftover:
        raise ReplayError("PII still detectable after redaction; case not stored")
    return redacted, spans


def redact_audio(
    src: Path, dst: Path, spans: list[tuple[int, int]], sample_rate: int = 16_000
) -> None:
    """Decode ``src`` (any FFmpeg format), silence ``spans``, write mono WAV ``dst``."""
    import librosa

    audio, _ = librosa.load(str(src), sr=sample_rate, mono=True)
    for start_ms, end_ms in spans:
        audio[int(start_ms * sample_rate / 1000) : int(end_ms * sample_rate / 1000) + 1] = 0.0
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())


def redact_report(report: CallReport, transcript: Transcript) -> CallReport:
    """The report with the redacted transcript and no turn-level detail that could
    leak redacted words (compliance finding details are already masked)."""
    return report.model_copy(update={"transcript": transcript})


# --- The store ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    seen: int = 0
    captured: int = 0
    new_cases: list[str] = field(default_factory=list)
    updated_cases: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)


Analyzer = Callable[[Path], CallReport]


def default_analyzer(path: Path) -> CallReport:
    from audiotrace.core import analyze

    return analyze(path, num_speakers=2)


class Store:
    """A replay store directory (see the module docstring for the layout)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # --- state ---

    @property
    def _state_path(self) -> Path:
        return self.root / "state.json"

    def _load_state(self) -> dict[str, list[str]]:
        if not self._state_path.exists():
            return {}
        data: dict[str, list[str]] = json.loads(self._state_path.read_text(encoding="utf-8"))
        return data

    def _save_state(self, state: dict[str, list[str]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    # --- cases ---

    def case_dir(self, case: str, status: str = "pending") -> Path:
        return self.root / status / case

    def load_case(self, case: str) -> dict[str, Any]:
        import yaml

        path = self.case_dir(case) / "case.yaml"
        if not path.exists():
            raise ReplayError(f"No pending case {case!r}")
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data

    def _write_case(self, case: str, data: dict[str, Any]) -> None:
        import yaml

        path = self.case_dir(case) / "case.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def pending(self) -> list[dict[str, Any]]:
        root = self.root / "pending"
        if not root.is_dir():
            return []
        return [self.load_case(p.name) for p in sorted(root.iterdir()) if p.is_dir()]

    # --- pipeline ---

    def ingest(
        self,
        source: Source,
        rules: list[Rule],
        analyzer: Analyzer = default_analyzer,
        policy: CompliancePolicy | None = None,
    ) -> IngestResult:
        """Analyze new recordings from ``source`` and capture rule hits as cases."""
        state = self._load_state()
        seen = set(state.get(source.name, []))
        result = IngestResult()
        for source_id in source.ids():
            if source_id in seen:
                continue
            result.seen += 1
            audio = source.fetch(source_id)
            report = analyzer(audio)
            for rule in rules:
                if not rule.matches(report):
                    continue
                result.captured += 1
                sig = signature(rule, report)
                case = case_id(sig)
                try:
                    created = self._capture(
                        case, sig, rule, source, source_id, audio, report, policy
                    )
                except ReplayError:
                    result.refused.append(source_id)
                    continue
                (result.new_cases if created else result.updated_cases).append(case)
                break  # one case per call: the first matching rule
            seen.add(source_id)
            state[source.name] = sorted(seen)
            self._save_state(state)  # after each call, so a crash doesn't redo work
        return result

    def _capture(
        self,
        case: str,
        sig: str,
        rule: Rule,
        source: Source,
        source_id: str,
        audio: Path,
        report: CallReport,
        policy: CompliancePolicy | None,
    ) -> bool:
        ref = f"{source.name}#{source_id}"
        directory = self.case_dir(case)
        if (directory / "case.yaml").exists():
            data = self.load_case(case)
            if ref not in data["calls"]:
                data["calls"].append(ref)
                data["count"] = len(data["calls"])
                self._write_case(case, data)
            return False
        transcript, spans = redact_transcript(report.transcript, policy)
        redact_audio(audio, directory / "audio.wav", spans)
        (directory / "report.json").write_text(
            redact_report(report, transcript).model_dump_json(indent=2), encoding="utf-8"
        )
        self._write_case(
            case,
            {
                "case": case,
                "rule": rule.name,
                "when": rule.when,
                "signature": sig,
                "status": "pending",
                "count": 1,
                "calls": [ref],
                "redacted_turns": len(spans),
                "reviewer": None,
            },
        )
        return True

    def approve(self, case: str, reviewer: str) -> Path:
        """Move a case into the suite: ``suite/<case>.wav`` + a baseline entry."""
        data = self.load_case(case)
        directory = self.case_dir(case)
        suite = self.root / "suite"
        suite.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(directory / "audio.wav", suite / f"{case}.wav")
        baseline_path = suite / "baseline.json"
        baseline = (
            json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
        )
        baseline[case] = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        baseline_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        data.update(status="approved", reviewer=reviewer)
        target = self.case_dir(case, "approved")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(directory), str(target))
        self._write_case_at(target, data)
        return suite / f"{case}.wav"

    def discard(self, case: str) -> None:
        self.load_case(case)  # raises for unknown cases
        shutil.rmtree(self.case_dir(case))

    def _write_case_at(self, directory: Path, data: dict[str, Any]) -> None:
        import yaml

        (directory / "case.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
        )
