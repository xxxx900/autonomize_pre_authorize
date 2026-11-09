"""Write the audit row for a call that passed authentication."""

from fastapi import Request

from app.api.middleware import route_template
from app.audit.store import AuditLog
from app.domain.audit import AuditContext
from app.domain.enums import AuditAction, Outcome
from app.domain.principal import Principal


def audit_call(
    audit: AuditLog,
    principal: Principal,
    request: Request,
    action: AuditAction,
    resource: str | None,
    outcome: Outcome,
    status_code: int,
    context: AuditContext | None = None,
) -> None:
    """Append one row, adding the route template and HTTP status to the context."""
    base = context or AuditContext()
    audit.append(
        actor=principal.actor,
        role=principal.role.value,
        action=action,
        request_id=request.state.request_id,
        resource=resource,
        outcome=outcome,
        context=base.model_copy(
            update={"http_route": route_template(request), "status_code": status_code}
        ),
    )
