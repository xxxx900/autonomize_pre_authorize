import json
import logging
import sys
from datetime import UTC, datetime

ALLOWED_FIELDS = frozenset({"event", "request_id", "route", "method", "status", "duration_ms"})
FIELDS_ATTR = "fields"


class JsonFormatter(logging.Formatter):
    """Emits only allow-listed structured fields, so a stray value cannot reach a log line."""

    def format(self, record: logging.LogRecord) -> str:
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
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, **fields: object) -> None:
    logger.info("", extra={FIELDS_ATTR: fields})
