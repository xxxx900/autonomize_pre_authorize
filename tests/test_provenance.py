import hashlib
import json

import pytest

from app.config import Settings
from tests.conftest import NURSE, RESOURCES, bearer, build_client
from tests.test_rules import EXPECTED, packet_for

POLICY_FILE = RESOURCES / "policy_MP-SYN-021.json"


def criterion(body: dict, cid: str) -> dict:
    return next(c for c in body["criteria"] if c["id"] == cid)


def facts(item: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for fact in item["facts"]:
        found.setdefault(fact["field"], []).append(fact["value"])
    return found


def test_conflicting_hba1c_shows_the_record_value_its_date_and_a_link(client):
    body = client.get("/requests/PA-006/evidence", headers=bearer(NURSE)).json()
    c2 = criterion(body, "C2")
    [item] = c2["evidence"]
    ref = f"{item['ref']['resource_type']}/{item['ref']['id']}"
    assert ref == f"Observation/{c2['conflicts'][0]['record_source']['id']}"
    assert item["fhir_url"] == f"http://fhir.test/fhir/{ref}"
    assert facts(item)["valueQuantity"] == ["6.4 %"]
    form = json.loads((RESOURCES / "requests" / "PA-006.json").read_text("utf-8"))
    assert facts(item)["effectiveDateTime"] == [form["prescriber_attestation"]["hba1c_date"]]
    assert any("4548-4" in v for v in facts(item)["code"])


def test_each_criterion_cites_its_policy_clause_and_parameters(client):
    body = client.get("/requests/PA-002/evidence", headers=bearer(NURSE)).json()
    c2 = criterion(body, "C2")["policy"]
    assert c2["section"] == "criteria[id=C2].fhir"
    assert c2["requirement"].startswith("HbA1c >= 7.0 %")
    params = {p["field"]: p["value"] for p in c2["parameters"]}
    assert params["value_min"] == "7.0"
    assert params["window_days"] == "90"
    assert params["code.code"] == "4548-4"
    c4 = {p["field"]: p["value"] for p in criterion(body, "C4")["policy"]["parameters"]}
    assert c4["codes[1].display"] == "Medullary thyroid carcinoma"


def test_packet_pins_the_policy_file_by_hash(client):
    source = client.get("/requests/PA-001/evidence", headers=bearer(NURSE)).json()["policy_source"]
    assert source["file"] == POLICY_FILE.name
    assert source["sha256"] == hashlib.sha256(POLICY_FILE.read_bytes()).hexdigest()
    assert source["effective"] == "2026-07-01"


@pytest.mark.parametrize("request_id", EXPECTED)
def test_every_cited_resource_has_an_evidence_entry_with_facts(request_id):
    packet = packet_for(request_id)
    for c in packet.criteria:
        cited = {*c.sources, *(x.record_source for x in c.conflicts if x.record_source)}
        assert {e.ref for e in c.evidence} == cited
        assert all(e.facts for e in c.evidence)
    assert [e.ref for e in packet.flagged_evidence] == packet.flagged_documents


def test_document_evidence_lists_type_and_date_but_never_content(client):
    body = client.get("/requests/PA-006/evidence", headers=bearer(NURSE)).json()
    [doc] = body["flagged_evidence"]
    assert set(facts(doc)) == {"type", "date"}


def test_links_use_the_public_fhir_url_when_set(settings):
    public = Settings(
        **{**settings.model_dump(), "fhir_public_base_url": "http://localhost:8080/fhir/"},
        _env_file=None,
    )
    body = build_client(public).get("/requests/PA-001/evidence", headers=bearer(NURSE)).json()
    urls = [e["fhir_url"] for c in body["criteria"] for e in c["evidence"]]
    assert urls and all(u.startswith("http://localhost:8080/fhir/") for u in urls)
    assert not any("//Observation" in u or "//Patient" in u for u in urls)
