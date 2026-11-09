"""Run every criterion and assemble the evidence packet with its provenance."""

from collections.abc import Callable

from app.domain.enums import CriterionId
from app.domain.packet import CriterionResult, EvidencePacket
from app.domain.policy import Policy
from app.domain.provenance import EvidenceItem, SourceRef
from app.domain.record import PatientRecord
from app.domain.request_form import RequestForm
from app.rules.c1_diagnosis import c1_diagnosis
from app.rules.c2_hba1c import c2_hba1c
from app.rules.c3_metformin import c3_metformin
from app.rules.c4_exclusions import c4_exclusions
from app.rules.c5_age import c5_age

Rule = Callable[[PatientRecord, RequestForm, Policy], CriterionResult]

CRITERIA: dict[CriterionId, Rule] = {
    CriterionId.C1: c1_diagnosis,
    CriterionId.C2: c2_hba1c,
    CriterionId.C3: c3_metformin,
    CriterionId.C4: c4_exclusions,
    CriterionId.C5: c5_age,
}


def evidence_item(
    record: PatientRecord, ref: SourceRef, fhir_link_base: str | None
) -> EvidenceItem:
    """Describe one cited resource with the fields the rules read and a link to the source."""
    label, facts = record.label_and_facts(ref)
    url = f"{fhir_link_base}/{ref}" if fhir_link_base else None
    return EvidenceItem(ref=ref, label=label, fhir_url=url, facts=facts)


def cited_refs(result: CriterionResult) -> list[SourceRef]:
    """Every resource a result cites, sources first, without repeats."""
    refs = [*result.sources, *(c.record_source for c in result.conflicts if c.record_source)]
    return list(dict.fromkeys(refs))


def with_evidence(
    result: CriterionResult, record: PatientRecord, fhir_link_base: str | None
) -> CriterionResult:
    """Attach the record facts behind each cited resource to a criterion result."""
    items = [evidence_item(record, ref, fhir_link_base) for ref in cited_refs(result)]
    return result.model_copy(update={"evidence": items})


def evaluate(
    record: PatientRecord,
    form: RequestForm,
    policy: Policy,
    fhir_link_base: str | None = None,
) -> EvidencePacket:
    """Evaluate every criterion and return the packet, without a summary."""
    results = [
        with_evidence(rule(record, form, policy), record, fhir_link_base)
        for rule in CRITERIA.values()
    ]
    return EvidencePacket(
        request_id=form.request_id,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        request_date=form.request_date,
        criteria=results,
        missing_documents=[r.missing_document for r in results if r.missing_document],
        flagged_documents=[d.ref for d in record.documents],
        policy_source=policy.source,
        flagged_evidence=[evidence_item(record, d.ref, fhir_link_base) for d in record.documents],
    )
