from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, computed_field

from app.record import SourceRef


class Status(StrEnum):
    MET = "met"
    NOT_MET = "not_met"
    MISSING = "missing"
    CONFLICTING = "conflicting"


class Route(StrEnum):
    EVIDENCE_COMPLETE = "evidence_complete"
    CLINICIAN_REVIEW = "clinician_review"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class AttestationComparison(Frozen):
    field: str
    form_value: float | str | None
    record_value: float | str | None
    record_source: SourceRef | None


class CriterionResult(Frozen):
    id: str
    requirement: str
    status: Status
    sources: list[SourceRef]
    rationale: str
    missing_document: str | None = None
    conflicts: list[AttestationComparison] = []


class EvidencePacket(Frozen):
    request_id: str
    policy_id: str
    policy_version: str
    request_date: date
    criteria: list[CriterionResult]
    missing_documents: list[str]
    flagged_documents: list[SourceRef]
    summary: str | None = None

    @computed_field
    @property
    def route(self) -> Route:
        if all(c.status is Status.MET for c in self.criteria):
            return Route.EVIDENCE_COMPLETE
        return Route.CLINICIAN_REVIEW
