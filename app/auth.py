import secrets
from collections.abc import Callable, Mapping
from enum import StrEnum

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.audit import AuditAction, AuditLog, Outcome
from app.config import Settings

ANONYMOUS_ACTOR = "anonymous"
UNKNOWN_ACTOR = "unknown"


class Role(StrEnum):
    NURSE = "nurse"
    ADMIN = "admin"


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor: str
    role: Role


def token_map(settings: Settings) -> dict[str, Principal]:
    return {
        settings.nurse_token.get_secret_value(): Principal(actor="nurse", role=Role.NURSE),
        settings.admin_token.get_secret_value(): Principal(actor="admin", role=Role.ADMIN),
    }


def bearer_token(authorization: str | None) -> str | None:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def authenticate(authorization: str | None, tokens: Mapping[str, Principal]) -> Principal | None:
    presented = bearer_token(authorization)
    if presented is None:
        return None
    match = None
    for token, principal in tokens.items():
        if secrets.compare_digest(token.encode(), presented.encode()):
            match = principal
    return match


def require(action: AuditAction, *allowed: Role) -> Callable[[Request], Principal]:
    """FastAPI dependency: resolve the caller, or audit the refusal and raise 401/403."""

    def dependency(request: Request) -> Principal:
        audit: AuditLog = request.app.state.audit
        header = request.headers.get("authorization")
        principal = authenticate(header, request.app.state.tokens)
        request_id = request.state.request_id
        resource = request.path_params.get("request_id")
        if principal is None:
            actor = UNKNOWN_ACTOR if bearer_token(header) else ANONYMOUS_ACTOR
            audit.append(
                actor=actor,
                role=None,
                action=action,
                request_id=request_id,
                resource=resource,
                outcome=Outcome.UNAUTHENTICATED,
            )
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if principal.role not in allowed:
            audit.append(
                actor=principal.actor,
                role=principal.role.value,
                action=action,
                request_id=request_id,
                resource=resource,
                outcome=Outcome.FORBIDDEN,
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "role not permitted for this action")
        return principal

    return dependency
