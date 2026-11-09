import json
import shutil
import sqlite3
from functools import partial

import httpx
import pytest
from starlette.testclient import TestClient

from app.audit.store import AuditLog
from app.config import Settings
from app.main import create_app
from app.summary.summarizer import Summarizer
from mcp_server.server import BearerGate, build_server
from tests.conftest import ADMIN, NURSE, RESOURCES, bearer, build_client

MODEL = "m:3b"


def fake_ollama(pulled: bool, loaded: bool, request: httpx.Request) -> httpx.Response:
    models = [{"name": MODEL, "digest": "abcdef0123456789"}]
    answers = {
        "/api/version": {"version": "0.12.6"},
        "/api/tags": {"models": models if pulled else []},
        "/api/ps": {"models": models if loaded else []},
    }
    return httpx.Response(200, json=answers[request.url.path])


def ollama_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


def summarizer_with(handler) -> Summarizer:
    return Summarizer("http://ollama.test", MODEL, 5, transport=httpx.MockTransport(handler))


def details(client: TestClient) -> dict:
    response = client.get("/health/details", headers=bearer(ADMIN))
    assert response.status_code == 200
    return {c["component"]: c for c in response.json()["components"]} | {
        "_state": response.json()["state"]
    }


def test_ready_lists_each_required_component(client):
    body = client.get("/ready").json()
    assert body == {
        "status": "ready",
        "components": {"fhir": "up", "audit_log": "up", "policy": "up", "request_store": "up"},
    }


def test_ready_is_503_and_names_fhir_when_fhir_is_down(make_client):
    response = make_client(reachable=False).get("/ready")
    assert response.status_code == 503
    assert response.json()["components"]["fhir"] == "down"


def test_missing_request_store_makes_the_service_not_ready(settings, tmp_path):
    shutil.copy(RESOURCES / settings.policy_file, tmp_path / settings.policy_file)
    moved = Settings(**{**settings.model_dump(), "resources_dir": tmp_path}, _env_file=None)
    response = build_client(moved).get("/ready")
    assert response.status_code == 503
    assert response.json()["components"]["request_store"] == "down"


def test_details_is_admin_only_and_audited(client):
    assert client.get("/health/details", headers=bearer(NURSE)).status_code == 403
    details(client)
    actions = [e["action"] for e in client.get("/audit", headers=bearer(ADMIN)).json()["events"]]
    assert actions == ["health.read", "health.read"]


def test_details_report_fhir_versions_and_a_degraded_unconfigured_model(client):
    report = details(client)
    assert report["fhir"]["state"] == "up"
    assert report["fhir"]["facts"]["fhir_version"] == "4.0.1"
    assert report["summary_model"]["state"] == "degraded"
    assert report["audit_log"]["detail"] == "writable; hash chain intact"
    assert report["_state"] == "degraded"


@pytest.mark.parametrize(
    ("pulled", "loaded", "state", "in_memory"),
    [(True, True, "up", "yes"), (True, False, "up", "no"), (False, False, "degraded", "no")],
)
def test_model_probe_reports_pulled_digest_and_memory(
    settings, fhir_client, pulled, loaded, state, in_memory
):
    summarizer = summarizer_with(partial(fake_ollama, pulled, loaded))
    client = TestClient(create_app(settings, fhir_client, summarizer))
    model = details(client)["summary_model"]
    assert model["state"] == state
    assert model["facts"]["loaded_in_memory"] == in_memory
    assert model["facts"]["ollama_version"] == "0.12.6"
    if pulled:
        assert model["facts"]["digest"] == "abcdef012345"
        assert details(client)["_state"] == "up"


def test_unreachable_ollama_degrades_but_keeps_the_service_ready(settings, fhir_client):
    client = TestClient(create_app(settings, fhir_client, summarizer_with(ollama_down)))
    assert details(client)["summary_model"]["state"] == "degraded"
    assert client.get("/ready").status_code == 200


def test_policy_file_edited_after_start_is_flagged(settings, tmp_path):
    shutil.copytree(RESOURCES / "requests", tmp_path / "requests")
    policy_path = tmp_path / settings.policy_file
    shutil.copy(RESOURCES / settings.policy_file, policy_path)
    moved = Settings(**{**settings.model_dump(), "resources_dir": tmp_path}, _env_file=None)
    client = build_client(moved)
    assert details(client)["policy"]["state"] == "up"
    edited = json.loads(policy_path.read_text("utf-8")) | {"version": "2026.2"}
    policy_path.write_text(json.dumps(edited), "utf-8")
    policy = details(client)["policy"]
    assert policy["state"] == "degraded"
    assert policy["facts"]["version"] == "2026.1"


def test_broken_audit_chain_marks_the_audit_log_down(client, settings):
    client.get("/requests/PA-001/evidence", headers=bearer(NURSE))
    with sqlite3.connect(settings.audit_db_path) as db:
        db.execute("DROP TRIGGER audit_event_no_update")
        db.execute("UPDATE audit_event SET actor = 'admin' WHERE seq = 1")
    audit = details(client)["audit_log"]
    assert audit["state"] == "down"
    assert audit["detail"] == "hash chain broken at seq 1"


def test_mcp_health_route_needs_no_token(settings, fhir_client, tmp_path):
    server = build_server(settings, fhir_client)
    gate = TestClient(BearerGate(server.streamable_http_app(), "secret", AuditLog(tmp_path / "a")))
    assert gate.get("/health").json() == {"status": "ok"}
    assert gate.get("/mcp").status_code == 401


def test_an_allowed_model_that_is_not_pulled_degrades_the_model_check(settings, fhir_client):
    summarizer = Summarizer(
        "http://ollama.test",
        MODEL,
        5,
        httpx.MockTransport(partial(fake_ollama, True, True)),
        choices=("absent:1b",),
    )
    client = TestClient(create_app(settings, fhir_client, summarizer))
    model = details(client)["summary_model"]
    assert model["state"] == "degraded"
    assert model["facts"]["allowed_not_pulled"] == "absent:1b"
    assert model["facts"]["allowed_models"] == f"{MODEL}, absent:1b"
