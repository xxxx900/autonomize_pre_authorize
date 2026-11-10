"""MCP server exposing the evidence packet and the policy as read-only tools for agents."""

import hmac
import os
import uuid
from dataclasses import dataclass

import mcp
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.factory import create_app, record_start
from app.api.pipeline import EvidencePipeline, PipelineError
from app.api.services import Services
from app.audit.store import AuditLog
from app.clients.fhir_client import FhirClient
from app.config import Settings
from app.domain.audit import AuditContext
from app.domain.enums import AuditAction, Outcome
from app.domain.packet import EvidencePacket
from app.domain.policy import Policy
from app.security.auth import ANONYMOUS_ACTOR, UNKNOWN_ACTOR, bearer_token

ACTOR = "mcp-agent"
SERVER_ACTOR = "mcp-server"
HEALTH_PATH = "/health"


class BearerGate:
    """Refuses and audits every HTTP request that lacks the shared MCP token.

    The gate answers before reading the JSON-RPC body, so it cannot know which tool was asked
    for; the row records the action as mcp.request rather than guessing evidence.read.
    The health route is the one path that needs no token.
    """

    def __init__(self, app: ASGIApp, token: str, audit: AuditLog) -> None:
        """Wrap the MCP ASGI app."""
        self._app = app
        self._token = token.encode()
        self._audit = audit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass authorized requests through; answer 401 and audit everything else."""
        if scope["type"] == "http" and scope.get("path") != HEALTH_PATH:
            header = dict(scope["headers"]).get(b"authorization", b"").decode()
            presented = bearer_token(header)
            if presented is None or not hmac.compare_digest(presented.encode(), self._token):
                self._audit.append(
                    actor=UNKNOWN_ACTOR if presented else ANONYMOUS_ACTOR,
                    role=None,
                    action=AuditAction.MCP_REQUEST,
                    request_id=uuid.uuid4().hex,
                    resource=None,
                    outcome=Outcome.UNAUTHENTICATED,
                )
                response = PlainTextResponse("missing or invalid bearer token", status_code=401)
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


@dataclass(frozen=True)
class EvidenceTools:
    """The MCP tools. Each call is audited with actor mcp-agent."""

    pipeline: EvidencePipeline
    policy: Policy
    audit: AuditLog

    def record(
        self,
        action: AuditAction,
        resource: str,
        outcome: Outcome,
        request_id: str,
        context: AuditContext | None = None,
    ) -> None:
        """Write the audit row for one tool call."""
        self.audit.append(
            actor=ACTOR,
            role=None,
            action=action,
            request_id=request_id,
            resource=resource,
            outcome=outcome,
            context=context,
        )

    def get_evidence_packet(self, request_id: str) -> EvidencePacket:
        """Return the evidence packet for a prior-authorization request id such as PA-001."""
        trace_id = uuid.uuid4().hex
        try:
            run = self.pipeline.run(request_id, trace_id)
        except PipelineError as exc:
            self.record(AuditAction.EVIDENCE_READ, request_id, exc.outcome, trace_id, exc.context)
            raise ValueError(exc.detail) from exc
        self.record(AuditAction.EVIDENCE_READ, request_id, Outcome.OK, trace_id, run.context)
        return run.packet

    def get_policy(self) -> Policy:
        """Return the medical policy the criteria are evaluated against."""
        self.record(AuditAction.POLICY_READ, self.policy.policy_id, Outcome.OK, uuid.uuid4().hex)
        return self.policy


async def health(_: Request) -> JSONResponse:
    """Liveness for the MCP server, polled by the API's health report and by Docker."""
    return JSONResponse({"status": "ok"})


def server_for(services: Services, host: str = "0.0.0.0", port: int = 8001) -> FastMCP:
    """Build the MCP server on the API's services, so both serve identical packets."""
    tools = EvidenceTools(services.pipeline, services.policy, services.audit)
    server = FastMCP(
        "pa-evidence",
        instructions="Read-only prior-authorization evidence. Reports evidence, never decides.",
        host=host,
        port=port,
    )
    server.add_tool(tools.get_evidence_packet)
    server.add_tool(tools.get_policy)
    server.custom_route(HEALTH_PATH, methods=["GET"])(health)
    return server


def build_server(
    settings: Settings | None = None,
    fhir: FhirClient | None = None,
    host: str = "0.0.0.0",
    port: int = 8001,
) -> FastMCP:
    """Build the services from settings, then the MCP server on top of them."""
    return server_for(create_app(settings, fhir).state.services, host, port)


def main() -> None:
    """Run the MCP server behind the bearer gate. MCP_TOKEN is required."""
    token = os.environ.get("MCP_TOKEN", "")
    if not token:
        raise SystemExit("MCP_TOKEN must be set")
    port = int(os.environ.get("MCP_PORT", "8001"))
    services: Services = create_app(Settings()).state.services
    record_start(services, SERVER_ACTOR)
    gate = BearerGate(server_for(services, port=port).streamable_http_app(), token, services.audit)
    uvicorn.run(gate, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
