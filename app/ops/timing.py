"""Wall-clock timing helpers shared by the pipeline, the summarizer, and health probes."""

import time


def elapsed_ms(started: float) -> float:
    """Milliseconds since a time.perf_counter() reading, to one decimal."""
    return round((time.perf_counter() - started) * 1000, 1)
