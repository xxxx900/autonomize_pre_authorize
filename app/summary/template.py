"""The fixed summary served when the model is unavailable or its output is rejected."""

from app.domain.enums import Status
from app.domain.packet import EvidencePacket


def template_summary(packet: EvidencePacket) -> str:
    """Two sentences built only from the packet: the met criteria, then each open one."""
    met = [c.id for c in packet.criteria if c.status is Status.MET]
    first = f"Met: {', '.join(met)}." if met else "No criterion is met."
    open_items = [
        f"{c.id} is {c.status.value.replace('_', ' ')} ({c.rationale})"
        for c in packet.criteria
        if c.status is not Status.MET
    ]
    second = "; ".join(open_items) + "." if open_items else "No criterion is open."
    return f"{first} {second}"
