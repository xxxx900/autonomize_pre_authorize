"""Parse raw FHIR R4 JSON resources into a PatientRecord.

Each parser copies only structured fields. Notes, narrative text, and attachments are dropped here.
"""

from collections.abc import Callable
from datetime import date

from app.domain.enums import ResourceType
from app.domain.provenance import SourceRef
from app.domain.record import (
    AllergyIntolerance,
    Coding,
    Condition,
    DocumentReference,
    MedicationRequest,
    Observation,
    PatientRecord,
    RecordEntry,
)


def parse_date(value: str | None) -> date | None:
    """Read the date part of a FHIR date or dateTime string."""
    return date.fromisoformat(value[:10]) if value else None


def parse_codings(concept: dict | None) -> tuple[Coding, ...]:
    """Read every coding of a CodeableConcept."""
    return tuple(
        Coding(system=c.get("system", ""), code=c.get("code", ""), display=c.get("display", ""))
        for c in (concept or {}).get("coding", [])
    )


def parse_clinical_status(resource: dict) -> str:
    """Read the first clinicalStatus code, or an empty string when there is none."""
    codings = parse_codings(resource.get("clinicalStatus"))
    return codings[0].code if codings else ""


def parse_ref(resource: dict) -> SourceRef:
    """Build the reference that points back at this resource."""
    return SourceRef(resource_type=resource["resourceType"], id=resource["id"])


def parse_condition(r: dict) -> Condition:
    """Parse a Condition: code, clinical status, and onset."""
    return Condition(
        ref=parse_ref(r),
        codings=parse_codings(r.get("code")),
        clinical_status=parse_clinical_status(r),
        onset=parse_date(r.get("onsetDateTime")),
    )


def parse_observation(r: dict) -> Observation:
    """Parse an Observation: code, numeric value and unit, and effective date."""
    quantity = r.get("valueQuantity") or {}
    return Observation(
        ref=parse_ref(r),
        codings=parse_codings(r.get("code")),
        value=quantity.get("value"),
        unit=quantity.get("unit", ""),
        effective=parse_date(r.get("effectiveDateTime")),
    )


def parse_medication_request(r: dict) -> MedicationRequest:
    """Parse a MedicationRequest: drug, status, authored date, and validity end."""
    period = (r.get("dispenseRequest") or {}).get("validityPeriod") or {}
    return MedicationRequest(
        ref=parse_ref(r),
        codings=parse_codings(r.get("medicationCodeableConcept")),
        status=r.get("status", ""),
        authored_on=parse_date(r.get("authoredOn")),
        validity_end=parse_date(period.get("end")),
    )


def parse_allergy(r: dict) -> AllergyIntolerance:
    """Parse an AllergyIntolerance: substance code and clinical status."""
    return AllergyIntolerance(
        ref=parse_ref(r),
        codings=parse_codings(r.get("code")),
        clinical_status=parse_clinical_status(r),
    )


def parse_document(r: dict) -> DocumentReference:
    """Parse a DocumentReference: type and date only. The attachment is never read."""
    concept = r.get("type") or {}
    codings = parse_codings(concept)
    display = codings[0].display if codings else concept.get("text", "")
    return DocumentReference(ref=parse_ref(r), type_display=display, date=parse_date(r.get("date")))


PARSERS: dict[ResourceType, Callable[[dict], RecordEntry]] = {
    ResourceType.CONDITION: parse_condition,
    ResourceType.OBSERVATION: parse_observation,
    ResourceType.MEDICATION_REQUEST: parse_medication_request,
    ResourceType.ALLERGY_INTOLERANCE: parse_allergy,
    ResourceType.DOCUMENT_REFERENCE: parse_document,
}


def record_from_resources(resources: list[dict]) -> PatientRecord:
    """Build a PatientRecord from a Patient and its patient-scoped resources.

    Resource types without a parser are skipped.
    """
    patient = next(r for r in resources if r["resourceType"] == ResourceType.PATIENT)
    parsed: dict[ResourceType, list] = {kind: [] for kind in PARSERS}
    for r in resources:
        kind = r["resourceType"]
        if kind in PARSERS:
            parsed[ResourceType(kind)].append(PARSERS[ResourceType(kind)](r))
    return PatientRecord(
        patient_id=patient["id"],
        birth_date=parse_date(patient.get("birthDate")),
        conditions=tuple(parsed[ResourceType.CONDITION]),
        observations=tuple(parsed[ResourceType.OBSERVATION]),
        medication_requests=tuple(parsed[ResourceType.MEDICATION_REQUEST]),
        allergies=tuple(parsed[ResourceType.ALLERGY_INTOLERANCE]),
        documents=tuple(parsed[ResourceType.DOCUMENT_REFERENCE]),
    )
