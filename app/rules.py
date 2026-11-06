from collections.abc import Callable
from datetime import date, timedelta

from app.packet import AttestationComparison, CriterionResult, EvidencePacket, Status
from app.policy import OTHER_DIABETES_TYPES, Policy, PolicyCode
from app.record import (
    Coding,
    Condition,
    MedicationRequest,
    Observation,
    PatientRecord,
    RequestForm,
    SourceRef,
)

DAYS_PER_MONTH = 30.44
ATTESTATION_MONTH_TOLERANCE = 1.0
VALUE_TOLERANCE = 0.05


def _has(codings: tuple[Coding, ...], code: PolicyCode) -> bool:
    return any(c.system == code.system and c.code == code.code for c in codings)


def _has_rxnorm(codings: tuple[Coding, ...], rxnorm: str) -> bool:
    return any(c.code == rxnorm for c in codings if "rxnorm" in c.system)


def _is_metformin(item: MedicationRequest, policy: Policy) -> bool:
    spec = policy.c3
    return (
        _has_rxnorm(item.codings, spec.ingredient_rxnorm)
        or _has_rxnorm(item.codings, spec.product_rxnorm)
        or any("metformin" in c.display.lower() for c in item.codings)
    )


def _result(
    policy: Policy,
    cid: str,
    status: Status,
    rationale: str,
    sources: list[SourceRef] | None = None,
    missing_document: str | None = None,
    conflicts: list[AttestationComparison] | None = None,
) -> CriterionResult:
    return CriterionResult(
        id=cid,
        requirement=policy.requirements[cid],
        status=status,
        sources=sources or [],
        rationale=rationale,
        missing_document=missing_document,
        conflicts=conflicts or [],
    )


def _latest(observations: list[Observation]) -> Observation:
    return max(observations, key=lambda o: (o.effective, o.ref.id))


def c1_diagnosis(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    spec = policy.c1
    t2dm = [c for c in record.conditions if _has(c.codings, spec.code)]
    active = [c for c in t2dm if c.clinical_status in spec.clinical_status_in]
    if active:
        return _result(
            policy,
            "C1",
            Status.MET,
            f"Type 2 diabetes mellitus recorded with clinical status {active[0].clinical_status}",
            [c.ref for c in active],
        )
    if t2dm:
        statuses = ", ".join(sorted({c.clinical_status or "unknown" for c in t2dm}))
        return _result(
            policy,
            "C1",
            Status.NOT_MET,
            f"Type 2 diabetes mellitus recorded only with clinical status {statuses}",
            [c.ref for c in t2dm],
        )
    other = _other_diabetes(record.conditions)
    if form.diagnosis_claimed == spec.code.code and other:
        return _result(
            policy,
            "C1",
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
    return _result(
        policy,
        "C1",
        Status.MISSING,
        "No type 2 diabetes mellitus Condition in the record",
        missing_document="Documentation of type 2 diabetes mellitus diagnosis",
    )


def _other_diabetes(conditions: tuple[Condition, ...]) -> list[Condition]:
    return [
        c for c in conditions if any(coding.code in OTHER_DIABETES_TYPES for coding in c.codings)
    ]


def _hba1c_results(record: PatientRecord, policy: Policy) -> list[Observation]:
    return [
        o
        for o in record.observations
        if _has(o.codings, policy.c2.code) and o.value is not None and o.effective is not None
    ]


def c2_hba1c(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    spec = policy.c2
    window_start = form.request_date - timedelta(days=spec.window_days)
    results = _hba1c_results(record, policy)
    attested = form.attestation

    if attested.hba1c_value is not None and attested.hba1c_date is not None:
        same_day = [o for o in results if o.effective == attested.hba1c_date]
        if same_day and all(
            abs(o.value - attested.hba1c_value) > VALUE_TOLERANCE for o in same_day
        ):
            found = _latest(same_day)
            return _result(
                policy,
                "C2",
                Status.CONFLICTING,
                f"Request form reports HbA1c {attested.hba1c_value} {spec.unit} on "
                f"{attested.hba1c_date}; record shows {found.value} {spec.unit} on that date",
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

    in_window = [o for o in results if window_start <= o.effective <= form.request_date]
    if not in_window:
        older = [o for o in results if o.effective < window_start]
        prior = _latest(older) if older else None
        detail = (
            f"; latest on record is {prior.value} {spec.unit} on {prior.effective}" if prior else ""
        )
        return _result(
            policy,
            "C2",
            Status.MISSING,
            f"No HbA1c result dated {window_start} to {form.request_date}{detail}",
            [prior.ref] if prior else [],
            missing_document=f"HbA1c result dated on or after {window_start}",
        )
    latest = _latest(in_window)
    status = Status.MET if latest.value >= spec.value_min else Status.NOT_MET
    return _result(
        policy,
        "C2",
        status,
        f"Latest HbA1c {latest.value} {spec.unit} on {latest.effective}; "
        f"threshold {spec.value_min} {spec.unit}",
        [latest.ref],
    )


def _end_of_therapy(item: MedicationRequest, request_date: date) -> date | None:
    if item.validity_end is not None:
        return item.validity_end
    if item.status == "active":
        return request_date
    return None


def _interval(item: MedicationRequest, request_date: date) -> tuple[date, date] | None:
    end = _end_of_therapy(item, request_date)
    if item.authored_on is None or end is None or end <= item.authored_on:
        return None
    return item.authored_on, min(end, request_date)


def _covered_days(intervals: list[tuple[date, date]], since: date | None = None) -> int:
    clipped = sorted(
        (max(start, since) if since else start, end)
        for start, end in intervals
        if since is None or end > since
    )
    total = 0
    cursor: date | None = None
    for start, end in clipped:
        start = max(start, cursor) if cursor else start
        if end > start:
            total += (end - start).days
            cursor = end
    return total


def c3_metformin(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    spec = policy.c3
    meds = [m for m in record.medication_requests if _is_metformin(m, policy)]
    intervals = {m.ref.id: _interval(m, form.request_date) for m in meds}
    spans = [i for i in intervals.values() if i is not None]
    window_start = form.request_date - timedelta(days=spec.window_days)
    therapy_days = _covered_days(spans, since=window_start)
    full_days = _covered_days(spans)

    attested_months = form.attestation.metformin_trial_months
    if meds and attested_months is not None:
        record_months = full_days / DAYS_PER_MONTH
        if attested_months > record_months + ATTESTATION_MONTH_TOLERANCE:
            return _result(
                policy,
                "C3",
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

    reasons: list[str] = []
    sources: list[SourceRef] = []
    if therapy_days >= spec.min_days_in_window:
        reasons.append(
            f"{therapy_days} days of metformin therapy in the {spec.window_days} days "
            f"before {form.request_date}"
        )
        sources += [
            m.ref for m in meds if (i := intervals[m.ref.id]) is not None and i[1] > window_start
        ]
    intolerant = [a for a in record.allergies if _has_rxnorm(a.codings, spec.ingredient_rxnorm)]
    if intolerant:
        reasons.append("metformin intolerance documented")
        sources += [a.ref for a in intolerant]
    egfr = [
        o
        for o in record.observations
        if _has(o.codings, spec.egfr_code) and o.value is not None and o.effective is not None
    ]
    if egfr and _latest(egfr).value < spec.egfr_value_max:
        latest = _latest(egfr)
        reasons.append(f"latest eGFR {latest.value} on {latest.effective}")
        sources.append(latest.ref)
    if reasons:
        return _result(policy, "C3", Status.MET, "; ".join(reasons).capitalize(), sources)

    if meds:
        return _result(
            policy,
            "C3",
            Status.NOT_MET,
            f"{therapy_days} days of metformin therapy in the {spec.window_days} days "
            f"before {form.request_date}; {spec.min_days_in_window} required",
            [m.ref for m in meds],
        )
    return _result(
        policy,
        "C3",
        Status.MISSING,
        "No metformin prescription, intolerance, or eGFR evidence in the record",
        missing_document=(
            f"Metformin prescription history for the {spec.window_days} days before "
            f"{form.request_date}, or documentation of intolerance or contraindication"
        ),
    )


def c4_exclusions(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    hits = [
        (c, coding)
        for c in record.conditions
        for coding in c.codings
        if any(coding.system == p.system and coding.code == p.code for p in policy.c4.codes)
    ]
    if not hits:
        return _result(
            policy,
            "C4",
            Status.MET,
            "No pancreatitis, medullary thyroid carcinoma, or MEN2 Condition in the record",
        )
    listed = "; ".join(
        f"{coding.display or coding.code} (status {c.clinical_status or 'unknown'})"
        for c, coding in hits
    )
    return _result(
        policy, "C4", Status.NOT_MET, f"History found: {listed}", [c.ref for c, _ in hits]
    )


def c5_age(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    born = record.birth_date
    if born is None:
        return _result(
            policy,
            "C5",
            Status.MISSING,
            "No birth date in the record",
            missing_document="Member date of birth",
        )
    on = form.request_date
    age = on.year - born.year - ((on.month, on.day) < (born.month, born.day))
    status = Status.MET if age >= policy.min_adult_age else Status.NOT_MET
    return _result(
        policy,
        "C5",
        status,
        f"Age {age} on {on}; minimum {policy.min_adult_age}",
        [SourceRef(resource_type="Patient", id=record.patient_id)],
    )


CRITERIA: dict[str, Callable[[PatientRecord, RequestForm, Policy], CriterionResult]] = {
    "C1": c1_diagnosis,
    "C2": c2_hba1c,
    "C3": c3_metformin,
    "C4": c4_exclusions,
    "C5": c5_age,
}


def evaluate(record: PatientRecord, form: RequestForm, policy: Policy) -> EvidencePacket:
    results = [rule(record, form, policy) for rule in CRITERIA.values()]
    return EvidencePacket(
        request_id=form.request_id,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        request_date=form.request_date,
        criteria=results,
        missing_documents=[r.missing_document for r in results if r.missing_document],
        flagged_documents=[d.ref for d in record.documents],
    )
