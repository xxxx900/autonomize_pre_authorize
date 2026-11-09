"""The SHA-256 hash chain that makes an edited or deleted audit row detectable."""

import hashlib
import json
from collections.abc import Iterable, Mapping

from app.domain.audit import AuditContext, AuditEvent, ChainStatus

GENESIS_HASH = "0" * 64


def canonical_context(context: AuditContext | None) -> str | None:
    """The exact JSON text stored and hashed for a context; None when there is no context."""
    if context is None:
        return None
    body = context.model_dump(mode="json", exclude_defaults=True)
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def compute_hash(row: Mapping[str, object]) -> str:
    """Hash every field of a row with the previous row's hash.

    Rows written before the context column existed have no context and hash exactly as before.
    """
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
    if row.get("context") is not None:
        material.append(row["context"])
    return hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


def event_hash(event: AuditEvent) -> str:
    """Recompute the hash a stored event should carry."""
    return compute_hash(
        {
            **event.model_dump(),
            "ts": event.ts.isoformat(),
            "context": canonical_context(event.context),
        }
    )


def verify_chain(events: Iterable[AuditEvent]) -> ChainStatus:
    """Walk the rows in order and report the first one whose sequence or hashes do not line up."""
    prev_hash = GENESIS_HASH
    expected_seq = 1
    checked = 0
    for event in events:
        intact = (
            event.seq == expected_seq
            and event.prev_hash == prev_hash
            and event.hash == event_hash(event)
        )
        if not intact:
            return ChainStatus(valid=False, checked=checked, broken_at_seq=event.seq)
        prev_hash = event.hash
        expected_seq += 1
        checked += 1
    return ChainStatus(valid=True, checked=checked)
