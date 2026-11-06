from app.audit import Outcome


class PipelineError(Exception):
    """A failed evidence run: the audit outcome, the HTTP status and a PHI-free message."""

    def __init__(self, outcome: Outcome, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.outcome = outcome
        self.status_code = status_code
        self.detail = detail
