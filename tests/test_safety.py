import pytest

from app.summary.safety import (
    cited_sources,
    faithfulness_problems,
    forbidden_words,
    missing_sources,
    sentence_count,
)
from tests.test_rules import packet_for

PA002 = packet_for("PA-002")
PA006 = packet_for("PA-006")


@pytest.mark.parametrize(
    "text",
    [
        "I recommend approval.",
        "The request should go ahead.",
        "The member is eligible for therapy.",
        "This should be DENIED.",
        "Approved on review.",
        "The member does not qualify.",
    ],
)
def test_forbidden_wording_is_caught(text):
    assert forbidden_words(text)


def test_descriptive_wording_passes():
    text = "C2 is missing; an HbA1c result dated on or after 2026-07-03 is outstanding."
    assert forbidden_words(text) == []


def test_faithful_summary_has_no_problems():
    text = "C1, C3, C4 and C5 are met. C2 is missing an HbA1c dated on or after 2026-07-03."
    assert faithfulness_problems(text, PA002) == []


def test_invented_number_is_caught():
    text = "C2 is missing. HbA1c was 8.1 on 2026-07-03."
    assert "number not in packet: 8.1" in faithfulness_problems(text, PA002)


def test_invented_date_is_caught():
    text = "C2 is missing; a result from 2026-01-15 is outstanding."
    assert "date not in packet: 2026-01-15" in faithfulness_problems(text, PA002)


def test_invented_criterion_is_caught():
    assert "criterion not in packet: C9" in faithfulness_problems("C2 and C9 are open.", PA002)


def test_non_met_criterion_must_be_named():
    problems = faithfulness_problems("All five criteria look fine.", PA002)
    assert "C2 is missing but not mentioned" in problems


def test_both_sides_of_a_conflict_are_citable():
    text = "C2 conflicts: the form says 7.8 and the record says 6.4 on 2026-09-12."
    assert faithfulness_problems(text, PA006) == []


def test_cited_sources_cover_criteria_conflicts_and_documents():
    refs = cited_sources(PA006)
    assert {r.resource_type for r in refs} >= {"Observation", "DocumentReference"}


def test_missing_sources_lists_refs_the_server_cannot_find():
    gone = sorted(cited_sources(PA006), key=str)[0]
    assert missing_sources(PA006, lambda r: r != gone) == [gone]
    assert missing_sources(PA006, lambda r: True) == []


@pytest.mark.parametrize(
    "text",
    [
        "C1, C3, C4 and C5 are met, while C2 is missing.",
        "The evidence meets criteria C1 and C3, but C2 is missing.",
        "C2 is missing; criteria C1 and C3 are met and C4 is met.",
    ],
)
def test_correct_status_claims_pass(text):
    assert faithfulness_problems(text, PA002) == []


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("C2 is not met and C1 is met.", "C2 stated as not_met but packet says missing"),
        ("C1 and C3 are met, but C4 is not met; C2 is missing.", "C4 stated as not_met"),
        ("C1 is met. C2 is missing. C3 does not meet the threshold.", "C3 stated as not_met"),
        ("Criterion C5 fails and C2 is missing.", "C5 stated as not_met"),
        ("C2 has status not_met due to a conflict.", "C2 stated as conflicting/not_met"),
        ("C2 is missing, not_met or conflicting.", "C2 stated as conflicting/missing/not_met"),
    ],
)
def test_wrong_status_claims_are_caught(text, problem):
    assert any(p.startswith(problem) for p in faithfulness_problems(text, PA002))


def test_metformin_is_not_read_as_met():
    text = "C2 is missing, and metformin therapy is documented for C3."
    assert not [p for p in faithfulness_problems(text, PA002) if "stated as" in p]


def test_sentence_count():
    assert sentence_count("One sentence with 7.0% inside.") == 1
    assert sentence_count("First. Second.") == 2
    assert sentence_count("No terminator") == 1
