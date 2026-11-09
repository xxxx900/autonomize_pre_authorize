"""The one constructor every criterion uses to report its finding."""

from app.domain.enums import CriterionId, Status
from app.domain.packet import AttestationComparison, CriterionResult
from app.domain.policy import Policy
from app.domain.provenance import SourceRef


def criterion_result(
    policy: Policy,
    cid: CriterionId,
    status: Status,
    rationale: str,
    sources: list[SourceRef] | None = None,
    missing_document: str | None = None,
    conflicts: list[AttestationComparison] | None = None,
) -> CriterionResult:
    """Build a result with the requirement text and citation taken from the policy."""
    return CriterionResult(
        id=cid,
        requirement=policy.requirements[cid],
        status=status,
        sources=sources or [],
        rationale=rationale,
        missing_document=missing_document,
        conflicts=conflicts or [],
        policy=policy.citations[cid],
    )
