"""The evidence packet: what the service returns for one request."""

from datetime import date, datetime

from pydantic import computed_field

from app.domain.base import Frozen
from app.domain.enums import CriterionId, Route, Status, SummaryFallback, SummarySource
from app.domain.provenance import EvidenceItem, PolicyCitation, PolicySource, SourceRef


class AttestationComparison(Frozen):
    """A form value set beside the record value it disagrees with."""

    field: str
    form_value: float | str | None
    record_value: float | str | None
    record_source: SourceRef | None


class CriterionResult(Frozen):
    """The status of one criterion, why, and the resources and policy clause behind it."""

    id: CriterionId
    requirement: str
    status: Status
    sources: list[SourceRef]
    rationale: str
    missing_document: str | None = None
    conflicts: list[AttestationComparison] = []
    policy: PolicyCitation
    evidence: list[EvidenceItem] = []


class SummaryTrace(Frozen):
    """How the summary was produced: by whom, with which model, and how long it took."""

    source: SummarySource
    model: str | None = None
    prompt_version: str | None = None
    latency_ms: float | None = None
    fallback: SummaryFallback | None = None


class PacketTrace(Frozen):
    """When and how fast this packet was built, keyed by the id in the X-Request-ID header."""

    trace_id: str
    generated_at: datetime
    duration_ms: float
    fhir_ms: float
    rules_ms: float
    source_check_ms: float
    summary: SummaryTrace
    fhir_resources_read: int


class EvidencePacket(Frozen):
    """Per-criterion findings for one request. It reports evidence and never decides."""

    request_id: str
    policy_id: str
    policy_version: str
    request_date: date
    criteria: list[CriterionResult]
    missing_documents: list[str]
    flagged_documents: list[SourceRef]
    summary: str | None = None
    summary_source: SummarySource | None = None
    summary_prompt_version: str | None = None
    policy_source: PolicySource
    flagged_evidence: list[EvidenceItem] = []
    trace: PacketTrace | None = None

    @computed_field
    @property
    def route(self) -> Route:
        """Evidence complete only when every criterion is met; otherwise clinician review."""
        if all(c.status is Status.MET for c in self.criteria):
            return Route.EVIDENCE_COMPLETE
        return Route.CLINICIAN_REVIEW
