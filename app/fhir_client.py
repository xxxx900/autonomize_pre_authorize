import time
from collections.abc import Generator

import httpx

from app.config import FhirAuthMode, FhirSettings
from app.record import PatientRecord, SourceRef, record_from_resources

PATIENT_SCOPED_TYPES = (
    "Condition",
    "Observation",
    "MedicationRequest",
    "AllergyIntolerance",
    "DocumentReference",
)
PAGE_SIZE = 200
MAX_PAGES = 50
TOKEN_EXPIRY_MARGIN_SECONDS = 30


class FhirError(Exception):
    pass


class PatientNotFound(FhirError):
    pass


class BearerAuth(httpx.Auth):
    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class SmartClientCredentialsAuth(httpx.Auth):
    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str) -> None:
        self._token_url = token_url
        self._form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        }
        self._token: str | None = None
        self._expires_at = 0.0

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        if self._token is None or time.monotonic() >= self._expires_at:
            response = yield httpx.Request("POST", self._token_url, data=self._form)
            response.read()
            if response.status_code != 200:
                raise FhirError(f"token endpoint returned {response.status_code}")
            body = response.json()
            self._token = body["access_token"]
            lifetime = float(body.get("expires_in", 300))
            self._expires_at = time.monotonic() + lifetime - TOKEN_EXPIRY_MARGIN_SECONDS
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


def build_auth(settings: FhirSettings) -> httpx.Auth | None:
    match settings.fhir_auth_mode:
        case FhirAuthMode.NONE:
            return None
        case FhirAuthMode.BEARER:
            assert settings.fhir_bearer_token is not None
            return BearerAuth(settings.fhir_bearer_token.get_secret_value())
        case FhirAuthMode.SMART:
            assert settings.fhir_token_url and settings.fhir_client_id
            assert settings.fhir_client_secret is not None
            return SmartClientCredentialsAuth(
                settings.fhir_token_url,
                settings.fhir_client_id,
                settings.fhir_client_secret.get_secret_value(),
                settings.fhir_scope,
            )


class FhirClient:
    def __init__(
        self, settings: FhirSettings, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(
            base_url=settings.fhir_base_url.rstrip("/") + "/",
            auth=build_auth(settings),
            timeout=settings.fhir_timeout_seconds,
            headers={"Accept": "application/fhir+json"},
            transport=transport,
        )

    @property
    def http(self) -> httpx.Client:
        return self._http

    def close(self) -> None:
        self._http.close()

    def ping(self) -> bool:
        try:
            return self._http.get("metadata", params={"_summary": "true"}).status_code == 200
        except httpx.HTTPError:
            return False

    def exists(self, ref: SourceRef) -> bool:
        response = self._get(f"{ref.resource_type}/{ref.id}")
        if response.status_code == 404:
            return False
        self._ok(response)
        return True

    def patient_resources(self, patient_id: str) -> list[dict]:
        response = self._get(f"Patient/{patient_id}")
        if response.status_code == 404:
            raise PatientNotFound(patient_id)
        self._ok(response)
        resources = [response.json()]
        for resource_type in PATIENT_SCOPED_TYPES:
            resources.extend(self._search(resource_type, patient_id))
        return resources

    def patient_record(self, patient_id: str) -> PatientRecord:
        return record_from_resources(self.patient_resources(patient_id))

    def _search(self, resource_type: str, patient_id: str) -> list[dict]:
        found: list[dict] = []
        response = self._get(resource_type, params={"patient": patient_id, "_count": PAGE_SIZE})
        for _ in range(MAX_PAGES):
            self._ok(response)
            bundle = response.json()
            found.extend(e["resource"] for e in bundle.get("entry", []) if "resource" in e)
            next_url = next(
                (link["url"] for link in bundle.get("link", []) if link["relation"] == "next"),
                None,
            )
            if next_url is None:
                return found
            response = self._get("", params=dict(httpx.URL(next_url).params))
        raise FhirError(f"{resource_type} search exceeded {MAX_PAGES} pages")

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        try:
            return self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise FhirError(f"FHIR unreachable: {type(exc).__name__}") from exc

    @staticmethod
    def _ok(response: httpx.Response) -> None:
        if response.status_code != 200:
            raise FhirError(f"FHIR returned {response.status_code}")
