"""Where a finding came from: the policy clause it applies and the record data it read."""

from datetime import date

from app.domain.base import Frozen
from app.domain.enums import CriterionId, ResourceType


class SourceRef(Frozen):
    """A pointer to one FHIR resource, such as Observation/abc."""

    resource_type: ResourceType
    id: str

    def __str__(self) -> str:
        """Render as the FHIR relative reference `Type/id`."""
        return f"{self.resource_type}/{self.id}"


class EvidenceFact(Frozen):
    """One named value, such as `valueQuantity = 6.4 %`, shown so a reader can proofread it."""

    field: str
    value: str


def format_date(value: date | None) -> str:
    """Render an optional date the same way in every fact."""
    return value.isoformat() if value else "(none)"


class EvidenceItem(Frozen):
    """One cited FHIR resource with the exact fields the rules read from it."""

    ref: SourceRef
    label: str
    fhir_url: str | None
    facts: list[EvidenceFact]


class PolicySource(Frozen):
    """The policy file the criteria were loaded from, pinned by its SHA-256."""

    file: str
    sha256: str
    title: str
    payer: str
    effective: date


class PolicyCitation(Frozen):
    """The policy clause one criterion applies, with the parameters the rule used."""

    criterion_id: CriterionId
    requirement: str
    section: str
    parameters: list[EvidenceFact]
