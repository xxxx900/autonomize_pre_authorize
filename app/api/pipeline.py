"""Build one evidence packet end to end, timing each stage for the packet trace and audit row.

Stages: load the request form, read the member's FHIR record, run the rules, confirm every cited
resource exists in FHIR, then summarize.
"""

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.clients.fhir_client import FhirClient, FhirError, PatientNotFound
from app.domain.audit import AuditContext
from app.domain.enums import Outcome, ResourceType
from app.domain.evidence_run import EvidenceRun
from app.domain.packet import PacketTrace
from app.domain.policy import Policy
from app.domain.request_form import RequestForm
from app.loaders.fhir_record import record_from_resources
from app.loaders.request_file import load_request_form
from app.ops.timing import elapsed_ms
from app.rules.evaluate import evaluate
from app.summary.safety import missing_sources
from app.summary.summarizer import Summarizer, apply_summary


def resource_types(resources: list[dict]) -> list[ResourceType]:
    """The known FHIR resource types among the resources read, sorted, for the PHI trace."""
    return sorted(
        {ResourceType(r["resourceType"]) for r in resources if r["resourceType"] in ResourceType}
    )


class PipelineError(Exception):
    """A failed evidence run: the audit outcome, the HTTP status, a PHI-free message, and
    whatever trace context was gathered before the failure."""

    def __init__(
        self,
        outcome: Outcome,
        status_code: int,
        detail: str,
        context: AuditContext | None = None,
    ) -> None:
        """Keep every field the route needs to answer and audit the failure."""
        super().__init__(detail)
        self.outcome = outcome
        self.status_code = status_code
        self.detail = detail
        self.context = context or AuditContext(error=detail)


@dataclass(frozen=True)
class EvidencePipeline:
    """The dependencies one evidence run needs."""

    policy: Policy
    fhir: FhirClient
    summarizer: Summarizer
    request_dirs: tuple[Path, ...]
    fhir_link_base: str

    def load_form(self, request_id: str) -> RequestForm:
        """Load and check the form, mapping each failure to a 404 or 422."""
        try:
            form = load_request_form(request_id, self.request_dirs)
        except (FileNotFoundError, ValidationError, KeyError, json.JSONDecodeError) as exc:
            missing = isinstance(exc, FileNotFoundError)
            raise PipelineError(
                Outcome.NOT_FOUND if missing else Outcome.ERROR,
                404 if missing else 422,
                "unknown or unreadable request",
            ) from exc
        if form.policy_id != self.policy.policy_id:
            raise PipelineError(
                Outcome.ERROR, 422, "request references a policy this service does not hold"
            )
        return form

    def run(self, request_id: str, trace_id: str, summary_model: str | None = None) -> EvidenceRun:
        """Build the packet for one request. Raises PipelineError with a PHI-free detail.

        `summary_model` picks one of the summarizer's allowed models; None uses the default.
        """
        started = time.perf_counter()
        if summary_model is not None and not self.summarizer.offers(summary_model):
            raise PipelineError(
                Outcome.ERROR, 422, "summary model not offered; GET /catalog lists the choices"
            )
        form = self.load_form(request_id)
        subject = f"{ResourceType.PATIENT}/{form.patient_id}"
        failed = AuditContext(subject=subject, policy_version=self.policy.version)
        try:
            stage = time.perf_counter()
            resources = self.fhir.patient_resources(form.patient_id)
            record = record_from_resources(resources)
            fhir_ms = elapsed_ms(stage)

            stage = time.perf_counter()
            packet = evaluate(record, form, self.policy, self.fhir_link_base)
            rules_ms = elapsed_ms(stage)

            stage = time.perf_counter()
            unverified = missing_sources(packet, self.fhir.exists)
            source_check_ms = elapsed_ms(stage)
        except PatientNotFound as exc:
            detail = "member not found in FHIR"
            context = failed.model_copy(update={"error": detail})
            raise PipelineError(Outcome.NOT_FOUND, 404, detail, context) from exc
        except FhirError as exc:
            detail = "FHIR server unavailable"
            context = failed.model_copy(update={"error": detail})
            raise PipelineError(Outcome.ERROR, 502, detail, context) from exc
        if unverified:
            detail = "a cited source could not be verified in FHIR"
            context = failed.model_copy(update={"error": detail})
            raise PipelineError(Outcome.ERROR, 502, detail, context)

        text, summary_trace = self.summarizer.summarize(packet, summary_model)
        duration_ms = elapsed_ms(started)
        trace = PacketTrace(
            trace_id=trace_id,
            generated_at=datetime.now(UTC),
            duration_ms=duration_ms,
            fhir_ms=fhir_ms,
            rules_ms=rules_ms,
            source_check_ms=source_check_ms,
            summary=summary_trace,
            fhir_resources_read=len(resources),
        )
        packet = apply_summary(packet, text, summary_trace).model_copy(update={"trace": trace})
        context = AuditContext(
            duration_ms=duration_ms,
            subject=subject,
            phi_resource_types=resource_types(resources),
            phi_resources_read=len(resources),
            policy_version=self.policy.version,
            policy_sha256=self.policy.source.sha256,
            summary=summary_trace,
        )
        return EvidenceRun(packet=packet, context=context)
