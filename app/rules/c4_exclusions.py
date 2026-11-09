"""C4: no history of an excluded diagnosis, at any time and in any status."""

from app.domain.enums import CriterionId, Status
from app.domain.packet import CriterionResult
from app.domain.policy import Policy
from app.domain.record import PatientRecord
from app.domain.request_form import RequestForm
from app.rules.matching import has_code
from app.rules.result import criterion_result

CID = CriterionId.C4


def c4_exclusions(record: PatientRecord, form: RequestForm, policy: Policy) -> CriterionResult:
    """Not met when any Condition carries an excluded code, even if resolved; met otherwise."""
    hits = [
        (c, coding)
        for c in record.conditions
        for coding in c.codings
        if any(has_code((coding,), p) for p in policy.c4.codes)
    ]
    if not hits:
        return criterion_result(
            policy,
            CID,
            Status.MET,
            "No pancreatitis, medullary thyroid carcinoma, or MEN2 Condition in the record",
        )
    listed = "; ".join(
        f"{coding.display or coding.code} (status {c.clinical_status or 'unknown'})"
        for c, coding in hits
    )
    return criterion_result(
        policy, CID, Status.NOT_MET, f"History found: {listed}", [c.ref for c, _ in hits]
    )
