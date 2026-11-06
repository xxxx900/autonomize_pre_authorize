import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

MIN_ADULT_AGE = 18
OTHER_DIABETES_TYPES = {"46635009": "Type 1 diabetes mellitus"}


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class PolicyCode(Frozen):
    system: str
    code: str
    display: str = ""


class C1Spec(Frozen):
    code: PolicyCode
    clinical_status_in: tuple[str, ...]


class C2Spec(Frozen):
    code: PolicyCode
    value_min: float
    unit: str
    window_days: int


class C3Spec(Frozen):
    ingredient_rxnorm: str
    product_rxnorm: str
    min_days_in_window: int
    window_days: int
    egfr_code: PolicyCode
    egfr_value_max: float


class C4Spec(Frozen):
    codes: tuple[PolicyCode, ...]


class Policy(Frozen):
    policy_id: str
    version: str
    requirements: dict[str, str]
    c1: C1Spec
    c2: C2Spec
    c3: C3Spec
    c4: C4Spec
    min_adult_age: int = MIN_ADULT_AGE


def load_policy(path: str | Path) -> Policy:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in raw["criteria"]}
    c1, c2, c3, c4 = (by_id[k]["fhir"] for k in ("C1", "C2", "C3", "C4"))
    return Policy(
        policy_id=raw["policy_id"],
        version=raw["version"],
        requirements={k: v["requirement"] for k, v in by_id.items()},
        c1=C1Spec(code=c1["code"], clinical_status_in=c1["clinicalStatus_in"]),
        c2=C2Spec(
            code=c2["code"],
            value_min=c2["value_min"],
            unit=c2["unit"],
            window_days=c2["window_days"],
        ),
        c3=C3Spec(
            ingredient_rxnorm=c3["path_a"]["ingredient_rxnorm"],
            product_rxnorm=c3["path_a"]["product_rxnorm_example"],
            min_days_in_window=c3["path_a"]["min_days_in_window"],
            window_days=c3["path_a"]["window_days"],
            egfr_code=c3["path_c"]["code"],
            egfr_value_max=c3["path_c"]["value_max"],
        ),
        c4=C4Spec(codes=c4["codes"]),
    )
