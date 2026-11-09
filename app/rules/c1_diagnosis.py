"""C1: an active type 2 diabetes diagnosis in the record."""

from app.domain.enums import CriterionId, Status
from app.domain.packet import AttestationComparison, CriterionResult
from app.domain.policy import OTHER_DIABETES_TYPES, Policy
from app.domain.record import PatientRecord
from app.domain.request_form import RequestForm
from app.rules.matching import has_code, other_diabetes
from app.rules.result import criterion_result

CID = CriterionId.C1


def c1_diagnosis(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    """Met for an active T2DM Condition; conflicting when the form claims T2DM but the record
    codes another diabetes type; not met for an inactive one; missing otherwise."""
    spec = policy.c1
    t2dm = [c for c in record.conditions if has_code(c.codings, spec.code)]
    active = [c for c in t2dm if c.clinical_status in spec.clinical_status_in]
    if active:
        return criterion_result(
            policy,
            CID,
            Status.MET,
            f"Type 2 diabetes mellitus recorded with clinical status {active[0].clinical_status}",
            [c.ref for c in active],
        )
    if t2dm:
        statuses = ", ".join(sorted({c.clinical_status or "unknown" for c in t2dm}))
        return criterion_result(
            policy,
            CID,
            Status.NOT_MET,
            f"Type 2 diabetes mellitus recorded only with clinical status {statuses}",
            [c.ref for c in t2dm],
        )
    other = other_diabetes(record.conditions)
    if form.diagnosis_claimed == spec.code.code and other:
        return criterion_result(
            policy,
            CID,
            Status.CONFLICTING,
            f"Request form claims type 2 diabetes mellitus; record codes "
            f"{OTHER_DIABETES_TYPES[other[0].codings[0].code]}",
            [c.ref for c in other],
            conflicts=[
                AttestationComparison(
                    field="diagnosis_claimed",
                    form_value=form.diagnosis_claimed,
                    record_value=other[0].codings[0].code,
                    record_source=other[0].ref,
                )
            ],
        )
    return criterion_result(
        policy,
        CID,
        Status.MISSING,
        "No type 2 diabetes mellitus Condition in the record",
        missing_document="Documentation of type 2 diabetes mellitus diagnosis",
    )
