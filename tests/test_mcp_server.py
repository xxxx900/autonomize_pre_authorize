import asyncio

import pytest
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app.audit import AuditLog
from app.fhir_client import FhirClient
from mcp_server.server import BearerGate, build_server
from tests.conftest import NURSE, _bundled_resources, bearer, fake_fhir_transport


@pytest.fixture
def server(settings):
    transport = fake_fhir_transport(_bundled_resources())
    return build_server(settings, FhirClient(settings, transport))


def call(server, tool, **arguments):
    return asyncio.run(server.call_tool(tool, arguments))


@pytest.mark.parametrize("request_id", [f"PA-00{n}" for n in range(1, 8)])
def test_mcp_packet_equals_endpoint_packet(server, client, request_id):
    _, structured = call(server, "get_evidence_packet", request_id=request_id)
    expected = client.get(f"/requests/{request_id}/evidence", headers=bearer(NURSE)).json()
    assert structured == expected


def test_policy_tool_returns_the_policy(server):
    _, structured = call(server, "get_policy")
    assert structured["policy_id"] == "MP-SYN-021"


def test_unknown_request_is_a_tool_error(server):
    with pytest.raises(Exception, match="unknown or unreadable request"):
        call(server, "get_evidence_packet", request_id="PA-999")


def test_calls_are_audited_as_mcp_agent(settings):
    transport = fake_fhir_transport(_bundled_resources())
    built = build_server(settings, FhirClient(settings, transport))
    call(built, "get_evidence_packet", request_id="PA-001")
    with pytest.raises(Exception, match="unknown"):
        call(built, "get_evidence_packet", request_id="PA-999")
    events = AuditLog(settings.audit_db_path).events()
    assert [(e.actor, e.resource, e.outcome.value) for e in events] == [
        ("mcp-agent", "PA-001", "ok"),
        ("mcp-agent", "PA-999", "not_found"),
    ]


def test_gate_refuses_and_audits_requests_without_the_token(tmp_path):
    async def inner(scope, receive, send):
        await PlainTextResponse("in")(scope, receive, send)

    audit = AuditLog(tmp_path / "audit.db")
    gated = TestClient(BearerGate(inner, "secret", audit))
    assert gated.get("/").status_code == 401
    assert gated.get("/", headers=bearer("wrong")).status_code == 401
    assert gated.get("/", headers=bearer("secret")).text == "in"
    assert [(e.actor, e.role, e.action.value, e.outcome.value) for e in audit.events()] == [
        ("anonymous", None, "mcp.request", "unauthenticated"),
        ("unknown", None, "mcp.request", "unauthenticated"),
    ]
    assert audit.verify().valid
