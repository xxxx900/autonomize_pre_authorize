"""The long-lived objects one app instance shares, built once and stored on `app.state`."""

from dataclasses import dataclass

from fastapi import Request

from app.api.pipeline import EvidencePipeline
from app.audit.store import AuditLog
from app.clients.fhir_client import FhirClient
from app.config import Settings
from app.domain.policy import Policy
from app.domain.principal import Principal
from app.ops.health import HealthProbes
from app.summary.summarizer import Summarizer


@dataclass(frozen=True)
class Services:
    """Settings, clients, and stores for one app instance.

    `owns_fhir` is False when a caller passed in its own FHIR client, which it then closes.
    """

    settings: Settings
    policy: Policy
    fhir: FhirClient
    owns_fhir: bool
    summarizer: Summarizer
    audit: AuditLog
    tokens: dict[str, Principal]
    pipeline: EvidencePipeline
    probes: HealthProbes


def get_services(request: Request) -> Services:
    """FastAPI dependency: the Services of the app handling this request."""
    return request.app.state.services
