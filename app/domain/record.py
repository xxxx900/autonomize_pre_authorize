"""The member's FHIR record, reduced to the structured fields the rules read.

Free-text fields (notes, document attachments) have no field here, so no code path can read them.
"""

from datetime import date

from app.domain.base import Frozen
from app.domain.enums import ResourceType
from app.domain.provenance import EvidenceFact, SourceRef, format_date


class Coding(Frozen):
    """One code from a FHIR CodeableConcept."""

    system: str
    code: str
    display: str

    def __str__(self) -> str:
        """Render as `display (code, system)` for a reader comparing against the source."""
        return f"{self.display or '(no display)'} ({self.code}, {self.system})"


def coding_facts(field: str, codings: tuple[Coding, ...]) -> list[EvidenceFact]:
    """List each coding of one FHIR element as a fact named after that element."""
    return [EvidenceFact(field=field, value=str(c)) for c in codings]


def first_display(codings: tuple[Coding, ...], fallback: str) -> str:
    """Return the first coding's display text, or the fallback when there is none."""
    return next((c.display for c in codings if c.display), fallback)


class Condition(Frozen):
    """A FHIR Condition: a diagnosis with its clinical status and onset."""

    ref: SourceRef
    codings: tuple[Coding, ...]
    clinical_status: str
    onset: date | None

    def facts(self) -> list[EvidenceFact]:
        """The fields the rules read, named by their FHIR element paths."""
        return [
            *coding_facts("code", self.codings),
            EvidenceFact(field="clinicalStatus", value=self.clinical_status or "(none)"),
            EvidenceFact(field="onsetDateTime", value=format_date(self.onset)),
        ]


class Observation(Frozen):
    """A FHIR Observation with a numeric value, such as an HbA1c or eGFR result."""

    ref: SourceRef
    codings: tuple[Coding, ...]
    value: float | None
    unit: str
    effective: date | None

    def facts(self) -> list[EvidenceFact]:
        """The fields the rules read, named by their FHIR element paths."""
        quantity = "(none)" if self.value is None else f"{self.value:g} {self.unit}".strip()
        return [
            *coding_facts("code", self.codings),
            EvidenceFact(field="valueQuantity", value=quantity),
            EvidenceFact(field="effectiveDateTime", value=format_date(self.effective)),
        ]


class MedicationRequest(Frozen):
    """A FHIR MedicationRequest: a prescription with its status and validity period."""

    ref: SourceRef
    codings: tuple[Coding, ...]
    status: str
    authored_on: date | None
    validity_end: date | None

    def facts(self) -> list[EvidenceFact]:
        """The fields the rules read, named by their FHIR element paths."""
        return [
            *coding_facts("medicationCodeableConcept", self.codings),
            EvidenceFact(field="status", value=self.status or "(none)"),
            EvidenceFact(field="authoredOn", value=format_date(self.authored_on)),
            EvidenceFact(
                field="dispenseRequest.validityPeriod.end", value=format_date(self.validity_end)
            ),
        ]


class AllergyIntolerance(Frozen):
    """A FHIR AllergyIntolerance, used as evidence of metformin intolerance."""

    ref: SourceRef
    codings: tuple[Coding, ...]
    clinical_status: str

    def facts(self) -> list[EvidenceFact]:
        """The fields the rules read, named by their FHIR element paths."""
        return [
            *coding_facts("code", self.codings),
            EvidenceFact(field="clinicalStatus", value=self.clinical_status or "(none)"),
        ]


class DocumentReference(Frozen):
    """A FHIR DocumentReference. Only its type and date are kept; content is never read."""

    ref: SourceRef
    type_display: str
    date: date | None

    def facts(self) -> list[EvidenceFact]:
        """The fields the service keeps. The attachment is never decoded."""
        return [
            EvidenceFact(field="type", value=self.type_display or "(none)"),
            EvidenceFact(field="date", value=format_date(self.date)),
        ]


RecordEntry = Condition | Observation | MedicationRequest | AllergyIntolerance | DocumentReference


class PatientRecord(Frozen):
    """Everything the rules may read about one member."""

    patient_id: str
    birth_date: date | None
    conditions: tuple[Condition, ...]
    observations: tuple[Observation, ...]
    medication_requests: tuple[MedicationRequest, ...]
    allergies: tuple[AllergyIntolerance, ...]
    documents: tuple[DocumentReference, ...]

    @property
    def patient_ref(self) -> SourceRef:
        """The reference to the member's Patient resource."""
        return SourceRef(resource_type=ResourceType.PATIENT, id=self.patient_id)

    def entries(self) -> tuple[RecordEntry, ...]:
        """Every parsed resource other than the Patient, in one tuple."""
        return (
            *self.conditions,
            *self.observations,
            *self.medication_requests,
            *self.allergies,
            *self.documents,
        )

    def label_and_facts(self, ref: SourceRef) -> tuple[str, list[EvidenceFact]]:
        """Describe one cited resource: a short label and the fields the rules read from it."""
        if ref == self.patient_ref:
            return "Patient", [EvidenceFact(field="birthDate", value=format_date(self.birth_date))]
        entry = next((e for e in self.entries() if e.ref == ref), None)
        if entry is None:
            return str(ref), []
        if isinstance(entry, DocumentReference):
            return entry.type_display or str(ref.resource_type), entry.facts()
        return first_display(entry.codings, str(ref.resource_type)), entry.facts()
