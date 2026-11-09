"""GET /policy and GET /audit: the policy text and the audit trail."""

from fastapi import APIRouter, Query, Request

from app.api.auditing import audit_call
from app.api.dependencies import AuditCaller, PolicyCaller, ServicesDep
from app.audit.hash_chain import verify_chain
from app.domain.audit import AuditContext, AuditFilter, AuditReport
from app.domain.enums import AuditAction, Outcome
from app.domain.policy import Policy

router = APIRouter()
MAX_AUDIT_ROWS = 1000


@router.get("/policy", response_model=Policy)
def get_policy(request: Request, principal: PolicyCaller, services: ServicesDep) -> Policy:
    """Return the loaded policy, with its source file hash and per-criterion citations."""
    policy = services.policy
    audit_call(
        services.audit,
        principal,
        request,
        AuditAction.POLICY_READ,
        policy.policy_id,
        Outcome.OK,
        200,
        AuditContext(policy_version=policy.version),
    )
    return policy


@router.get("/audit", response_model=AuditReport)
def get_audit(
    request: Request,
    principal: AuditCaller,
    services: ServicesDep,
    action: AuditAction | None = None,
    actor: str | None = None,
    resource: str | None = None,
    outcome: Outcome | None = None,
    request_id: str | None = None,
    limit: int = Query(default=MAX_AUDIT_ROWS, ge=1, le=MAX_AUDIT_ROWS),
) -> AuditReport:
    """Verify the whole chain, then return the newest matching rows (oldest first).

    Filter with `action`, `actor`, `resource` (such as PA-004), `outcome`, or `request_id`
    (the X-Request-ID of the call to trace).
    """
    events = services.audit.events()
    chain = verify_chain(events)
    wanted = AuditFilter(
        action=action, actor=actor, resource=resource, outcome=outcome, request_id=request_id
    )
    matched = [e for e in events if wanted.matches(e)]
    report = AuditReport(chain=chain, total=len(events), events=matched[-limit:])
    audit_call(services.audit, principal, request, AuditAction.AUDIT_READ, None, Outcome.OK, 200)
    return report
