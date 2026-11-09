"""GET /requests/{request_id}/evidence: the nurse-facing evidence packet."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auditing import audit_call
from app.api.dependencies import EvidenceCaller, ServicesDep
from app.api.pipeline import PipelineError
from app.domain.enums import AuditAction, Outcome
from app.domain.packet import EvidencePacket

router = APIRouter()


@router.get("/requests/{request_id}/evidence", response_model=EvidencePacket)
def get_evidence(
    request_id: str,
    request: Request,
    principal: EvidenceCaller,
    services: ServicesDep,
    summary_model: str | None = Query(
        default=None, description="One of GET /catalog summary_models.choices; default if unset"
    ),
) -> EvidencePacket:
    """Build the packet for one request and audit the read, including failures."""
    try:
        run = services.pipeline.run(request_id, request.state.request_id, summary_model)
    except PipelineError as exc:
        audit_call(
            services.audit,
            principal,
            request,
            AuditAction.EVIDENCE_READ,
            request_id,
            exc.outcome,
            exc.status_code,
            exc.context,
        )
        raise HTTPException(exc.status_code, exc.detail) from exc
    audit_call(
        services.audit,
        principal,
        request,
        AuditAction.EVIDENCE_READ,
        request_id,
        Outcome.OK,
        200,
        run.context,
    )
    return run.packet
