import json
import logging

import pytest

from app.logs import JsonFormatter
from tests.conftest import NURSE, bearer

EXPECTED_ROUTE = {
    "PA-001": "evidence_complete",
    "PA-002": "clinician_review",
    "PA-003": "clinician_review",
    "PA-004": "clinician_review",
    "PA-005": "clinician_review",
    "PA-006": "clinician_review",
    "PA-007": "clinician_review",
}


@pytest.mark.parametrize(("request_id", "route"), EXPECTED_ROUTE.items())
def test_route_for_each_supplied_request(client, request_id, route):
    response = client.get(f"/requests/{request_id}/evidence", headers=bearer(NURSE))
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == route
    assert body["request_id"] == request_id
    assert body["summary"] is None


def test_unknown_or_malformed_request_id_is_404(client):
    assert client.get("/requests/PA-999/evidence", headers=bearer(NURSE)).status_code == 404
    assert client.get("/requests/..%2Fpolicy/evidence", headers=bearer(NURSE)).status_code == 404


def test_member_missing_from_fhir_is_404(make_client):
    client = make_client(resources=[])
    assert client.get("/requests/PA-001/evidence", headers=bearer(NURSE)).status_code == 404


def test_fhir_outage_is_502(make_client):
    client = make_client(reachable=False)
    assert client.get("/requests/PA-001/evidence", headers=bearer(NURSE)).status_code == 502


def test_policy_endpoint_returns_the_loaded_policy(client):
    assert client.get("/policy", headers=bearer(NURSE)).json()["policy_id"] == "MP-SYN-021"


def test_request_log_line_has_only_allow_listed_fields(client, caplog):
    caplog.set_level(logging.INFO, logger="pa.api")
    client.get("/requests/PA-006/evidence", headers=bearer(NURSE))
    record = next(r for r in caplog.records if r.name == "pa.api")
    line = json.loads(JsonFormatter().format(record))
    assert set(line) == {
        "ts",
        "level",
        "event",
        "request_id",
        "method",
        "route",
        "status",
        "duration_ms",
    }
    assert line["route"] == "/requests/{request_id}/evidence"
    assert line["status"] == 200


def test_unlisted_log_fields_are_dropped():
    record = logging.getLogger("pa.test").makeRecord(
        "pa.test",
        logging.INFO,
        "f",
        1,
        "",
        (),
        None,
        extra={"fields": {"event": "x", "hba1c": 6.4}},
    )
    assert "hba1c" not in json.loads(JsonFormatter().format(record))
