from collections.abc import Callable

from app.packet import EvidencePacket
from app.record import SourceRef


def cited_sources(packet: EvidencePacket) -> set[SourceRef]:
    cited = set(packet.flagged_documents)
    for criterion in packet.criteria:
        cited.update(criterion.sources)
        cited.update(c.record_source for c in criterion.conflicts if c.record_source)
    return cited


def missing_sources(packet: EvidencePacket, exists: Callable[[SourceRef], bool]) -> list[SourceRef]:
    return sorted(
        (ref for ref in cited_sources(packet) if not exists(ref)),
        key=str,
    )
