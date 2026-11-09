"""Service settings, read from environment variables and `.env`, validated at startup."""

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import FhirAuthMode

REPO_ROOT = Path(__file__).resolve().parent.parent
FHIR_AUTH_REQUIRED_FIELDS: dict[FhirAuthMode, tuple[str, ...]] = {
    FhirAuthMode.NONE: (),
    FhirAuthMode.BEARER: ("fhir_bearer_token",),
    FhirAuthMode.SMART: ("fhir_token_url", "fhir_client_id", "fhir_client_secret"),
}


class FhirSettings(BaseSettings):
    """How to reach and authenticate to the FHIR server."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fhir_base_url: str = "http://localhost:8080/fhir"
    fhir_public_base_url: str | None = None
    fhir_auth_mode: FhirAuthMode = FhirAuthMode.NONE
    fhir_bearer_token: SecretStr | None = None
    fhir_token_url: str | None = None
    fhir_client_id: str | None = None
    fhir_client_secret: SecretStr | None = None
    fhir_scope: str = "system/*.read"
    fhir_timeout_seconds: float = 10.0

    @property
    def fhir_link_base(self) -> str:
        """The FHIR base URL a person's browser can open; defaults to the service's own URL."""
        return (self.fhir_public_base_url or self.fhir_base_url).rstrip("/")

    @model_validator(mode="after")
    def _check_auth_fields(self) -> "FhirSettings":
        """Refuse to start when the chosen auth mode lacks the fields it needs."""
        needed = FHIR_AUTH_REQUIRED_FIELDS[self.fhir_auth_mode]
        absent = [name.upper() for name in needed if not getattr(self, name)]
        if absent:
            raise ValueError(f"FHIR_AUTH_MODE={self.fhir_auth_mode} requires {', '.join(absent)}")
        return self


class Settings(FhirSettings):
    """Every setting the API and the MCP server read."""

    nurse_token: SecretStr = Field(min_length=1)
    admin_token: SecretStr = Field(min_length=1)

    resources_dir: Path = REPO_ROOT / "resources"
    policy_file: str = "policy_MP-SYN-021.json"
    extra_requests_dir: Path | None = None
    audit_db_path: Path = REPO_ROOT / "audit" / "audit.db"
    log_level: str = "INFO"
    ollama_url: str | None = None
    summary_model: str = "llama3.2:3b-instruct-q4_K_M"
    summary_model_choices: str = ""
    summary_timeout_seconds: float = 30.0
    health_timeout_seconds: float = 3.0
    mcp_health_url: str | None = None

    @property
    def summary_models(self) -> tuple[str, ...]:
        """The default summary model, then each comma-separated SUMMARY_MODEL_CHOICES entry."""
        extra = (m.strip() for m in self.summary_model_choices.split(","))
        return tuple(dict.fromkeys((self.summary_model, *(m for m in extra if m))))

    @property
    def policy_path(self) -> Path:
        """The policy JSON file the service loads at startup."""
        return self.resources_dir / self.policy_file

    @property
    def request_dirs(self) -> tuple[Path, ...]:
        """Directories searched, in order, for request form JSON files."""
        primary = self.resources_dir / "requests"
        return (primary, self.extra_requests_dir) if self.extra_requests_dir else (primary,)

    def fingerprint(self) -> dict[str, str]:
        """Non-secret settings recorded on the service.start audit row to trace config changes."""
        return {
            "fhir_base_url": self.fhir_base_url,
            "fhir_auth_mode": self.fhir_auth_mode.value,
            "policy_file": self.policy_file,
            "request_dirs": ",".join(str(d) for d in self.request_dirs),
            "ollama_url": self.ollama_url or "",
            "summary_model": self.summary_model,
            "summary_model_choices": ",".join(self.summary_models[1:]),
            "summary_timeout_seconds": f"{self.summary_timeout_seconds:g}",
        }

    @model_validator(mode="after")
    def _check_tokens(self) -> "Settings":
        """Refuse to start when the nurse and admin tokens are the same."""
        if self.nurse_token.get_secret_value() == self.admin_token.get_secret_value():
            raise ValueError("NURSE_TOKEN and ADMIN_TOKEN must differ")
        return self
