import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

GENESIS_HASH = "0" * 64


class AuditAction(StrEnum):
    EVIDENCE_READ = "evidence.read"
    POLICY_READ = "policy.read"
    AUDIT_READ = "audit.read"


class Outcome(StrEnum):
    OK = "ok"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    ERROR = "error"


class AuditEvent(BaseModel):
    """One audit row. Carries identity and outcome only, never clinical values."""

    model_config = ConfigDict(frozen=True)

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


class ChainStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    valid: bool
    checked: int
    broken_at_seq: int | None = None


def compute_hash(row: Mapping[str, object]) -> str:
    material = [
        row["seq"],
        row["ts"],
        row["actor"],
        row["role"],
        str(row["action"]),
        row["request_id"],
        row["resource"],
        str(row["outcome"]),
        row["prev_hash"],
    ]
    return hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


def _event_hash(event: AuditEvent) -> str:
    return compute_hash({**event.model_dump(), "ts": event.ts.isoformat()})


def verify_chain(events: Iterable[AuditEvent]) -> ChainStatus:
    prev_hash = GENESIS_HASH
    expected_seq = 1
    checked = 0
    for event in events:
        intact = (
            event.seq == expected_seq
            and event.prev_hash == prev_hash
            and event.hash == _event_hash(event)
        )
        if not intact:
            return ChainStatus(valid=False, checked=checked, broken_at_seq=event.seq)
        prev_hash = event.hash
        expected_seq += 1
        checked += 1
    return ChainStatus(valid=True, checked=checked)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_event (
    seq        INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    role       TEXT,
    action     TEXT NOT NULL,
    request_id TEXT NOT NULL,
    resource   TEXT,
    outcome    TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_event_no_update
BEFORE UPDATE ON audit_event BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_event_no_delete
BEFORE DELETE ON audit_event BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


class AuditLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._path, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def append(
        self,
        *,
        actor: str,
        role: str | None,
        action: AuditAction,
        request_id: str,
        resource: str | None,
        outcome: Outcome,
    ) -> AuditEvent:
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute(
                "SELECT seq, hash FROM audit_event ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            row = {
                "seq": last["seq"] + 1 if last else 1,
                "ts": datetime.now(UTC).isoformat(),
                "actor": actor,
                "role": role,
                "action": action.value,
                "request_id": request_id,
                "resource": resource,
                "outcome": outcome.value,
                "prev_hash": last["hash"] if last else GENESIS_HASH,
            }
            row["hash"] = compute_hash(row)
            db.execute(
                "INSERT INTO audit_event VALUES "
                "(:seq, :ts, :actor, :role, :action, :request_id, :resource, :outcome,"
                " :prev_hash, :hash)",
                row,
            )
            db.execute("COMMIT")
        return AuditEvent(**row)

    def events(self) -> list[AuditEvent]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM audit_event ORDER BY seq").fetchall()
        return [AuditEvent(**dict(r)) for r in rows]

    def verify(self) -> ChainStatus:
        return verify_chain(self.events())
