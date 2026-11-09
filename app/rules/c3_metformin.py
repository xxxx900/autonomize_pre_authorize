"""C3: a metformin trial, or documented intolerance or contraindication to metformin."""

from datetime import timedelta

from app.domain.enums import CriterionId, Status
from app.domain.packet import AttestationComparison, CriterionResult
from app.domain.policy import Policy
from app.domain.provenance import SourceRef
from app.domain.record import MedicationRequest, PatientRecord
from app.domain.request_form import RequestForm
from app.rules.matching import dated_results, has_rxnorm, is_metformin, latest
from app.rules.result import criterion_result
from app.rules.therapy import covered_days, end_of_therapy, therapy_span

CID = CriterionId.C3
DAYS_PER_MONTH = 30.44
ATTESTATION_MONTH_TOLERANCE = 1.0


def attested_conflict(
    meds: list[MedicationRequest], full_days: int, form: RequestForm, policy: Policy
) -> CriterionResult | None:
    """A conflicting result when the form attests more months than the record supports.

    Skipped when any prescription has no end date, since the record total is then unknown.
    """
    attested_months = form.attestation.metformin_trial_months
    undated = [m for m in meds if end_of_therapy(m, form.request_date) is None]
    if not meds or undated or attested_months is None:
        return None
    record_months = full_days / DAYS_PER_MONTH
    if attested_months <= record_months + ATTESTATION_MONTH_TOLERANCE:
        return None
    return criterion_result(
        policy,
        CID,
        Status.CONFLICTING,
        f"Request form attests {attested_months:g} months of metformin; record supports "
        f"{record_months:.1f} months ({full_days} days)",
        [m.ref for m in meds],
        conflicts=[
            AttestationComparison(
                field="metformin_trial_months",
                form_value=attested_months,
                record_value=round(record_months, 1),
                record_source=meds[0].ref if len(meds) == 1 else None,
            )
        ],
    )


def c3_metformin(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    """Met by any of three paths: enough therapy days in the window, a metformin intolerance,
    or a latest eGFR under the contraindication threshold. Conflicting when the form overstates
    the trial; not met when prescriptions fall short; missing when there is no evidence."""
    spec = policy.c3
    meds = [m for m in record.medication_requests if is_metformin(m, policy)]
    spans = {m.ref.id: therapy_span(m, form.request_date) for m in meds}
    known = [s for s in spans.values() if s is not None]
    window_start = form.request_date - timedelta(days=spec.window_days)
    therapy_days = covered_days(known, since=window_start)

    conflict = attested_conflict(meds, covered_days(known), form, policy)
    if conflict is not None:
        return conflict

    reasons: list[str] = []
    sources: list[SourceRef] = []
    if therapy_days >= spec.min_days_in_window:
        reasons.append(
            f"{therapy_days} days of metformin therapy in the {spec.window_days} days "
            f"before {form.request_date}"
        )
        sources += [
            m.ref for m in meds if (s := spans[m.ref.id]) is not None and s.end > window_start
        ]
    intolerant = [a for a in record.allergies if has_rxnorm(a.codings, spec.ingredient_rxnorm)]
    if intolerant:
        reasons.append("metformin intolerance documented")
        sources += [a.ref for a in intolerant]
    egfr = dated_results(record, spec.egfr_code)
    if egfr and latest(egfr).value < spec.egfr_value_max:
        found = latest(egfr)
        reasons.append(f"latest eGFR {found.value} on {found.effective}")
        sources.append(found.ref)
    if reasons:
        joined = "; ".join(reasons)
        return criterion_result(policy, CID, Status.MET, joined[0].upper() + joined[1:], sources)

    if meds:
        undated = [m for m in meds if end_of_therapy(m, form.request_date) is None]
        return criterion_result(
            policy,
            CID,
            Status.NOT_MET,
            f"{therapy_days} days of metformin therapy in the {spec.window_days} days "
            f"before {form.request_date}; {spec.min_days_in_window} required"
            + (f"; not counted for lack of an end date: {len(undated)}" if undated else ""),
            [m.ref for m in meds],
        )
    return criterion_result(
        policy,
        CID,
        Status.MISSING,
        "No metformin prescription, intolerance, or eGFR evidence in the record",
        missing_document=(
            f"Metformin prescription history for the {spec.window_days} days before "
            f"{form.request_date}, or documentation of intolerance or contraindication"
        ),
    )
