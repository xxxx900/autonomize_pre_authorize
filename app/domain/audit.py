"""Audit records: who did what, when, to which request, with what result, and how fast."""

from datetime import datetime

from app.domain.base import Frozen
from app.domain.enums import AuditAction, Outcome, ResourceType
from app.domain.packet import SummaryTrace


class AuditContext(Frozen):
    """Trace detail for one audit row. Holds identifiers and timings, never clinical values.

    `subject` names the Patient whose record was read, so PHI access can be accounted for
    per member. `config` is set only on service.start rows, to trace configuration changes.
    """

    http_route: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    subject: str | None = None
    phi_resource_types: list[ResourceType] = []
    phi_resources_read: int | None = None
    policy_version: str | None = None
    policy_sha256: str | None = None
    summary: SummaryTrace | None = None
    error: str | None = None
    config: dict[str, str] = {}


class AuditEvent(Frozen):
    """One audit row, linked to the row before it by `prev_hash`."""

    seq: int
    ts: datetime
    actor: str
    role: str | None
    action: AuditAction
    request_id: str
    resource: str | None
    outcome: Outcome
    prev_hash: str
    hash: str
    context: AuditContext | None = None


class ChainStatus(Frozen):
    """Whether the hash chain is intact, and the first broken row if not."""

    valid: bool
    checked: int
    broken_at_seq: int | None = None


class AuditReport(Frozen):
    """What GET /audit returns: the chain check over every row, and the rows that matched."""

    chain: ChainStatus
    total: int
    events: list[AuditEvent]


class AuditFilter(Frozen):
    """Which rows GET /audit returns. An unset field matches every row."""

    action: AuditAction | None = None
    actor: str | None = None
    resource: str | None = None
    outcome: Outcome | None = None
    request_id: str | None = None

    def matches(self, event: AuditEvent) -> bool:
        """True when the event agrees with every field that is set."""
        return all(v is None or getattr(event, k) == v for k, v in self.model_dump().items())
