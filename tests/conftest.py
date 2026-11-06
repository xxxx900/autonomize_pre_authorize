import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.fhir_client import FhirClient
from app.main import create_app

NURSE = "test-nurse-token"
ADMIN = "test-admin-token"
RESOURCES = Path(__file__).resolve().parent.parent / "resources"


@pytest.fixture(scope="session")
def resources_dir() -> Path:
    return RESOURCES


def _bundled_resources() -> list[dict]:
    return [
        entry["resource"]
        for path in sorted((RESOURCES / "bundles").glob("*.json"))
        for entry in json.loads(path.read_text(encoding="utf-8"))["entry"]
    ]


def fake_fhir_transport(resources: list[dict], reachable: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if not reachable:
            raise httpx.ConnectError("down")
        parts = request.url.path.removeprefix("/fhir").strip("/").split("/")
        if parts == ["metadata"]:
            return httpx.Response(200, json={"resourceType": "CapabilityStatement"})
        if len(parts) == 2:
            match = [r for r in resources if (r["resourceType"], r["id"]) == tuple(parts)]
            return httpx.Response(200, json=match[0]) if match else httpx.Response(404)
        patient = request.url.params["patient"]
        entries = [
            {"resource": r}
            for r in resources
            if r["resourceType"] == parts[0]
            and patient in json.dumps(r.get("subject", r.get("patient", {})))
        ]
        return httpx.Response(200, json={"resourceType": "Bundle", "entry": entries})

    return httpx.MockTransport(handler)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        nurse_token=NURSE,
        admin_token=ADMIN,
        audit_db_path=tmp_path / "audit.db",
        resources_dir=RESOURCES,
        fhir_base_url="http://fhir.test/fhir",
    )


@pytest.fixture
def make_client(settings):
    def build(resources: list[dict] | None = None, reachable: bool = True) -> TestClient:
        data = _bundled_resources() if resources is None else resources
        transport = fake_fhir_transport(data, reachable)
        return TestClient(create_app(settings, FhirClient(settings, transport)))

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
