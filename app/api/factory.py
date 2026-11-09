"""Assemble the FastAPI app: build the services, register middleware and routes."""

import threading
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import request_context
from app.api.pipeline import EvidencePipeline
from app.api.responses import PrettyJSONResponse
from app.api.routes import admin, catalog, evidence, ops, web
from app.api.services import Services
from app.audit.store import AuditLog
from app.clients.fhir_client import FhirClient
from app.config import Settings
from app.domain.audit import AuditContext
from app.domain.enums import AuditAction, Outcome
from app.loaders.policy_file import load_policy
from app.ops.health import HealthProbes
from app.ops.logs import configure_logging
from app.security.auth import token_map
from app.summary.prompt import PROMPT_VERSION
from app.summary.summarizer import Summarizer

SYSTEM_ACTOR = "system"


def build_services(
    settings: Settings, fhir: FhirClient | None, summarizer: Summarizer | None
) -> Services:
    """Load the policy and create every client and store the app needs."""
    policy = load_policy(settings.policy_path)
    fhir_client = fhir or FhirClient(settings)
    summary = summarizer or Summarizer(
        settings.ollama_url,
        settings.summary_model,
        settings.summary_timeout_seconds,
        choices=settings.summary_models[1:],
    )
    audit = AuditLog(settings.audit_db_path)
    return Services(
        settings=settings,
        policy=policy,
        fhir=fhir_client,
        owns_fhir=fhir is None,
        summarizer=summary,
        audit=audit,
        tokens=token_map(settings),
        pipeline=EvidencePipeline(
            policy=policy,
            fhir=fhir_client,
            summarizer=summary,
            request_dirs=settings.request_dirs,
            fhir_link_base=settings.fhir_link_base,
        ),
        probes=HealthProbes(
            fhir=fhir_client,
            summarizer=summary,
            audit=audit,
            policy=policy,
            policy_path=settings.policy_path,
            request_dirs=settings.request_dirs,
            timeout_seconds=settings.health_timeout_seconds,
            mcp_health_url=settings.mcp_health_url,
            started_monotonic=time.monotonic(),
        ),
    )


def record_start(services: Services, actor: str) -> None:
    """Audit a service start with the policy hash, prompt version, and non-secret settings.

    Comparing consecutive start rows shows exactly what changed between deployments.
    """
    policy = services.policy
    services.audit.append(
        actor=actor,
        role=None,
        action=AuditAction.SERVICE_START,
        request_id=uuid.uuid4().hex,
        resource=policy.policy_id,
        outcome=Outcome.OK,
        context=AuditContext(
            policy_version=policy.version,
            policy_sha256=policy.source.sha256,
            config={**services.settings.fingerprint(), "prompt_version": PROMPT_VERSION},
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """On start, audit the start and warm the model in the background; on stop, close clients."""
    services: Services = app.state.services
    record_start(services, SYSTEM_ACTOR)
    threading.Thread(
        target=services.summarizer.warm_up, name="summary-warm-up", daemon=True
    ).start()
    yield
    if services.owns_fhir:
        services.fhir.close()
    services.summarizer.close()


def create_app(
    settings: Settings | None = None,
    fhir: FhirClient | None = None,
    summarizer: Summarizer | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own FHIR client and summarizer."""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="PA Evidence Packet", lifespan=lifespan, default_response_class=PrettyJSONResponse
    )
    app.state.services = build_services(settings, fhir, summarizer)
    app.middleware("http")(request_context)
    for module in (evidence, catalog, admin, ops, web):
        app.include_router(module.router)
    web.mount_static(app)
    return app
