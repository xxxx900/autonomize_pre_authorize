"""Read-only FHIR R4 client: fetch a member's resources and confirm cited resources exist."""

import httpx

from app.clients.fhir_auth import FhirAuthError, build_auth
from app.config import FhirSettings
from app.domain.enums import ResourceType
from app.domain.provenance import SourceRef

PATIENT_SCOPED_TYPES = (
    ResourceType.CONDITION,
    ResourceType.OBSERVATION,
    ResourceType.MEDICATION_REQUEST,
    ResourceType.ALLERGY_INTOLERANCE,
    ResourceType.DOCUMENT_REFERENCE,
)
PAGE_SIZE = 200
MAX_PAGES = 50


class FhirError(Exception):
    """The FHIR server could not be reached or answered with an error."""


class PatientNotFound(FhirError):
    """The FHIR server has no Patient with the requested id."""


class FhirClient:
    """A synchronous FHIR client bound to one server and one auth mode."""

    def __init__(
        self, settings: FhirSettings, transport: httpx.BaseTransport | None = None
    ) -> None:
        """Open a connection pool to the configured FHIR base URL."""
        self._http = httpx.Client(
            base_url=settings.fhir_base_url.rstrip("/") + "/",
            auth=build_auth(settings),
            timeout=settings.fhir_timeout_seconds,
            headers={"Accept": "application/fhir+json"},
            transport=transport,
        )

    @property
    def http(self) -> httpx.Client:
        """The underlying httpx client, for the bundle loader script."""
        return self._http

    def close(self) -> None:
        """Close the connection pool."""
        self._http.close()

    def ping(self) -> bool:
        """True when the server answers its capability statement."""
        try:
            return self.capability_statement() is not None
        except FhirError:
            return False

    def capability_statement(self, timeout_seconds: float | None = None) -> dict | None:
        """The server's CapabilityStatement summary, or None on a non-200 answer.

        Raises FhirError when the server cannot be reached.
        """
        try:
            response = self._http.get(
                "metadata",
                params={"_summary": "true"},
                timeout=timeout_seconds or self._http.timeout,
            )
        except (httpx.HTTPError, FhirAuthError) as exc:
            raise FhirError(f"FHIR unreachable: {type(exc).__name__}") from exc
        return response.json() if response.status_code == 200 else None

    def exists(self, ref: SourceRef) -> bool:
        """True when the server holds this resource; raises FhirError on any other failure."""
        response = self._get(str(ref))
        if response.status_code == 404:
            return False
        self._ok(response)
        return True

    def patient_resources(self, patient_id: str) -> list[dict]:
        """The Patient resource followed by every patient-scoped resource of the read types."""
        response = self._get(f"{ResourceType.PATIENT}/{patient_id}")
        if response.status_code == 404:
            raise PatientNotFound(patient_id)
        self._ok(response)
        resources = [response.json()]
        for resource_type in PATIENT_SCOPED_TYPES:
            resources.extend(self._search(resource_type, patient_id))
        return resources

    def _search(self, resource_type: ResourceType, patient_id: str) -> list[dict]:
        """Every resource of one type for a patient, following `next` links page by page."""
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
        """GET relative to the base URL, turning transport and auth failures into FhirError."""
        try:
            return self._http.get(url, params=params)
        except (httpx.HTTPError, FhirAuthError) as exc:
            raise FhirError(f"FHIR unreachable: {type(exc).__name__}") from exc

    @staticmethod
    def _ok(response: httpx.Response) -> None:
        """Raise FhirError unless the response is 200."""
        if response.status_code != 200:
            raise FhirError(f"FHIR returned {response.status_code}")
