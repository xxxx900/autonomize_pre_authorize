"""Code matching and record lookups shared by more than one criterion."""

from app.domain.policy import OTHER_DIABETES_TYPES, Policy, PolicyCode
from app.domain.record import Coding, Condition, MedicationRequest, Observation, PatientRecord


def has_code(codings: tuple[Coding, ...], code: PolicyCode) -> bool:
    """True when any coding matches the policy code's system and code."""
    return any(c.system == code.system and c.code == code.code for c in codings)


def has_rxnorm(codings: tuple[Coding, ...], rxnorm: str) -> bool:
    """True when any RxNorm coding has this code."""
    return any(c.code == rxnorm for c in codings if "rxnorm" in c.system)


def is_metformin(item: MedicationRequest, policy: Policy) -> bool:
    """True for a metformin prescription, by ingredient code, product code, or display text."""
    spec = policy.c3
    return (
        has_rxnorm(item.codings, spec.ingredient_rxnorm)
        or has_rxnorm(item.codings, spec.product_rxnorm)
        or any("metformin" in c.display.lower() for c in item.codings)
    )


def dated_results(record: PatientRecord, code: PolicyCode) -> list[Observation]:
    """Observations with this code that carry both a value and a date."""
    return [
        o
        for o in record.observations
        if has_code(o.codings, code) and o.value is not None and o.effective is not None
    ]


def latest(observations: list[Observation]) -> Observation:
    """The most recent observation; ties break on resource id so the choice is stable."""
    return max(observations, key=lambda o: (o.effective, o.ref.id))


def other_diabetes(conditions: tuple[Condition, ...]) -> list[Condition]:
    """Conditions coded as a diabetes type other than type 2."""
    return [
        c for c in conditions if any(coding.code in OTHER_DIABETES_TYPES for coding in c.codings)
    ]
