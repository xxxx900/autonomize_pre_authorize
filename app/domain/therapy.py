"""Value types for metformin therapy duration."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, order=True)
class TherapySpan:
    """The dates one prescription covers, ending no later than the request date."""

    start: date
    end: date
