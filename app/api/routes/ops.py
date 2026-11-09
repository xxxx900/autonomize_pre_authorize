"""Liveness, readiness, and the detailed component health report."""

from fastapi import APIRouter, Request

from app.api.auditing import audit_call
from app.api.dependencies import HealthCaller, ServicesDep
from app.api.responses import PrettyJSONResponse
from app.domain.enums import AuditAction, HealthState, Outcome
from app.domain.health import HealthReport, ReadinessReport
from app.ops.health import overall_state

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up and answering. Checks nothing else."""
    return {"status": "ok"}


@router.get("/ready", response_model=ReadinessReport)
def ready(services: ServicesDep) -> PrettyJSONResponse:
    """Readiness: 200 when every required component is up or degraded, else 503."""
    checks = services.probes.readiness()
    state = overall_state(checks)
    is_ready = state is not HealthState.DOWN
    report = ReadinessReport(
        status="ready" if is_ready else "not_ready",
        components={c.component: c.state for c in checks},
    )
    return PrettyJSONResponse(report.model_dump(mode="json"), status_code=200 if is_ready else 503)


@router.get("/health/details", response_model=HealthReport)
def health_details(
    request: Request, principal: HealthCaller, services: ServicesDep
) -> HealthReport:
    """Probe every component, with versions, latencies, and the model's state (admin only)."""
    report = services.probes.details()
    audit_call(services.audit, principal, request, AuditAction.HEALTH_READ, None, Outcome.OK, 200)
    return report
