"""The SQLite table that holds the audit chain. Triggers make it append-only."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.audit.hash_chain import GENESIS_HASH, canonical_context, compute_hash, verify_chain
from app.domain.audit import AuditContext, AuditEvent, ChainStatus
from app.domain.enums import AuditAction, Outcome

SCHEMA = """
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
CONTEXT_COLUMN = "context"


def ensure_context_column(db: sqlite3.Connection) -> None:
    """Add the context column to a table created before it existed. Safe to run every start."""
    columns = {row["name"] for row in db.execute("PRAGMA table_info(audit_event)")}
    if CONTEXT_COLUMN not in columns:
        db.execute(f"ALTER TABLE audit_event ADD COLUMN {CONTEXT_COLUMN} TEXT")


def event_from_row(row: sqlite3.Row) -> AuditEvent:
    """Build an AuditEvent from a stored row, parsing the context JSON if present."""
    data = dict(row)
    raw = data.pop(CONTEXT_COLUMN, None)
    context = AuditContext.model_validate(json.loads(raw)) if raw else None
    return AuditEvent(**data, context=context)


class AuditLog:
    """Appends and reads audit rows. Each append runs in its own write transaction."""

    def __init__(self, path: Path) -> None:
        """Create the table, triggers, and context column if they do not exist."""
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.executescript(SCHEMA)
            ensure_context_column(db)

    @property
    def path(self) -> Path:
        """The SQLite file this log writes to."""
        return self._path

    def _connect(self) -> sqlite3.Connection:
        """Open a connection in autocommit mode so transactions are explicit."""
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
        context: AuditContext | None = None,
    ) -> AuditEvent:
        """Write the next row, chained to the last one. BEGIN IMMEDIATE keeps seq gapless."""
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
                "context": canonical_context(context),
            }
            row["hash"] = compute_hash(row)
            db.execute(
                "INSERT INTO audit_event "
                "(seq, ts, actor, role, action, request_id, resource, outcome, prev_hash, hash,"
                " context) VALUES "
                "(:seq, :ts, :actor, :role, :action, :request_id, :resource, :outcome,"
                " :prev_hash, :hash, :context)",
                row,
            )
            db.execute("COMMIT")
        return AuditEvent(**{**row, "context": context})

    def events(self) -> list[AuditEvent]:
        """Every row, oldest first."""
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM audit_event ORDER BY seq").fetchall()
        return [event_from_row(r) for r in rows]

    def verify(self) -> ChainStatus:
        """Check the whole chain."""
        return verify_chain(self.events())

    def writable(self) -> bool:
        """True when a write transaction can be opened, for the readiness probe."""
        try:
            with closing(self._connect()) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("ROLLBACK")
        except sqlite3.Error:
            return False
        return True
