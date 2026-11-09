"""The facts a piece of text states, as compared by the summary faithfulness check."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FactTokens:
    """The dates, criterion ids, and numbers a text states."""

    dates: frozenset[str]
    ids: frozenset[str]
    numbers: frozenset[float]
