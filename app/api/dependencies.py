"""Typed FastAPI dependencies: the caller for each protected action, and the shared services."""

from typing import Annotated

from fastapi import Depends

from app.api.services import Services, get_services
from app.domain.enums import AuditAction, Role
from app.domain.principal import Principal
from app.security.auth import RoleGuard

ANY_ROLE = (Role.NURSE, Role.ADMIN)
ADMIN_ONLY = (Role.ADMIN,)

EvidenceCaller = Annotated[Principal, Depends(RoleGuard(AuditAction.EVIDENCE_READ, ANY_ROLE))]
PolicyCaller = Annotated[Principal, Depends(RoleGuard(AuditAction.POLICY_READ, ANY_ROLE))]
AuditCaller = Annotated[Principal, Depends(RoleGuard(AuditAction.AUDIT_READ, ADMIN_ONLY))]
CatalogCaller = Annotated[Principal, Depends(RoleGuard(AuditAction.CATALOG_READ, ANY_ROLE))]
HealthCaller = Annotated[Principal, Depends(RoleGuard(AuditAction.HEALTH_READ, ADMIN_ONLY))]
ServicesDep = Annotated[Services, Depends(get_services)]
