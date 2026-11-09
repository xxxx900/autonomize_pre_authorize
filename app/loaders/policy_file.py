"""Load the policy JSON file into a Policy, keeping a citation for every criterion."""

import hashlib
import json
from pathlib import Path

from app.domain.enums import CriterionId
from app.domain.policy import C1Spec, C2Spec, C3Spec, C4Spec, Policy
from app.domain.provenance import EvidenceFact, PolicyCitation, PolicySource


def file_sha256(path: Path) -> str:
    """Hash a file's bytes, so a reader can confirm which policy text produced a packet."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flatten(value: object, prefix: str = "") -> list[EvidenceFact]:
    """Turn a nested JSON block into `dotted.path = value` facts, in file order."""
    if isinstance(value, dict):
        return [f for k, v in value.items() for f in flatten(v, f"{prefix}.{k}" if prefix else k)]
    if isinstance(value, list) and any(isinstance(v, dict) for v in value):
        return [f for i, v in enumerate(value) for f in flatten(v, f"{prefix}[{i}]")]
    if isinstance(value, list):
        return [EvidenceFact(field=prefix, value=", ".join(str(v) for v in value))]
    return [EvidenceFact(field=prefix, value=str(value))]


def citation(criterion: dict) -> PolicyCitation:
    """Cite one criterion: its requirement text and every parameter of its `fhir` block."""
    cid = criterion["id"]
    return PolicyCitation(
        criterion_id=cid,
        requirement=criterion["requirement"],
        section=f"criteria[id={cid}].fhir",
        parameters=flatten(criterion.get("fhir", {})),
    )


def load_policy(path: str | Path) -> Policy:
    """Read the policy file and build the specs the rules read."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    by_id = {CriterionId(c["id"]): c for c in raw["criteria"]}
    c1, c2, c3, c4 = (by_id[k]["fhir"] for k in list(CriterionId)[:4])
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
        source=PolicySource(
            file=path.name,
            sha256=file_sha256(path),
            title=raw.get("title", ""),
            payer=raw.get("payer", ""),
            effective=raw["effective"],
        ),
        citations={k: citation(v) for k, v in by_id.items()},
    )
