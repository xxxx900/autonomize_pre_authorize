"""Health reports for the service and each component it depends on."""

from datetime import datetime

from app.domain.base import Frozen
from app.domain.enums import Component, HealthState


class ComponentCheck(Frozen):
    """The result of probing one component.

    A required component that is down makes the service not ready. An optional one, such as the
    summary model, only degrades it: the service still serves packets with a template summary.
    """

    component: Component
    state: HealthState
    required: bool
    latency_ms: float | None = None
    detail: str
    facts: dict[str, str] = {}


class HealthReport(Frozen):
    """The overall state and every component check behind it."""

    state: HealthState
    checked_at: datetime
    uptime_seconds: float
    components: list[ComponentCheck]


class ReadinessReport(Frozen):
    """What GET /ready returns: the overall state and each component's state, nothing more."""

    status: str
    components: dict[Component, HealthState]
