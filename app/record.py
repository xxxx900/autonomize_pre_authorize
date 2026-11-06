from datetime import date

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class SourceRef(Frozen):
    resource_type: str
    id: str

    def __str__(self) -> str:
        return f"{self.resource_type}/{self.id}"


class Coding(Frozen):
    system: str
    code: str
    display: str


class Condition(Frozen):
    ref: SourceRef
    codings: tuple[Coding, ...]
    clinical_status: str
    onset: date | None


class Observation(Frozen):
    ref: SourceRef
    codings: tuple[Coding, ...]
    value: float | None
    unit: str
    effective: date | None


class MedicationRequest(Frozen):
    ref: SourceRef
    codings: tuple[Coding, ...]
    status: str
    authored_on: date | None
    validity_end: date | None


class AllergyIntolerance(Frozen):
    ref: SourceRef
    codings: tuple[Coding, ...]
    clinical_status: str


class DocumentReference(Frozen):
    ref: SourceRef
    type_display: str
    date: date | None


class PatientRecord(Frozen):
    patient_id: str
    birth_date: date | None
    conditions: tuple[Condition, ...]
    observations: tuple[Observation, ...]
    medication_requests: tuple[MedicationRequest, ...]
    allergies: tuple[AllergyIntolerance, ...]
    documents: tuple[DocumentReference, ...]


class Attestation(Frozen):
    metformin_trial_months: float | None = None
    hba1c_value: float | None = None
    hba1c_date: date | None = None
    notes: str = ""


class RequestForm(Frozen):
    request_id: str
    request_date: date
    policy_id: str
    patient_id: str
    requested_medication: str
    diagnosis_claimed: str
    attestation: Attestation

    @classmethod
    def from_json(cls, raw: dict) -> "RequestForm":
        return cls(
            request_id=raw["request_id"],
            request_date=raw["request_date"],
            policy_id=raw["policy_id"],
            patient_id=raw["member"]["patient_id"],
            requested_medication=raw["requested_medication"]["rxnorm"],
            diagnosis_claimed=raw["diagnosis_claimed"]["snomed"],
            attestation=raw.get("prescriber_attestation", {}),
        )


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _codings(concept: dict | None) -> tuple[Coding, ...]:
    return tuple(
        Coding(system=c.get("system", ""), code=c.get("code", ""), display=c.get("display", ""))
        for c in (concept or {}).get("coding", [])
    )


def _status(resource: dict) -> str:
    codings = _codings(resource.get("clinicalStatus"))
    return codings[0].code if codings else ""


def _ref(resource: dict) -> SourceRef:
    return SourceRef(resource_type=resource["resourceType"], id=resource["id"])


def _condition(r: dict) -> Condition:
    return Condition(
        ref=_ref(r),
        codings=_codings(r.get("code")),
        clinical_status=_status(r),
        onset=_date(r.get("onsetDateTime")),
    )


def _observation(r: dict) -> Observation:
    quantity = r.get("valueQuantity") or {}
    return Observation(
        ref=_ref(r),
        codings=_codings(r.get("code")),
        value=quantity.get("value"),
        unit=quantity.get("unit", ""),
        effective=_date(r.get("effectiveDateTime")),
    )


def _medication_request(r: dict) -> MedicationRequest:
    period = (r.get("dispenseRequest") or {}).get("validityPeriod") or {}
    return MedicationRequest(
        ref=_ref(r),
        codings=_codings(r.get("medicationCodeableConcept")),
        status=r.get("status", ""),
        authored_on=_date(r.get("authoredOn")),
        validity_end=_date(period.get("end")),
    )


def _allergy(r: dict) -> AllergyIntolerance:
    return AllergyIntolerance(
        ref=_ref(r), codings=_codings(r.get("code")), clinical_status=_status(r)
    )


def _document(r: dict) -> DocumentReference:
    concept = r.get("type") or {}
    codings = _codings(concept)
    display = codings[0].display if codings else concept.get("text", "")
    return DocumentReference(ref=_ref(r), type_display=display, date=_date(r.get("date")))


_PARSERS = {
    "Condition": _condition,
    "Observation": _observation,
    "MedicationRequest": _medication_request,
    "AllergyIntolerance": _allergy,
    "DocumentReference": _document,
}


def record_from_resources(resources: list[dict]) -> PatientRecord:
    patient = next(r for r in resources if r["resourceType"] == "Patient")
    parsed: dict[str, list] = {name: [] for name in _PARSERS}
    for r in resources:
        parser = _PARSERS.get(r["resourceType"])
        if parser:
            parsed[r["resourceType"]].append(parser(r))
    return PatientRecord(
        patient_id=patient["id"],
        birth_date=_date(patient.get("birthDate")),
        conditions=tuple(parsed["Condition"]),
        observations=tuple(parsed["Observation"]),
        medication_requests=tuple(parsed["MedicationRequest"]),
        allergies=tuple(parsed["AllergyIntolerance"]),
        documents=tuple(parsed["DocumentReference"]),
    )
