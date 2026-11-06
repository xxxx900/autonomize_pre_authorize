import re
from collections.abc import Callable

from app.packet import EvidencePacket, Status
from app.record import SourceRef

FORBIDDEN_PATTERN = re.compile(
    r"\b(?:approv\w*|den(?:y|ies|ied|ial)|reject\w*|decline\w*|recommend\w*|advis\w*|suggest\w*"
    r"|(?:in)?eligib\w*|qualif\w*|warrant\w*|should|must|ought|appropriate|authoriz\w*)\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
CRITERION_ID_PATTERN = re.compile(r"\bC\d+\b")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def forbidden_words(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in FORBIDDEN_PATTERN.finditer(text)})


def evidence_text(packet: EvidencePacket) -> str:
    """Every fact a summary may state. The model is shown exactly this text and nothing else."""
    lines = [f"Request date: {packet.request_date}"]
    for c in packet.criteria:
        lines.append(f"{c.id} [{c.status.value}] {c.requirement}. Finding: {c.rationale}")
        if c.missing_document:
            lines.append(f"{c.id} needs from the provider: {c.missing_document}")
        lines.extend(
            f"{c.id} conflict on {x.field}: request form says {x.form_value}, "
            f"record says {x.record_value}"
            for x in c.conflicts
        )
    return "\n".join(lines)


def _tokens(text: str) -> tuple[set[str], set[str], set[float]]:
    dates = set(DATE_PATTERN.findall(text))
    rest = DATE_PATTERN.sub(" ", text)
    ids = set(CRITERION_ID_PATTERN.findall(rest))
    rest = CRITERION_ID_PATTERN.sub(" ", rest)
    return dates, ids, {float(n) for n in NUMBER_PATTERN.findall(rest)}


def faithfulness_problems(text: str, packet: EvidencePacket) -> list[str]:
    allowed_dates, allowed_ids, allowed_numbers = _tokens(evidence_text(packet))
    dates, ids, numbers = _tokens(text)
    problems = [f"date not in packet: {d}" for d in sorted(dates - allowed_dates)]
    problems += [f"criterion not in packet: {i}" for i in sorted(ids - allowed_ids)]
    problems += [f"number not in packet: {n:g}" for n in sorted(numbers - allowed_numbers)]
    problems += [
        f"{c.id} is {c.status.value} but not mentioned"
        for c in packet.criteria
        if c.status is not Status.MET and c.id not in ids
    ]
    return problems


def cited_sources(packet: EvidencePacket) -> set[SourceRef]:
    cited = set(packet.flagged_documents)
    for criterion in packet.criteria:
        cited.update(criterion.sources)
        cited.update(c.record_source for c in criterion.conflicts if c.record_source)
    return cited


def missing_sources(packet: EvidencePacket, exists: Callable[[SourceRef], bool]) -> list[SourceRef]:
    return sorted((ref for ref in cited_sources(packet) if not exists(ref)), key=str)
