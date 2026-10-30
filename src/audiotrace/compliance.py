"""Compliance detection: recording disclosure and exposed PII (PRD 0013).

Rule-based and local. Every finding records where it happened (turn, time
range, speaker, and the speaker's role) so a report can point at it and
production replay can redact it. Matched values are masked before they're
stored: a report never repeats the PII it found.

Numbers in transcripts are often spoken ("four one one one ..."), so each turn
is normalized first: number words become digits, "dot"/"at" in spoken emails
become punctuation. Detection runs on the normalized text.

Policies are plain data (:class:`CompliancePolicy`), from code or YAML.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from audiotrace.models import ComplianceFinding, Transcript, Turn
from audiotrace.transcripts import speaker_role

# Substrings that satisfy a recording/consent disclosure.
CONSENT_KEYWORDS = ("record", "recorded", "recording", "consent", "monitored")

PII_TYPES = (
    "ssn",
    "card",
    "email",
    "phone",
    "dob",
    "address",
    "account",
    "ni_number",
    "postcode",
    "iban",
)
# Which PII types each region preset enables, on top of the universal ones.
_UNIVERSAL = ("card", "email", "dob", "address", "account")
REGION_PII: dict[str, tuple[str, ...]] = {
    "us": ("ssn", "phone"),
    "uk": ("ni_number", "postcode", "phone"),
    "eu": ("iban", "phone"),
}


class CompliancePolicy(BaseModel):
    """Which compliance rules run, and how strictly."""

    model_config = ConfigDict(extra="forbid")

    requires_consent: bool = True
    consent_keywords: tuple[str, ...] = CONSENT_KEYWORDS
    # The disclosure must *start* within this many ms of the call start, in an
    # agent turn. ``None`` accepts it anywhere in the call.
    consent_window_ms: int | None = Field(default=30_000, ge=0)
    regions: tuple[str, ...] = ("us",)
    # PII types to skip, e.g. ("address",) for a delivery line.
    disabled_pii: tuple[str, ...] = ()
    # When False, PII spoken by the caller is ignored and only the agent saying
    # it (reading it back, or asking for it aloud) counts.
    flag_caller_pii: bool = True

    def pii_types(self) -> set[str]:
        unknown = set(self.regions) - set(REGION_PII)
        if unknown:
            raise ValueError(
                f"Unknown region(s): {', '.join(sorted(unknown))} "
                f"(available: {', '.join(sorted(REGION_PII))})"
            )
        enabled = set(_UNIVERSAL)
        for region in self.regions:
            enabled.update(REGION_PII[region])
        return enabled - set(self.disabled_pii)


def load_policy(path: str | Path) -> CompliancePolicy:
    """Load a :class:`CompliancePolicy` from a YAML file (needs PyYAML)."""
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return CompliancePolicy.model_validate(data)


# --- Normalization -------------------------------------------------------------

_NUMBER_WORDS = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
_REPEAT = {"double": 2, "triple": 3}
_TOKEN = re.compile(r"[A-Za-z]+|\d+|[^\sA-Za-z\d]+|\s+")


def normalize(text: str) -> str:
    """Spoken digits to digits ("four one one" -> "4 1 1", "double five" -> "5 5"),
    and spoken email punctuation ("jo at example dot com" -> "jo@example.com").

    "oh"/"o" only count as zero next to other digits, so ordinary speech is
    left alone.
    """
    tokens = _TOKEN.findall(text)
    words = [t.lower() for t in tokens]

    def is_digit_word(i: int) -> bool:
        return 0 <= i < len(words) and (words[i] in _NUMBER_WORDS or words[i].isdigit())

    def near_digit(i: int) -> bool:
        # Skip whitespace/punctuation tokens to find the neighbouring words.
        for step in (-1, 1):
            j = i + step
            while 0 <= j < len(words) and not words[j].strip().isalnum():
                j += step
            if is_digit_word(j) and words[j] not in ("oh", "o"):
                return True
        return False

    out: list[str] = []
    repeat = 1
    for i, (tok, low) in enumerate(zip(tokens, words)):
        if low in _REPEAT and near_digit(i):
            repeat = _REPEAT[low]
            continue
        if low in _NUMBER_WORDS and (low not in ("oh", "o") or near_digit(i)):
            out.append(" ".join([_NUMBER_WORDS[low]] * repeat))
            repeat = 1
            continue
        if not tok.strip() and repeat != 1:
            continue  # keep "double" attached to its digit
        out.append(tok)
    joined = "".join(out)
    joined = re.sub(r"\s+dot\s+(?=[A-Za-z0-9])", ".", joined, flags=re.I)
    joined = re.sub(r"(?<=[A-Za-z0-9])\s+at\s+(?=[A-Za-z0-9-]+\.[A-Za-z])", "@", joined, flags=re.I)
    return joined


# --- PII detectors ---------------------------------------------------------------

# A run of digits with the separators people say or Whisper writes between them.
_DIGIT_RUN = re.compile(r"(?<![\w])\+?\d(?:[\s().-]*\d)*(?![\w])")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
_ADDRESS = re.compile(
    r"\b\d{1,5}(?:\s+[A-Z][a-z]+){1,3}\s+"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way|place|pl)\b",
    re.I,
)
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
_DATE = re.compile(
    rf"\b(?:(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+(?:of\s+)?\d{{4}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTHS}),?\s+\d{{4}}"
    r"|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b",
    re.I,
)
_NI_NUMBER = re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.I)
_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b")

_SSN_CONTEXT = re.compile(r"social security|\bssn\b|\bsocial\b", re.I)
_DOB_CONTEXT = re.compile(r"\bborn\b|birth|\bdob\b|birthday", re.I)
_ACCOUNT_CONTEXT = re.compile(
    r"\baccount\b|\bmember(?:ship)?\b|\bpolicy\b|\bcustomer (?:id|number)\b|\breference\b", re.I
)
_PHONE_CONTEXT = re.compile(r"\bphone\b|\bcall (?:me|back)\b|\bnumber\b|\bcell\b|\bmobile\b", re.I)


def luhn_valid(digits: str) -> bool:
    """True when ``digits`` passes the Luhn checksum used by payment cards."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _classify_digits(digits: str, raw: str, text: str, enabled: set[str]) -> str | None:
    """Name the PII type of one digit run, given the turn's text for context."""
    n = len(digits)
    if 13 <= n <= 19 and "card" in enabled and luhn_valid(digits):
        return "card"
    if (
        "ssn" in enabled
        and n == 9
        and (re.fullmatch(r"\d{3}-\d{2}-\d{4}", raw.strip()) or _SSN_CONTEXT.search(text))
    ):
        return "ssn"
    if "phone" in enabled and (
        (n == 10 and not digits.startswith(("0", "1")))
        or (n == 11 and digits.startswith(("1", "0", "44")))
        or (n in (11, 12) and raw.lstrip().startswith("+"))
    ):
        if n == 10 and _ACCOUNT_CONTEXT.search(text) and not _PHONE_CONTEXT.search(text):
            return "account" if "account" in enabled else None
        return "phone"
    if "account" in enabled and 6 <= n <= 16 and _ACCOUNT_CONTEXT.search(text):
        return "account"
    return None


@dataclass(frozen=True)
class _Match:
    pii_type: str
    value: str


def _find_pii(text: str, enabled: set[str]) -> Iterator[_Match]:
    taken: list[tuple[int, int]] = []

    def free(span: tuple[int, int]) -> bool:
        return all(span[1] <= a or span[0] >= b for a, b in taken)

    def scan(
        pattern: re.Pattern[str], pii_type: str, guard: Callable[[str], bool] | None = None
    ) -> Iterator[_Match]:
        if pii_type not in enabled:
            return
        for m in pattern.finditer(text):
            if free(m.span()) and (guard is None or guard(m.group())):
                taken.append(m.span())
                yield _Match(pii_type, m.group())

    yield from scan(_EMAIL, "email")
    yield from scan(_IBAN, "iban")
    yield from scan(_NI_NUMBER, "ni_number")
    yield from scan(_POSTCODE, "postcode")
    yield from scan(_ADDRESS, "address")
    yield from scan(_DATE, "dob", lambda _: bool(_DOB_CONTEXT.search(text)))
    for m in _DIGIT_RUN.finditer(text):
        if not free(m.span()):
            continue
        digits = re.sub(r"\D", "", m.group())
        pii_type = _classify_digits(digits, m.group(), text, enabled)
        if pii_type:
            taken.append(m.span())
            yield _Match(pii_type, m.group())


def mask(value: str) -> str:
    """Hide a matched value, keeping its last two alphanumerics for reference."""
    chars = [c for c in value if c.isalnum()]
    keep = "".join(chars[-2:]) if len(chars) > 4 else ""
    return "*" * max(len(chars) - len(keep), 1) + keep


# --- Entry point -------------------------------------------------------------------


def find_compliance_issues(
    transcript: Transcript, policy: CompliancePolicy | None = None
) -> list[ComplianceFinding]:
    """All compliance findings for a transcript, in call order."""
    policy = policy or CompliancePolicy()
    findings: list[ComplianceFinding] = []
    if policy.requires_consent and not _has_disclosure(_turns(transcript), policy):
        window = policy.consent_window_ms
        findings.append(
            ComplianceFinding(
                type="missing_consent",
                detail=(
                    f"no recording disclosure by the agent in the first {window / 1000:g}s"
                    if window is not None
                    else "no recording disclosure by the agent"
                ),
                start_ms=0,
                end_ms=window or 0,
            )
        )
    enabled = policy.pii_types()
    for index, turn in enumerate(_turns(transcript)):
        role = speaker_role(turn.speaker)
        if role == "caller" and not policy.flag_caller_pii:
            continue
        for match in _find_pii(normalize(turn.text), enabled):
            findings.append(
                ComplianceFinding(
                    type="pii",
                    pii_type=match.pii_type,
                    detail=mask(match.value),
                    speaker=turn.speaker,
                    role=role or "",
                    turn_index=index,
                    start_ms=turn.start_ms,
                    end_ms=turn.end_ms,
                )
            )
    return findings


def _turns(transcript: Transcript) -> list[Turn]:
    """The transcript's turns, or its full text as one unlabelled turn."""
    if transcript.turns or not transcript.full_text:
        return transcript.turns
    return [Turn(speaker="", text=transcript.full_text, start_ms=0, end_ms=0)]


def _has_disclosure(turns: list[Turn], policy: CompliancePolicy) -> bool:
    """A disclosure keyword in an agent turn that starts inside the window. When no
    turn has a recognizable agent label, any speaker counts (roles unknown)."""
    roles_known = any(speaker_role(t.speaker) == "agent" for t in turns)
    for turn in turns:
        if roles_known and speaker_role(turn.speaker) != "agent":
            continue
        if policy.consent_window_ms is not None and turn.start_ms > policy.consent_window_ms:
            continue
        if any(k in turn.text.lower() for k in policy.consent_keywords):
            return True
    return False


def compliance_flags(findings: list[ComplianceFinding]) -> list[str]:
    """The summary flags kept on ``Events.compliance_flags`` for compatibility."""
    flags: list[str] = []
    if any(f.type == "missing_consent" for f in findings):
        flags.append("missing_consent")
    if any(f.type == "pii" for f in findings):
        flags.append("pii_exposed")
    return flags
