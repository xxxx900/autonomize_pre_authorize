import pytest

from app.safety import cited_sources, faithfulness_problems, forbidden_words, missing_sources
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
