"""JSON log lines with an allow-list of fields, so no clinical value can reach a log."""

import json
import logging
import sys
from datetime import UTC, datetime

ALLOWED_FIELDS = frozenset(
    {
        "event",
        "request_id",
        "route",
        "method",
        "status",
        "duration_ms",
        "component",
        "state",
        "latency_ms",
        "summary_source",
        "summary_model",
        "summary_fallback",
        "outcome",
    }
)
FIELDS_ATTR = "fields"


class JsonFormatter(logging.Formatter):
    """Emits only allow-listed structured fields, so a stray value cannot reach a log line."""

    def format(self, record: logging.LogRecord) -> str:
        """Render one record as a JSON object with a timestamp and level."""
        line = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
        }
        fields = getattr(record, FIELDS_ATTR, None)
        if fields is None:
            line["logger"] = record.name
            line["msg"] = record.getMessage()
        else:
            line.update({k: v for k, v in fields.items() if k in ALLOWED_FIELDS})
        if record.exc_info and record.exc_info[0]:
            line["error_type"] = record.exc_info[0].__name__
        return json.dumps(line)


def configure_logging(level: str) -> None:
    """Send every log record to stdout as one JSON line."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, **fields: object) -> None:
    """Log a structured event; fields outside ALLOWED_FIELDS are dropped by the formatter."""
    logger.info("", extra={FIELDS_ATTR: fields})
