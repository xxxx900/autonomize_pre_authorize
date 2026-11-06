import sqlite3
from contextlib import closing

import pytest

from app.audit import AuditAction, AuditLog, Outcome, compute_hash


@pytest.fixture
def log(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    for i in range(4):
        log.append(
            actor="nurse",
            role="nurse",
            action=AuditAction.EVIDENCE_READ,
            request_id=f"req{i}",
            resource=f"PA-00{i}",
            outcome=Outcome.OK,
        )
    return log


def raw(log: AuditLog, *statements: str) -> None:
    with closing(sqlite3.connect(log._path)) as db:
        for statement in statements:
            db.execute(statement)
        db.commit()


def test_untouched_chain_verifies(log):
    status = log.verify()
    assert (status.valid, status.checked) == (True, 4)


def test_events_link_to_their_predecessor(log):
    events = log.events()
    assert [e.seq for e in events] == [1, 2, 3, 4]
    assert all(b.prev_hash == a.hash for a, b in zip(events, events[1:], strict=False))


def test_update_and_delete_are_refused_by_the_store(log):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        raw(log, "UPDATE audit_event SET actor = 'admin' WHERE seq = 2")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        raw(log, "DELETE FROM audit_event WHERE seq = 2")


def test_edited_row_is_detected_even_with_triggers_removed(log):
    raw(
        log,
        "DROP TRIGGER audit_event_no_update",
        "UPDATE audit_event SET outcome = 'ok', actor = 'admin' WHERE seq = 3",
    )
    status = log.verify()
    assert (status.valid, status.broken_at_seq, status.checked) == (False, 3, 2)


def test_deleted_middle_row_is_detected(log):
    raw(log, "DROP TRIGGER audit_event_no_delete", "DELETE FROM audit_event WHERE seq = 2")
    status = log.verify()
    assert (status.valid, status.broken_at_seq) == (False, 3)


def test_row_rewritten_with_a_recomputed_hash_breaks_the_next_link(log):
    target = log.events()[1]
    forged = compute_hash({**target.model_dump(), "ts": target.ts.isoformat(), "actor": "admin"})
    raw(
        log,
        "DROP TRIGGER audit_event_no_update",
        f"UPDATE audit_event SET actor = 'admin', hash = '{forged}' WHERE seq = 2",
    )
    status = log.verify()
    assert (status.valid, status.broken_at_seq) == (False, 3)


def test_chain_continues_across_reopen(log):
    reopened = AuditLog(log._path)
    event = reopened.append(
        actor="admin",
        role="admin",
        action=AuditAction.AUDIT_READ,
        request_id="r",
        resource=None,
        outcome=Outcome.OK,
    )
    assert event.seq == 5
    assert reopened.verify().valid
