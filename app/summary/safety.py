"""Checks a summary must pass: no decision words, and no fact that is not in the packet.

Also lists the packet's cited sources so the pipeline can confirm each exists in FHIR.
"""

import re
from collections.abc import Callable

from app.domain.enums import Status
from app.domain.fact_tokens import FactTokens
from app.domain.packet import EvidencePacket
from app.domain.provenance import SourceRef

FORBIDDEN_PATTERN = re.compile(
    r"\b(?:approv\w*|den(?:y|ies|ied|ial)|reject\w*|decline\w*|recommend\w*|advis\w*|suggest\w*"
    r"|(?:in)?eligib\w*|qualif\w*|warrant\w*|should|must|ought|appropriate|authoriz\w*)\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
CRITERION_ID_PATTERN = re.compile(r"\bC\d+\b")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
CLAUSE_SPLIT = re.compile(
    r"[,;]|\b(?:while|but|whereas)\b|\band(?=\s+(?:criteri\w+\s+)?C\d+\s+(?:is|are|has|have)\b)",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
STATUS_WORDS: tuple[tuple[re.Pattern[str], Status], ...] = (
    (
        re.compile(r"\b(?:not[\s_]+met|unmet|(?:does|do|did)\s+not\s+meet|fails?|failed)\b", re.I),
        Status.NOT_MET,
    ),
    (re.compile(r"\b(?:met|meets?|meeting|satisf\w+)\b", re.I), Status.MET),
    (re.compile(r"\b(?:missing|absent)\b", re.I), Status.MISSING),
    (re.compile(r"\bconflict\w*", re.I), Status.CONFLICTING),
)


def forbidden_words(text: str) -> list[str]:
    """Decision words (approve, deny, should, ...) found in the text, lowercased and sorted."""
    return sorted({m.group(0).lower() for m in FORBIDDEN_PATTERN.finditer(text)})


def evidence_text(packet: EvidencePacket) -> str:
    """Every fact a summary may state. The model is shown exactly this text and nothing else."""
    lines = [f"Request date: {packet.request_date}"]
    for c in packet.criteria:
        lines.append(
            f"{c.id} has status {c.status.value}. Requirement: {c.requirement}. "
            f"Finding: {c.rationale}"
        )
        if c.missing_document:
            lines.append(f"{c.id} needs from the provider: {c.missing_document}")
        lines.extend(
            f"{c.id} conflict on {x.field}: request form says {x.form_value}, "
            f"record says {x.record_value}"
            for x in c.conflicts
        )
    return "\n".join(lines)


def sentence_count(text: str) -> int:
    """Number of sentences, counting a text with no end mark as one."""
    return len(SENTENCE_END.findall(text.strip())) or 1


def statuses_in(clause: str) -> frozenset[Status]:
    """Every status a clause states. `not met` is consumed first so it never also reads as met."""
    found = set()
    for pattern, status in STATUS_WORDS:
        clause, hits = pattern.subn(" ", clause)
        if hits:
            found.add(status)
    return frozenset(found)


def stated_statuses(text: str) -> list[tuple[str, frozenset[Status]]]:
    """Criterion ids paired with every status word in the clause that names or follows them."""
    claims: dict[str, set[Status]] = {}
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        pending: list[str] = []
        last_claimed: list[str] = []
        for clause in CLAUSE_SPLIT.split(sentence):
            pending += CRITERION_ID_PATTERN.findall(clause)
            statuses = statuses_in(clause)
            if not statuses:
                continue
            targets = pending or last_claimed
            for cid in targets:
                claims.setdefault(cid, set()).update(statuses)
            last_claimed, pending = targets, []
    return [(cid, frozenset(said)) for cid, said in claims.items()]


def fact_tokens(text: str) -> FactTokens:
    """Pull dates out first, then criterion ids, then the remaining numbers."""
    dates = set(DATE_PATTERN.findall(text))
    rest = DATE_PATTERN.sub(" ", text)
    ids = set(CRITERION_ID_PATTERN.findall(rest))
    rest = CRITERION_ID_PATTERN.sub(" ", rest)
    numbers = {float(n) for n in NUMBER_PATTERN.findall(rest)}
    return FactTokens(frozenset(dates), frozenset(ids), frozenset(numbers))


def faithfulness_problems(text: str, packet: EvidencePacket) -> list[str]:
    """Every way the text departs from the packet; an empty list means it is faithful."""
    allowed = fact_tokens(evidence_text(packet))
    said = fact_tokens(text)
    problems = [f"date not in packet: {d}" for d in sorted(said.dates - allowed.dates)]
    problems += [f"criterion not in packet: {i}" for i in sorted(said.ids - allowed.ids)]
    problems += [f"number not in packet: {n:g}" for n in sorted(said.numbers - allowed.numbers)]
    actual = {c.id: c.status for c in packet.criteria}
    problems += [
        f"{cid} stated as {'/'.join(sorted(claimed))} but packet says {actual[cid].value}"
        for cid, claimed in stated_statuses(text)
        if cid in actual and claimed != {actual[cid]}
    ]
    problems += [
        f"{c.id} is {c.status.value} but not mentioned"
        for c in packet.criteria
        if c.status is not Status.MET and c.id not in said.ids
    ]
    return problems


def cited_sources(packet: EvidencePacket) -> set[SourceRef]:
    """Every resource the packet points at: criterion sources, conflicts, and flagged documents."""
    cited = set(packet.flagged_documents)
    for criterion in packet.criteria:
        cited.update(criterion.sources)
        cited.update(c.record_source for c in criterion.conflicts if c.record_source)
    return cited


def missing_sources(packet: EvidencePacket, exists: Callable[[SourceRef], bool]) -> list[SourceRef]:
    """Cited resources the FHIR server does not hold, sorted for a stable error."""
    return sorted((ref for ref in cited_sources(packet) if not exists(ref)), key=str)
