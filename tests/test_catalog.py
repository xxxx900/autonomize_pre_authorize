"""The worksheet's dropdowns: request ids from disk and the summary model allow-list."""

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.summary.summarizer import Summarizer
from tests.conftest import ADMIN, NURSE, bearer

DEFAULT = "llama3.2:3b"
CHOICE = "qwen2.5:3b"


def ollama_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


def client_with_choices(settings, fhir_client) -> TestClient:
    summarizer = Summarizer(
        "http://ollama.test", DEFAULT, 5, httpx.MockTransport(ollama_down), choices=(CHOICE,)
    )
    return TestClient(create_app(settings, fhir_client, summarizer))


def audit_rows(client: TestClient, action: str) -> list[dict]:
    events = client.get("/audit", headers=bearer(ADMIN)).json()["events"]
    return [e for e in events if e["action"] == action]


def test_catalog_lists_every_request_form_and_the_allowed_models(settings, fhir_client):
    client = client_with_choices(settings, fhir_client)
    body = client.get("/catalog", headers=bearer(NURSE)).json()
    assert body["request_ids"] == [f"PA-00{n}" for n in range(1, 8)]
    assert body["summary_models"] == {"default": DEFAULT, "choices": [DEFAULT, CHOICE]}
    assert [e["outcome"] for e in audit_rows(client, "catalog.read")] == ["ok"]


def test_catalog_refuses_a_caller_without_a_token(client):
    assert client.get("/catalog").status_code == 401
    assert [e["outcome"] for e in audit_rows(client, "catalog.read")] == ["unauthenticated"]


def test_a_picked_model_writes_the_summary_and_is_recorded(settings, fhir_client):
    client = client_with_choices(settings, fhir_client)
    url = f"/requests/PA-002/evidence?summary_model={CHOICE}"
    packet = client.get(url, headers=bearer(NURSE)).json()
    assert packet["trace"]["summary"]["model"] == CHOICE
    [row] = audit_rows(client, "evidence.read")
    assert row["context"]["summary"]["model"] == CHOICE


def test_a_model_outside_the_allow_list_is_refused_and_audited(settings, fhir_client):
    client = client_with_choices(settings, fhir_client)
    response = client.get("/requests/PA-002/evidence?summary_model=evil:70b", headers=bearer(NURSE))
    assert response.status_code == 422
    [row] = audit_rows(client, "evidence.read")
    assert (row["outcome"], row["context"]["status_code"]) == ("error", 422)


def test_settings_put_the_default_first_and_drop_duplicates(settings):
    both = Settings(
        **{**settings.model_dump(), "summary_model_choices": f" {CHOICE}, {DEFAULT},,"},
        _env_file=None,
    )
    assert both.summary_models == (both.summary_model, CHOICE, DEFAULT)
    assert settings.summary_models == (settings.summary_model,)
