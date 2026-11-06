import hmac
import os
import uuid

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.audit import AuditAction, Outcome
from app.config import Settings
from app.fhir_client import FhirClient
from app.main import create_app
from app.packet import EvidencePacket
from app.pipeline import PipelineError
from app.policy import Policy

ACTOR = "mcp-agent"


class BearerGate:
    """Refuses every HTTP request that lacks the shared MCP token. Lifespan passes through."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            scheme, _, presented = headers.get(b"authorization", b"").decode().partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(
                presented.strip().encode(), self._token
            ):
                response = PlainTextResponse("missing or invalid bearer token", status_code=401)
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def build_server(
    settings: Settings | None = None,
    fhir: FhirClient | None = None,
    host: str = "0.0.0.0",
    port: int = 8001,
) -> FastMCP:
    api = create_app(settings, fhir)
    audit = api.state.audit
    server = FastMCP(
        "pa-evidence",
        instructions="Read-only prior-authorization evidence. Reports evidence, never decides.",
        host=host,
        port=port,
    )

    def record(action: AuditAction, resource: str, outcome: Outcome) -> None:
        audit.append(
            actor=ACTOR,
            role=None,
            action=action,
            request_id=uuid.uuid4().hex,
            resource=resource,
            outcome=outcome,
        )

    @server.tool()
    def get_evidence_packet(request_id: str) -> EvidencePacket:
        """Return the evidence packet for a prior-authorization request id such as PA-001."""
        try:
            packet = api.state.build_packet(request_id)
        except PipelineError as exc:
            record(AuditAction.EVIDENCE_READ, request_id, exc.outcome)
            raise ValueError(exc.detail) from exc
        record(AuditAction.EVIDENCE_READ, request_id, Outcome.OK)
        return packet

    @server.tool()
    def get_policy() -> Policy:
        """Return the medical policy the criteria are evaluated against."""
        policy: Policy = api.state.policy
        record(AuditAction.POLICY_READ, policy.policy_id, Outcome.OK)
        return policy

    return server


def main() -> None:
    token = os.environ.get("MCP_TOKEN", "")
    if not token:
        raise SystemExit("MCP_TOKEN must be set")
    port = int(os.environ.get("MCP_PORT", "8001"))
    server = build_server(port=port)
    uvicorn.run(BearerGate(server.streamable_http_app(), token), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
