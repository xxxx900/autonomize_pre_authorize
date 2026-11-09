"""httpx auth flows for the FHIR server: a static bearer token or SMART client credentials."""

import time
from collections.abc import Generator

import httpx

from app.config import FhirSettings
from app.domain.enums import FhirAuthMode

TOKEN_EXPIRY_MARGIN_SECONDS = 30


class FhirAuthError(Exception):
    """The SMART token endpoint refused to issue a token."""


class BearerAuth(httpx.Auth):
    """Sends one fixed bearer token on every request."""

    def __init__(self, token: str) -> None:
        """Keep the token to send."""
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        """Add the Authorization header."""
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class SmartClientCredentialsAuth(httpx.Auth):
    """SMART backend services: fetch a token with client credentials and reuse it until expiry."""

    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str) -> None:
        """Keep the token request form; the first request fetches the token."""
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
        """Refresh the token when it is missing or about to expire, then send the request."""
        if self._token is None or time.monotonic() >= self._expires_at:
            response = yield httpx.Request("POST", self._token_url, data=self._form)
            response.read()
            if response.status_code != 200:
                raise FhirAuthError(f"token endpoint returned {response.status_code}")
            body = response.json()
            self._token = body["access_token"]
            lifetime = float(body.get("expires_in", 300))
            self._expires_at = time.monotonic() + lifetime - TOKEN_EXPIRY_MARGIN_SECONDS
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


def build_auth(settings: FhirSettings) -> httpx.Auth | None:
    """The auth flow for the configured mode; settings validation guarantees its fields."""
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
