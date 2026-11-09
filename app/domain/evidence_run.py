"""The result of one successful evidence run."""

from dataclasses import dataclass

from app.domain.audit import AuditContext
from app.domain.packet import EvidencePacket


@dataclass(frozen=True)
class EvidenceRun:
    """A finished run: the packet for the caller and the context for the audit row."""

    packet: EvidencePacket
    context: AuditContext
