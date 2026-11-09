"""Bearer-token authentication and the role check every protected route depends on."""

import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.audit.store import AuditLog
from app.config import Settings
from app.domain.enums import AuditAction, Outcome, Role
from app.domain.principal import Principal

ANONYMOUS_ACTOR = "anonymous"
UNKNOWN_ACTOR = "unknown"


def token_map(settings: Settings) -> dict[str, Principal]:
    """Map each configured token to the principal it identifies."""
    return {
        settings.nurse_token.get_secret_value(): Principal(actor="nurse", role=Role.NURSE),
        settings.admin_token.get_secret_value(): Principal(actor="admin", role=Role.ADMIN),
    }


def bearer_token(authorization: str | None) -> str | None:
    """The token from an `Authorization: Bearer <token>` header, or None."""
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def authenticate(authorization: str | None, tokens: Mapping[str, Principal]) -> Principal | None:
    """The principal whose token matches, compared in constant time against every token."""
    presented = bearer_token(authorization)
    if presented is None:
        return None
    match = None
    for token, principal in tokens.items():
        if secrets.compare_digest(token.encode(), presented.encode()):
            match = principal
    return match


@dataclass(frozen=True)
class RoleGuard:
    """A FastAPI dependency that resolves the caller or audits the refusal and raises 401/403.

    Use as `Depends(RoleGuard(action, roles))`.
    """

    action: AuditAction
    allowed: tuple[Role, ...]

    def __call__(self, request: Request) -> Principal:
        """Return the caller's principal when their role is allowed."""
        services = request.app.state.services
        audit: AuditLog = services.audit
        header = request.headers.get("authorization")
        principal = authenticate(header, services.tokens)
        if principal is None:
            actor = UNKNOWN_ACTOR if bearer_token(header) else ANONYMOUS_ACTOR
            self.refuse(audit, request, actor, None, Outcome.UNAUTHENTICATED)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if principal.role not in self.allowed:
            self.refuse(audit, request, principal.actor, principal.role, Outcome.FORBIDDEN)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "role not permitted for this action")
        return principal

    def refuse(
        self, audit: AuditLog, request: Request, actor: str, role: Role | None, outcome: Outcome
    ) -> None:
        """Write the audit row for a refused call."""
        audit.append(
            actor=actor,
            role=role.value if role else None,
            action=self.action,
            request_id=request.state.request_id,
            resource=request.path_params.get("request_id"),
            outcome=outcome,
        )
