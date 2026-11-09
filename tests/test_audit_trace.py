import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.audit.hash_chain import GENESIS_HASH, compute_hash
from app.audit.store import AuditLog
from app.domain.audit import AuditContext
from app.domain.enums import AuditAction, Outcome, SummaryFallback, SummarySource
from app.domain.packet import SummaryTrace
from app.main import create_app
from tests.conftest import ADMIN, NURSE, bearer

OLD_SCHEMA = """
CREATE TABLE audit_event (
    seq INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, role TEXT,
    action TEXT NOT NULL, request_id TEXT NOT NULL, resource TEXT, outcome TEXT NOT NULL,
    prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
"""


def audit_rows(client: TestClient, **params) -> list[dict]:
    return client.get("/audit", headers=bearer(ADMIN), params=params).json()["events"]


def test_evidence_row_traces_timing_phi_subject_policy_and_summary(client):
    response = client.get("/requests/PA-004/evidence", headers=bearer(NURSE))
    trace_id = response.headers["X-Request-ID"]
    [row] = audit_rows(client, request_id=trace_id)
    context = row["context"]
    assert (row["actor"], row["action"], row["resource"]) == ("nurse", "evidence.read", "PA-004")
    assert context["http_route"] == "/requests/{request_id}/evidence"
    assert context["status_code"] == 200
    assert context["duration_ms"] > 0
    assert context["subject"].startswith("Patient/")
    assert "Observation" in context["phi_resource_types"]
    assert context["phi_resources_read"] > 1
    assert context["policy_version"] == "2026.1"
    assert len(context["policy_sha256"]) == 64
    summary = context["summary"]
    assert (summary["source"], summary["fallback"]) == ("template", "not_configured")


def test_packet_trace_uses_the_same_id_as_the_header_and_the_audit_row(client):
    response = client.get("/requests/PA-001/evidence", headers=bearer(NURSE))
    trace = response.json()["trace"]
    assert trace["trace_id"] == response.headers["X-Request-ID"]
    assert trace["duration_ms"] >= trace["fhir_ms"] + trace["rules_ms"]
    assert trace["fhir_resources_read"] > 1


def test_failed_read_records_the_error_and_the_member_it_touched(make_client):
    client = make_client(resources=[])
    client.get("/requests/PA-001/evidence", headers=bearer(NURSE))
    row = audit_rows(client, action="evidence.read")[0]
    assert row["outcome"] == "not_found"
    assert row["context"]["error"] == "member not found in FHIR"
    assert row["context"]["subject"].startswith("Patient/")
    assert row["context"]["status_code"] == 404


def test_audit_filters_narrow_rows_but_the_chain_covers_all(client):
    for rid in ("PA-001", "PA-002", "PA-999"):
        client.get(f"/requests/{rid}/evidence", headers=bearer(NURSE))
    body = client.get("/audit", headers=bearer(ADMIN), params={"resource": "PA-002"}).json()
    assert [e["resource"] for e in body["events"]] == ["PA-002"]
    assert body["chain"]["valid"] and body["chain"]["checked"] == body["total"] == 3
    failed = audit_rows(client, outcome="not_found")
    assert [e["resource"] for e in failed] == ["PA-999"]


def test_service_start_records_config_without_secrets(settings, fhir_client):
    with TestClient(create_app(settings, fhir_client)) as client:
        [start] = audit_rows(client, action="service.start")
    config = start["context"]["config"]
    assert start["actor"] == "system"
    assert config["summary_model"] == settings.summary_model
    assert config["prompt_version"] == "summary-v4"
    assert len(start["context"]["policy_sha256"]) == 64
    flat = str(start)
    assert NURSE not in flat and ADMIN not in flat


def test_context_with_floats_and_nested_trace_still_verifies(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    context = AuditContext(
        duration_ms=12.3,
        summary=SummaryTrace(
            source=SummarySource.TEMPLATE, latency_ms=0.1, fallback=SummaryFallback.REJECTED
        ),
    )
    log.append(
        actor="nurse",
        role="nurse",
        action=AuditAction.EVIDENCE_READ,
        request_id="r",
        resource="PA-001",
        outcome=Outcome.OK,
        context=context,
    )
    assert log.events()[0].context == context
    assert log.verify().valid


def test_database_from_before_the_context_column_keeps_verifying(tmp_path):
    path = tmp_path / "audit.db"
    row = {
        "seq": 1,
        "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "actor": "nurse",
        "role": "nurse",
        "action": "evidence.read",
        "request_id": "old",
        "resource": "PA-001",
        "outcome": "ok",
        "prev_hash": GENESIS_HASH,
    }
    row["hash"] = compute_hash(row)
    with closing(sqlite3.connect(path)) as db:
        db.executescript(OLD_SCHEMA)
        db.execute(
            "INSERT INTO audit_event VALUES (:seq, :ts, :actor, :role, :action, :request_id,"
            " :resource, :outcome, :prev_hash, :hash)",
            row,
        )
        db.commit()
    log = AuditLog(path)
    log.append(
        actor="admin",
        role="admin",
        action=AuditAction.AUDIT_READ,
        request_id="new",
        resource=None,
        outcome=Outcome.OK,
        context=AuditContext(duration_ms=1.0),
    )
    assert [e.context for e in log.events()] == [None, AuditContext(duration_ms=1.0)]
    assert log.verify().valid
