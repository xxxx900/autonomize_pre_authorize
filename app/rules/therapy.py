"""Metformin therapy spans and the number of days they cover."""

from datetime import date

from app.domain.record import MedicationRequest
from app.domain.therapy import TherapySpan


def end_of_therapy(item: MedicationRequest, request_date: date) -> date | None:
    """The validity end, or the request date for an active prescription, or None if unknown."""
    if item.validity_end is not None:
        return item.validity_end
    if item.status == "active":
        return request_date
    return None


def therapy_span(item: MedicationRequest, request_date: date) -> TherapySpan | None:
    """The span a prescription covers, or None when its start or end is unknown or inverted."""
    end = end_of_therapy(item, request_date)
    if item.authored_on is None or end is None or end <= item.authored_on:
        return None
    return TherapySpan(item.authored_on, min(end, request_date))


def covered_days(spans: list[TherapySpan], since: date | None = None) -> int:
    """Count distinct days covered by the spans, counting overlaps once.

    With `since`, only days on or after that date count.
    """
    clipped = sorted(
        TherapySpan(max(s.start, since) if since else s.start, s.end)
        for s in spans
        if since is None or s.end > since
    )
    total = 0
    cursor: date | None = None
    for span in clipped:
        start = max(span.start, cursor) if cursor else span.start
        if span.end > start:
            total += (span.end - start).days
            cursor = span.end
    return total
