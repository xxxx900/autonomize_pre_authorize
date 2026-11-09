from functools import partial

import httpx
import pytest

from app.clients.fhir_client import FhirClient, FhirError, PatientNotFound
from app.config import FhirSettings
from app.domain.provenance import SourceRef


def client_for(handler, **env) -> FhirClient:
    settings = FhirSettings(_env_file=None, fhir_base_url="http://f.test/fhir", **env)
    return FhirClient(settings, httpx.MockTransport(handler))


def record_auth(seen: dict, request: httpx.Request) -> httpx.Response:
    seen["auth"] = request.headers.get("authorization")
    return httpx.Response(200, json={})


def test_bearer_mode_sends_the_token():
    seen = {}
    client = client_for(
        partial(record_auth, seen), fhir_auth_mode="bearer", fhir_bearer_token="abc"
    )
    assert client.ping()
    assert seen["auth"] == "Bearer abc"


def smart_server(calls: list, request: httpx.Request) -> httpx.Response:
    calls.append(request.url.path)
    if request.url.path == "/token":
        return httpx.Response(200, json={"access_token": "t1", "expires_in": 3600})
    assert request.headers["authorization"] == "Bearer t1"
    return httpx.Response(200, json={})


def test_smart_mode_fetches_and_reuses_a_token():
    calls = []
    client = client_for(
        partial(smart_server, calls),
        fhir_auth_mode="smart",
        fhir_token_url="http://f.test/token",
        fhir_client_id="id",
        fhir_client_secret="secret",
    )
    assert client.ping() and client.ping()
    assert calls.count("/token") == 1


def test_incomplete_smart_settings_are_rejected():
    with pytest.raises(ValueError, match="FHIR_TOKEN_URL"):
        FhirSettings(_env_file=None, fhir_auth_mode="smart")


def paged_server(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("Patient/p1"):
        return httpx.Response(200, json={"resourceType": "Patient", "id": "p1"})
    if "_getpages" in request.url.params:
        return httpx.Response(
            200, json={"entry": [{"resource": {"resourceType": "Condition", "id": "c2"}}]}
        )
    if request.url.path.endswith("/Condition"):
        return httpx.Response(
            200,
            json={
                "entry": [{"resource": {"resourceType": "Condition", "id": "c1"}}],
                "link": [{"relation": "next", "url": "http://other-host/fhir?_getpages=x"}],
            },
        )
    return httpx.Response(200, json={"entry": []})


def test_search_follows_next_links_and_keeps_every_resource():
    resources = client_for(paged_server).patient_resources("p1")
    assert [r["id"] for r in resources if r["resourceType"] == "Condition"] == ["c1", "c2"]


def status_by_id(request: httpx.Request) -> httpx.Response:
    status = {"yes": 200, "no": 404}.get(request.url.path.rsplit("/", 1)[1], 500)
    return httpx.Response(status, json={})


def test_exists_distinguishes_missing_from_failure():
    client = client_for(status_by_id)
    assert client.exists(SourceRef(resource_type="Condition", id="yes"))
    assert not client.exists(SourceRef(resource_type="Condition", id="no"))
    with pytest.raises(FhirError):
        client.exists(SourceRef(resource_type="Condition", id="boom"))


def test_unknown_patient():
    with pytest.raises(PatientNotFound):
        client_for(lambda r: httpx.Response(404)).patient_resources("nobody")
