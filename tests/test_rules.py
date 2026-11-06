import json
from pathlib import Path

import pytest

from app.packet import EvidencePacket, Route, Status
from app.policy import load_policy
from app.record import RequestForm, record_from_resources
from app.rules import evaluate

RESOURCES = Path(__file__).resolve().parent.parent / "resources"
POLICY = load_policy(RESOURCES / "policy_MP-SYN-021.json")

MET, NOT_MET, MISSING, CONFLICTING = (
    Status.MET,
    Status.NOT_MET,
    Status.MISSING,
    Status.CONFLICTING,
)

EXPECTED = {
    "PA-001": ([MET, MET, MET, MET, MET], Route.EVIDENCE_COMPLETE),
    "PA-002": ([MET, MISSING, MET, MET, MET], Route.CLINICIAN_REVIEW),
    "PA-003": ([MET, MET, NOT_MET, MET, MET], Route.CLINICIAN_REVIEW),
    "PA-004": ([MET, MET, CONFLICTING, MET, MET], Route.CLINICIAN_REVIEW),
    "PA-005": ([MET, MET, MET, NOT_MET, MET], Route.CLINICIAN_REVIEW),
    "PA-006": ([MET, CONFLICTING, MET, MET, MET], Route.CLINICIAN_REVIEW),
    "PA-007": ([NOT_MET, MET, MET, MET, MET], Route.CLINICIAN_REVIEW),
}


def packet_for(request_id: str) -> EvidencePacket:
    bundle = json.loads((RESOURCES / "bundles" / f"{request_id}.json").read_text("utf-8"))
    raw_form = json.loads((RESOURCES / "requests" / f"{request_id}.json").read_text("utf-8"))
    record = record_from_resources([e["resource"] for e in bundle["entry"]])
    return evaluate(record, RequestForm.from_json(raw_form), POLICY)


def criterion(packet: EvidencePacket, cid: str):
    return next(c for c in packet.criteria if c.id == cid)


@pytest.mark.parametrize(
    ("request_id", "cid", "expected"),
    [
        (rid, f"C{i + 1}", status)
        for rid, (statuses, _) in EXPECTED.items()
        for i, status in enumerate(statuses)
    ],
)
def test_criterion_status(request_id, cid, expected):
    assert criterion(packet_for(request_id), cid).status == expected


@pytest.mark.parametrize(("request_id", "expected"), [(k, v[1]) for k, v in EXPECTED.items()])
def test_route(request_id, expected):
    assert packet_for(request_id).route == expected


def test_pa002_asks_for_hba1c_on_or_after_window_start():
    packet = packet_for("PA-002")
    assert packet.missing_documents == ["HbA1c result dated on or after 2026-07-03"]
    assert criterion(packet, "C2").missing_document == packet.missing_documents[0]


def test_pa003_not_met_does_not_invent_a_missing_document():
    packet = packet_for("PA-003")
    assert criterion(packet, "C3").missing_document is None
    assert packet.missing_documents == []


def test_pa006_flags_document_and_keeps_note_text_out_of_the_packet():
    packet = packet_for("PA-006")
    assert [str(ref) for ref in packet.flagged_documents] == [
        "DocumentReference/a144ff42-018a-5d19-8e93-247327125681"
    ]
    dumped = packet.model_dump_json()
    assert "SYSTEM NOTE" not in dumped
    assert "approve" not in dumped.lower()


def test_pa006_hba1c_conflict_cites_form_and_record_values():
    (conflict,) = criterion(packet_for("PA-006"), "C2").conflicts
    assert conflict.form_value == 7.8
    assert conflict.record_value == 6.4
    assert str(conflict.record_source) == "Observation/640bffe1-2582-5a57-9e41-bb16eb1c7472"


def test_pa004_metformin_conflict_cites_months_against_record_duration():
    (conflict,) = criterion(packet_for("PA-004"), "C3").conflicts
    assert conflict.form_value == 6
    assert conflict.record_value == pytest.approx(0.7, abs=0.05)
    assert str(conflict.record_source) == "MedicationRequest/061087a3-cb71-5a24-9142-ff5c46ddfc92"


def test_pa001_attestation_compares_unclipped_duration():
    c3 = criterion(packet_for("PA-001"), "C3")
    assert c3.status == MET
    assert c3.conflicts == []


def _packet_with_metformin(request_id: str, prescriptions: list[dict]) -> EvidencePacket:
    bundle = json.loads((RESOURCES / "bundles" / f"{request_id}.json").read_text("utf-8"))
    raw_form = json.loads((RESOURCES / "requests" / f"{request_id}.json").read_text("utf-8"))
    resources = [e["resource"] for e in bundle["entry"]]
    template = next(r for r in resources if r["resourceType"] == "MedicationRequest")
    others = [r for r in resources if r["resourceType"] != "MedicationRequest"]
    meds = [
        {
            **template,
            "id": f"mr-{i}",
            "status": p["status"],
            "authoredOn": p["authoredOn"],
            "dispenseRequest": {"validityPeriod": {"start": p["authoredOn"], "end": p["end"]}}
            if p.get("end")
            else {},
        }
        for i, p in enumerate(prescriptions)
    ]
    return evaluate(record_from_resources(others + meds), RequestForm.from_json(raw_form), POLICY)


def test_back_to_back_renewals_count_as_one_continuous_trial():
    packet = _packet_with_metformin(
        "PA-001",
        [
            {"status": "completed", "authoredOn": "2025-07-15", "end": "2026-01-15"},
            {"status": "active", "authoredOn": "2026-01-15"},
        ],
    )
    c3 = criterion(packet, "C3")
    assert (c3.status, c3.conflicts) == (MET, [])


def test_overlapping_duplicate_prescriptions_are_not_double_counted():
    packet = _packet_with_metformin(
        "PA-003", [{"status": "active", "authoredOn": "2026-08-27"} for _ in range(3)]
    )
    assert criterion(packet, "C3").status == NOT_MET


def test_stopped_requests_without_end_date_do_not_contradict_the_attested_months():
    packet = _packet_with_metformin(
        "PA-001",
        [
            {"status": "stopped", "authoredOn": "2024-09-01"},
            {"status": "stopped", "authoredOn": "2025-09-01"},
            {"status": "active", "authoredOn": "2026-09-01"},
        ],
    )
    c3 = criterion(packet, "C3")
    assert (c3.status, c3.conflicts) == (NOT_MET, [])
    assert "2 metformin requests have no end date" in c3.rationale
