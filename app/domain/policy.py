"""The medical policy the criteria are evaluated against, in the shape the rules read."""

from app.domain.base import Frozen
from app.domain.enums import CriterionId
from app.domain.provenance import PolicyCitation, PolicySource

MIN_ADULT_AGE = 18
OTHER_DIABETES_TYPES = {"46635009": "Type 1 diabetes mellitus"}


class PolicyCode(Frozen):
    """A code the policy names, such as the SNOMED code for type 2 diabetes."""

    system: str
    code: str
    display: str = ""


class C1Spec(Frozen):
    """C1: the diagnosis code and the clinical statuses that count as active."""

    code: PolicyCode
    clinical_status_in: tuple[str, ...]


class C2Spec(Frozen):
    """C2: the HbA1c code, threshold, unit, and look-back window."""

    code: PolicyCode
    value_min: float
    unit: str
    window_days: int


class C3Spec(Frozen):
    """C3: metformin codes and duration, plus the eGFR contraindication threshold."""

    ingredient_rxnorm: str
    product_rxnorm: str
    min_days_in_window: int
    window_days: int
    egfr_code: PolicyCode
    egfr_value_max: float


class C4Spec(Frozen):
    """C4: the exclusion diagnoses."""

    codes: tuple[PolicyCode, ...]


class Policy(Frozen):
    """A loaded policy: identity, per-criterion specs, and where each clause came from."""

    policy_id: str
    version: str
    requirements: dict[CriterionId, str]
    c1: C1Spec
    c2: C2Spec
    c3: C3Spec
    c4: C4Spec
    source: PolicySource
    citations: dict[CriterionId, PolicyCitation]
    min_adult_age: int = MIN_ADULT_AGE
