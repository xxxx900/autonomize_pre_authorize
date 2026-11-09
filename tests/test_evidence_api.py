import json
import logging

import pytest

from app.ops.logs import JsonFormatter
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
    assert body["summary_source"] == "template"
    assert body["summary"]


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


@pytest.mark.parametrize("path", ["/", "/audit/view", "/static/dom.js", "/static/style.css"])
def test_pages_load_without_a_token_and_never_use_innerhtml(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "innerHTML" not in response.text
    assert "http://" not in response.text and "https://" not in response.text


def test_json_responses_are_indented_for_people(client):
    assert client.get("/health").text == '{\n  "status": "ok"\n}'


def test_request_form_in_the_extra_directory_is_served(settings, make_client, tmp_path):
    form = json.loads((settings.resources_dir / "requests" / "PA-001.json").read_text("utf-8"))
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "EXTRA-001.json").write_text(json.dumps({**form, "request_id": "EXTRA-001"}))
    settings.extra_requests_dir = extra
    response = make_client().get("/requests/EXTRA-001/evidence", headers=bearer(NURSE))
    assert response.status_code == 200
    assert response.json()["request_id"] == "EXTRA-001"
