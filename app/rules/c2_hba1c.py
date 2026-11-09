"""C2: a recent HbA1c at or above the policy threshold."""

from datetime import timedelta

from app.domain.enums import CriterionId, Status
from app.domain.packet import AttestationComparison, CriterionResult
from app.domain.policy import Policy
from app.domain.record import Observation, PatientRecord
from app.domain.request_form import RequestForm
from app.rules.matching import dated_results, latest
from app.rules.result import criterion_result

CID = CriterionId.C2
VALUE_TOLERANCE = 0.05


def attested_conflict(
    results: list[Observation], form: RequestForm, policy: Policy
) -> CriterionResult | None:
    """A conflicting result when the form's HbA1c differs from every record value that day."""
    attested = form.attestation
    if attested.hba1c_value is None or attested.hba1c_date is None:
        return None
    same_day = [o for o in results if o.effective == attested.hba1c_date]
    if not same_day or any(
        abs(o.value - attested.hba1c_value) <= VALUE_TOLERANCE for o in same_day
    ):
        return None
    unit = policy.c2.unit
    found = latest(same_day)
    return criterion_result(
        policy,
        CID,
        Status.CONFLICTING,
        f"Request form reports HbA1c {attested.hba1c_value} {unit} on "
        f"{attested.hba1c_date}; record shows {found.value} {unit} on that date",
        [found.ref],
        conflicts=[
            AttestationComparison(
                field="hba1c_value",
                form_value=attested.hba1c_value,
                record_value=found.value,
                record_source=found.ref,
            )
        ],
    )


def c2_hba1c(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    """Conflicting on a same-day mismatch with the form; otherwise judge the latest in-window
    result against the threshold, or report it missing with the latest older result."""
    spec = policy.c2
    window_start = form.request_date - timedelta(days=spec.window_days)
    results = dated_results(record, spec.code)

    conflict = attested_conflict(results, form, policy)
    if conflict is not None:
        return conflict

    in_window = [o for o in results if window_start <= o.effective <= form.request_date]
    if not in_window:
        older = [o for o in results if o.effective < window_start]
        prior = latest(older) if older else None
        detail = (
            f"; latest on record is {prior.value} {spec.unit} on {prior.effective}" if prior else ""
        )
        return criterion_result(
            policy,
            CID,
            Status.MISSING,
            f"No HbA1c result dated {window_start} to {form.request_date}{detail}",
            [prior.ref] if prior else [],
            missing_document=f"HbA1c result dated on or after {window_start}",
        )
    found = latest(in_window)
    status = Status.MET if found.value >= spec.value_min else Status.NOT_MET
    return criterion_result(
        policy,
        CID,
        status,
        f"Latest HbA1c {found.value} {spec.unit} on {found.effective}; "
        f"threshold {spec.value_min} {spec.unit}",
        [found.ref],
    )
