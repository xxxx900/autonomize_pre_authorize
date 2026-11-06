import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from app.audit import AuditAction, AuditEvent, AuditLog, ChainStatus, Outcome, verify_chain
from app.auth import Principal, Role, require, token_map
from app.config import Settings
from app.fhir_client import FhirClient, FhirError, PatientNotFound
from app.logs import configure_logging, log_event
from app.packet import EvidencePacket
from app.policy import Policy, load_policy
from app.record import RequestForm
from app.rules import evaluate
from app.safety import missing_sources

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ANY_ROLE = (Role.NURSE, Role.ADMIN)

EvidenceCaller = Annotated[Principal, Depends(require(AuditAction.EVIDENCE_READ, *ANY_ROLE))]
PolicyCaller = Annotated[Principal, Depends(require(AuditAction.POLICY_READ, *ANY_ROLE))]
AuditCaller = Annotated[Principal, Depends(require(AuditAction.AUDIT_READ, Role.ADMIN))]

logger = logging.getLogger("pa.api")


class AuditReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain: ChainStatus
    events: list[AuditEvent]


def attach_summary(packet: EvidencePacket) -> EvidencePacket:
    return packet


def create_app(settings: Settings | None = None, fhir: FhirClient | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    policy = load_policy(settings.policy_path)
    owned_fhir = fhir is None
    fhir = fhir or FhirClient(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owned_fhir:
            fhir.close()

    app = FastAPI(title="PA Evidence Packet", lifespan=lifespan)
    app.state.audit = AuditLog(settings.audit_db_path)
    app.state.tokens = token_map(settings)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        finally:
            route = request.scope.get("route")
            log_event(
                logger,
                event="request",
                request_id=request.state.request_id,
                method=request.method,
                route=route.path if route else "unmatched",
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )

    def audit_call(
        principal: Principal,
        request: Request,
        action: AuditAction,
        resource: str | None,
        outcome: Outcome,
    ) -> None:
        app.state.audit.append(
            actor=principal.actor,
            role=principal.role.value,
            action=action,
            request_id=request.state.request_id,
            resource=resource,
            outcome=outcome,
        )

    def load_form(request_id: str) -> RequestForm:
        if not REQUEST_ID_PATTERN.match(request_id):
            raise FileNotFoundError(request_id)
        raw = json.loads((settings.resources_dir / "requests" / f"{request_id}.json").read_text())
        return RequestForm.from_json(raw)

    @app.get("/requests/{request_id}/evidence", response_model=EvidencePacket)
    def evidence(
        request_id: str,
        request: Request,
        principal: EvidenceCaller,
    ):
        try:
            form = load_form(request_id)
        except (FileNotFoundError, ValidationError, KeyError, json.JSONDecodeError) as exc:
            missing = isinstance(exc, FileNotFoundError)
            audit_call(
                principal,
                request,
                AuditAction.EVIDENCE_READ,
                request_id,
                Outcome.NOT_FOUND if missing else Outcome.ERROR,
            )
            raise HTTPException(404 if missing else 422, "unknown or unreadable request") from exc
        if form.policy_id != policy.policy_id:
            audit_call(principal, request, AuditAction.EVIDENCE_READ, request_id, Outcome.ERROR)
            raise HTTPException(422, "request references a policy this service does not hold")
        try:
            patient = fhir.patient_record(form.patient_id)
            packet = attach_summary(evaluate(patient, form, policy))
            unverified = missing_sources(packet, fhir.exists)
        except PatientNotFound as exc:
            audit_call(principal, request, AuditAction.EVIDENCE_READ, request_id, Outcome.NOT_FOUND)
            raise HTTPException(404, "member not found in FHIR") from exc
        except FhirError as exc:
            audit_call(principal, request, AuditAction.EVIDENCE_READ, request_id, Outcome.ERROR)
            raise HTTPException(502, "FHIR server unavailable") from exc
        if unverified:
            audit_call(principal, request, AuditAction.EVIDENCE_READ, request_id, Outcome.ERROR)
            raise HTTPException(502, "a cited source could not be verified in FHIR")
        audit_call(principal, request, AuditAction.EVIDENCE_READ, request_id, Outcome.OK)
        return packet

    @app.get("/policy", response_model=Policy)
    def get_policy(
        request: Request,
        principal: PolicyCaller,
    ):
        audit_call(principal, request, AuditAction.POLICY_READ, policy.policy_id, Outcome.OK)
        return policy

    @app.get("/audit", response_model=AuditReport)
    def get_audit(
        request: Request,
        principal: AuditCaller,
    ):
        events = app.state.audit.events()
        report = AuditReport(chain=verify_chain(events), events=events)
        audit_call(principal, request, AuditAction.AUDIT_READ, None, Outcome.OK)
        return report

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        if fhir.ping():
            return {"status": "ready"}
        return JSONResponse({"status": "fhir_unreachable"}, status_code=503)

    return app
