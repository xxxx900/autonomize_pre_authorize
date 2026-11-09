import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients.fhir_client import FhirClient
from app.config import Settings
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


@dataclass(frozen=True, eq=False)
class FakeFhir:
    """An in-memory FHIR server: metadata, read by id, and search by patient."""

    resources: list[dict]
    reachable: bool = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request the way HAPI would for these resources."""
        if not self.reachable:
            raise httpx.ConnectError("down")
        parts = request.url.path.removeprefix("/fhir").strip("/").split("/")
        if parts == ["metadata"]:
            return httpx.Response(
                200,
                json={
                    "resourceType": "CapabilityStatement",
                    "fhirVersion": "4.0.1",
                    "software": {"name": "Fake FHIR", "version": "1"},
                },
            )
        if len(parts) == 2:
            match = [r for r in self.resources if (r["resourceType"], r["id"]) == tuple(parts)]
            return httpx.Response(200, json=match[0]) if match else httpx.Response(404)
        patient = request.url.params["patient"]
        entries = [
            {"resource": r}
            for r in self.resources
            if r["resourceType"] == parts[0]
            and patient in json.dumps(r.get("subject", r.get("patient", {})))
        ]
        return httpx.Response(200, json={"resourceType": "Bundle", "entry": entries})


def fake_fhir_transport(resources: list[dict], reachable: bool = True) -> httpx.MockTransport:
    """A transport that routes FhirClient calls to a FakeFhir."""
    return httpx.MockTransport(FakeFhir(resources, reachable))


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


def build_client(
    settings: Settings, resources: list[dict] | None = None, reachable: bool = True
) -> TestClient:
    """A TestClient over the app, backed by the bundled resources unless others are given."""
    data = _bundled_resources() if resources is None else resources
    transport = fake_fhir_transport(data, reachable)
    return TestClient(create_app(settings, FhirClient(settings, transport)))


@pytest.fixture
def fhir_client(settings) -> FhirClient:
    return FhirClient(settings, fake_fhir_transport(_bundled_resources()))


@pytest.fixture
def make_client(settings):
    return partial(build_client, settings)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
