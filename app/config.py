from enum import StrEnum
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class FhirAuthMode(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    SMART = "smart"


class FhirSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fhir_base_url: str = "http://localhost:8080/fhir"
    fhir_auth_mode: FhirAuthMode = FhirAuthMode.NONE
    fhir_bearer_token: SecretStr | None = None
    fhir_token_url: str | None = None
    fhir_client_id: str | None = None
    fhir_client_secret: SecretStr | None = None
    fhir_scope: str = "system/*.read"
    fhir_timeout_seconds: float = 10.0

    @model_validator(mode="after")
    def _check_auth_fields(self) -> "FhirSettings":
        needed = {
            FhirAuthMode.NONE: (),
            FhirAuthMode.BEARER: ("fhir_bearer_token",),
            FhirAuthMode.SMART: ("fhir_token_url", "fhir_client_id", "fhir_client_secret"),
        }[self.fhir_auth_mode]
        absent = [name.upper() for name in needed if not getattr(self, name)]
        if absent:
            raise ValueError(f"FHIR_AUTH_MODE={self.fhir_auth_mode} requires {', '.join(absent)}")
        return self


class Settings(FhirSettings):
    nurse_token: SecretStr = Field(min_length=1)
    admin_token: SecretStr = Field(min_length=1)

    resources_dir: Path = REPO_ROOT / "resources"
    policy_file: str = "policy_MP-SYN-021.json"
    extra_requests_dir: Path | None = None
    audit_db_path: Path = REPO_ROOT / "audit" / "audit.db"
    log_level: str = "INFO"
    ollama_url: str | None = None
    summary_model: str = "llama3.2:3b-instruct-q4_K_M"
    summary_timeout_seconds: float = 30.0

    @property
    def policy_path(self) -> Path:
        return self.resources_dir / self.policy_file

    @property
    def request_dirs(self) -> tuple[Path, ...]:
        primary = self.resources_dir / "requests"
        return (primary, self.extra_requests_dir) if self.extra_requests_dir else (primary,)

    @model_validator(mode="after")
    def _check_tokens(self) -> "Settings":
        if self.nurse_token.get_secret_value() == self.admin_token.get_secret_value():
            raise ValueError("NURSE_TOKEN and ADMIN_TOKEN must differ")
        return self
