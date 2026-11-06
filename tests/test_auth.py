import pytest

from app.auth import Principal, Role, authenticate
from app.config import Settings
from tests.conftest import ADMIN, NURSE, bearer

NURSE_PRINCIPAL = Principal(actor="nurse", role=Role.NURSE)
ADMIN_PRINCIPAL = Principal(actor="admin", role=Role.ADMIN)
TOKENS = {"n": NURSE_PRINCIPAL, "a": ADMIN_PRINCIPAL}


def audit_rows(client):
    return client.get("/audit", headers=bearer(ADMIN)).json()["events"]


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer n", NURSE_PRINCIPAL),
        ("bearer a", ADMIN_PRINCIPAL),
        ("Bearer nope", None),
        ("Basic n", None),
        ("Bearer ", None),
        ("n", None),
        (None, None),
    ],
)
def test_authenticate(header, expected):
    assert authenticate(header, TOKENS) == expected


def test_missing_token_is_401_and_audited(client):
    response = client.get("/requests/PA-001/evidence")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    refused = audit_rows(client)[0]
    assert (refused["actor"], refused["role"], refused["outcome"], refused["resource"]) == (
        "anonymous",
        None,
        "unauthenticated",
        "PA-001",
    )


def test_bad_token_is_401_and_audited_without_the_token(client):
    response = client.get("/policy", headers=bearer("guess"))
    assert response.status_code == 401
    events = audit_rows(client)
    assert events[0]["actor"] == "unknown"
    assert "guess" not in str(events)


def test_nurse_cannot_read_audit_and_the_attempt_is_audited(client):
    assert client.get("/audit", headers=bearer(NURSE)).status_code == 403
    refused = audit_rows(client)[0]
    assert (refused["actor"], refused["role"], refused["outcome"]) == (
        "nurse",
        "nurse",
        "forbidden",
    )


def test_admin_reads_audit_with_a_valid_chain(client):
    client.get("/requests/PA-001/evidence", headers=bearer(NURSE))
    client.get("/requests/PA-001/evidence")
    body = client.get("/audit", headers=bearer(ADMIN)).json()
    assert body["chain"] == {"valid": True, "checked": 2, "broken_at_seq": None}
    assert [e["outcome"] for e in body["events"]] == ["ok", "unauthenticated"]


def test_audit_events_carry_no_clinical_fields(client):
    client.get("/requests/PA-006/evidence", headers=bearer(NURSE))
    event = audit_rows(client)[0]
    assert set(event) == {
        "seq",
        "ts",
        "actor",
        "role",
        "action",
        "request_id",
        "resource",
        "outcome",
        "prev_hash",
        "hash",
    }


def test_health_needs_no_token_and_ready_reflects_fhir(make_client):
    assert make_client().get("/health").json() == {"status": "ok"}
    assert make_client().get("/ready").status_code == 200
    assert make_client(reachable=False).get("/ready").status_code == 503


def test_equal_tokens_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="must differ"):
        Settings(_env_file=None, nurse_token="x", admin_token="x", audit_db_path=tmp_path / "a")
