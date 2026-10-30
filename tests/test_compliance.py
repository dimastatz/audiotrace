import pytest

from audiotrace.compliance import (
    CompliancePolicy,
    compliance_flags,
    find_compliance_issues,
    load_policy,
    luhn_valid,
    mask,
    normalize,
)
from audiotrace.models import Transcript, Turn


def _t(*turns):
    """Build a transcript from (speaker, text, start_ms) tuples."""
    return Transcript(
        full_text=" ".join(t[1] for t in turns),
        turns=[
            Turn(speaker=s, text=text, start_ms=start, end_ms=start + 2000)
            for s, text, start in turns
        ],
    )


DISCLOSED = ("agent", "This call is recorded for quality.", 0)


def _pii(*turns, policy=None):
    findings = find_compliance_issues(_t(DISCLOSED, *turns), policy)
    return [(f.pii_type, f.speaker, f.turn_index) for f in findings if f.type == "pii"]


# --- normalize ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "spoken, written",
    [
        ("four one one one", "4 1 1 1"),
        ("double five", "5 5"),
        ("triple seven two", "7 7 7 2"),
        ("five oh two", "5 0 2"),
        ("oh, I see", "oh, I see"),
        ("Oh no", "Oh no"),
        ("one of them", "1 of them"),
        ("jordan dot lee at example dot com", "jordan.lee@example.com"),
        ("meet at noon", "meet at noon"),
        ("double check it", "double check it"),
    ],
)
def test_normalize(spoken, written):
    assert normalize(spoken) == written


def test_luhn_and_mask():
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")
    assert mask("4111 1111 1111 1111") == "**************11"
    assert mask("abc") == "***"


# --- consent -------------------------------------------------------------------------


def test_consent_satisfied_by_agent_in_window():
    assert find_compliance_issues(_t(DISCLOSED)) == []


def test_caller_saying_record_is_not_a_disclosure():
    findings = find_compliance_issues(
        _t(("agent", "Hello, how can I help?", 0), ("caller", "Is this recorded?", 3000))
    )
    assert [f.type for f in findings] == ["missing_consent"]
    assert findings[0].detail == "no recording disclosure by the agent in the first 30s"
    assert findings[0].end_ms == 30_000


def test_late_disclosure_fails_the_window_but_passes_without_one():
    late = _t(("agent", "Hi", 0), ("agent", "This call is recorded", 45_000))
    assert compliance_flags(find_compliance_issues(late)) == ["missing_consent"]
    anywhere = CompliancePolicy(consent_window_ms=None)
    assert find_compliance_issues(late, anywhere) == []
    missing = find_compliance_issues(_t(("agent", "Hi", 0)), anywhere)
    assert missing[0].detail == "no recording disclosure by the agent"


def test_unknown_roles_accept_any_speaker():
    transcript = _t(("SPEAKER_00", "Hi", 0), ("SPEAKER_01", "this is being recorded", 2000))
    assert find_compliance_issues(transcript) == []


def test_consent_can_be_disabled_and_keywords_changed():
    transcript = _t(("agent", "Hi", 0))
    assert find_compliance_issues(transcript, CompliancePolicy(requires_consent=False)) == []
    policy = CompliancePolicy(consent_keywords=("hi",))
    assert find_compliance_issues(transcript, policy) == []


# --- PII ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, pii_type",
    [
        ("My social is 123-45-6789", "ssn"),
        ("social security number one two three four five six seven eight nine", "ssn"),
        ("card 4111 1111 1111 1111", "card"),
        ("four one one one one one one one one one one one one one one one", "card"),
        ("email me at jordan.lee@example.com", "email"),
        ("it's jordan dot lee at example dot com", "email"),
        ("call me back at 415-555-0134", "phone"),
        ("my number is four one five five five five oh one three four", "phone"),
        ("+1 415 555 0134", "phone"),
        ("I was born on March 4th, 1990", "dob"),
        ("date of birth 04/03/1990", "dob"),
        ("I live at 42 Maple Street", "address"),
        ("my account number is 88213456", "account"),
        ("account 5551234567", "account"),
    ],
)
def test_detects_us_pii_in_digit_and_spoken_forms(text, pii_type):
    assert _pii(("caller", text, 3000)) == [(pii_type, "caller", 1)]


@pytest.mark.parametrize(
    "text",
    [
        "card 4111 1111 1111 1112",  # fails Luhn
        "your appointment is March 4th, 2026",  # a date, but not a birth date
        "that'll be 25 dollars",
        "order 123456789",  # nine digits without SSN context or format
        "press 1 for billing",
    ],
)
def test_ignores_non_pii(text):
    assert _pii(("caller", text, 3000)) == []


def test_findings_carry_location_role_and_masked_value():
    findings = find_compliance_issues(
        _t(DISCLOSED, ("AI Agent", "I have your card as 4111 1111 1111 1111", 4000))
    )
    (finding,) = findings
    assert finding.type == "pii"
    assert finding.pii_type == "card"
    assert (finding.speaker, finding.role, finding.turn_index) == ("AI Agent", "agent", 1)
    assert (finding.start_ms, finding.end_ms) == (4000, 6000)
    assert finding.detail == "**************11"
    assert "4111" not in finding.model_dump_json()


def test_caller_pii_can_be_ignored():
    policy = CompliancePolicy(flag_caller_pii=False)
    turns = [("caller", "123-45-6789", 3000), ("agent", "Your SSN is 123-45-6789", 5000)]
    assert _pii(*turns, policy=policy) == [("ssn", "agent", 2)]


def test_regions_and_disabled_types():
    uk = CompliancePolicy(regions=("uk",))
    assert _pii(("caller", "my NI number is AB 12 34 56 C", 0), policy=uk) == [
        ("ni_number", "caller", 1)
    ]
    assert _pii(("caller", "postcode SW1A 1AA", 0), policy=uk) == [("postcode", "caller", 1)]
    assert _pii(("caller", "my mobile is 07700 900123", 0), policy=uk) == [("phone", "caller", 1)]
    assert _pii(("caller", "my social is 123-45-6789", 0), policy=uk) == []
    eu = CompliancePolicy(regions=("eu",))
    assert _pii(("caller", "IBAN DE89 3704 0044 0532 0130 00", 0), policy=eu) == [
        ("iban", "caller", 1)
    ]
    no_address = CompliancePolicy(disabled_pii=("address",))
    assert _pii(("caller", "42 Maple Street", 0), policy=no_address) == []
    with pytest.raises(ValueError, match="Unknown region"):
        CompliancePolicy(regions=("mars",)).pii_types()


def test_one_value_is_reported_once():
    # A card number is also a long digit run; it must not double as an account.
    assert _pii(("caller", "account card 4111 1111 1111 1111", 0)) == [("card", "caller", 1)]


def test_flags_summarize_findings():
    transcript = _t(("agent", "Hi", 0), ("caller", "123-45-6789", 2000))
    assert compliance_flags(find_compliance_issues(transcript)) == [
        "missing_consent",
        "pii_exposed",
    ]
    assert compliance_flags([]) == []


def test_load_policy(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "policy.yaml"
    path.write_text("regions: [us, uk]\nconsent_window_ms: 10000\n", encoding="utf-8")
    policy = load_policy(path)
    assert policy.regions == ("us", "uk") and policy.consent_window_ms == 10_000
    (tmp_path / "empty.yaml").write_text("", encoding="utf-8")
    assert load_policy(tmp_path / "empty.yaml") == CompliancePolicy()


def test_report_lists_findings_linked_to_turns():
    from audiotrace.models import CallReport, Events
    from audiotrace.report import render_html

    transcript = _t(("agent", "Hi", 0), ("Customer", "my social is 123-45-6789", 61_000))
    findings = find_compliance_issues(transcript)
    report = CallReport(
        transcript=transcript,
        events=Events(compliance_flags=compliance_flags(findings), compliance_findings=findings),
    )
    page = render_html(report)
    assert "<li>⚠ Missing consent at 0:00 — no recording disclosure" in page
    assert '<li>⚠ PII (ssn) said by Customer at <a href="#turn-1">1:01</a> — *******89</li>' in page
    assert 'id="turn-1"' in page
    assert "123-45" not in page.split('<ul class="flags">')[1].split("</ul>")[0]
