"""Probe every component the service depends on and roll the results into one state.

Required components (FHIR, audit log, policy, request store) decide readiness. Optional ones
(summary model, MCP server) only degrade the service, which still serves template summaries.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.audit.store import AuditLog
from app.clients.fhir_client import FhirClient, FhirError
from app.domain.enums import Component, HealthState
from app.domain.health import ComponentCheck, HealthReport
from app.domain.policy import Policy
from app.loaders.policy_file import file_sha256
from app.loaders.request_file import count_request_files
from app.ops.timing import elapsed_ms
from app.summary.summarizer import Summarizer


def overall_state(checks: list[ComponentCheck]) -> HealthState:
    """Down if a required component is down; degraded if anything else is not up; else up."""
    if any(c.required and c.state is HealthState.DOWN for c in checks):
        return HealthState.DOWN
    if any(c.state is not HealthState.UP for c in checks):
        return HealthState.DEGRADED
    return HealthState.UP


def probe_fhir(fhir: FhirClient, timeout_seconds: float) -> ComponentCheck:
    """Fetch the FHIR capability statement and report the server's FHIR and software versions."""
    started = time.perf_counter()
    try:
        statement = fhir.capability_statement(timeout_seconds)
    except FhirError as exc:
        return ComponentCheck(
            component=Component.FHIR,
            state=HealthState.DOWN,
            required=True,
            latency_ms=elapsed_ms(started),
            detail=str(exc),
        )
    if statement is None:
        return ComponentCheck(
            component=Component.FHIR,
            state=HealthState.DOWN,
            required=True,
            latency_ms=elapsed_ms(started),
            detail="capability statement request did not return 200",
        )
    software = statement.get("software") or {}
    return ComponentCheck(
        component=Component.FHIR,
        state=HealthState.UP,
        required=True,
        latency_ms=elapsed_ms(started),
        detail="capability statement answered",
        facts={
            "fhir_version": str(statement.get("fhirVersion", "")),
            "software": f"{software.get('name', '')} {software.get('version', '')}".strip(),
        },
    )


def model_facts(summarizer: Summarizer, timeout_seconds: float) -> dict[str, str]:
    """Ollama's version; whether the default model is pulled and loaded, with its digest; and
    which of the allowed models a caller may pick are not pulled."""
    client = summarizer.client
    assert client is not None
    version = client.get_json("/api/version", timeout_seconds).get("version", "")
    pulled = {m["name"]: m for m in client.get_json("/api/tags", timeout_seconds).get("models", [])}
    loaded = {m["name"] for m in client.get_json("/api/ps", timeout_seconds).get("models", [])}
    found = pulled.get(summarizer.model)
    return {
        "ollama_version": str(version),
        "model": summarizer.model,
        "pulled": "yes" if found else "no",
        "digest": (found or {}).get("digest", "")[:12],
        "loaded_in_memory": "yes" if summarizer.model in loaded else "no",
        "allowed_models": ", ".join(summarizer.models),
        "allowed_not_pulled": ", ".join(m for m in summarizer.models if m not in pulled),
    }


def probe_summary_model(summarizer: Summarizer, timeout_seconds: float) -> ComponentCheck:
    """Check that Ollama answers and holds the configured summary model."""
    if summarizer.client is None:
        return ComponentCheck(
            component=Component.SUMMARY_MODEL,
            state=HealthState.DEGRADED,
            required=False,
            detail="OLLAMA_URL is not set; every summary uses the template",
            facts={"model": summarizer.model},
        )
    started = time.perf_counter()
    try:
        facts = model_facts(summarizer, timeout_seconds)
    except (httpx.HTTPError, ValueError) as exc:
        return ComponentCheck(
            component=Component.SUMMARY_MODEL,
            state=HealthState.DEGRADED,
            required=False,
            latency_ms=elapsed_ms(started),
            detail=f"Ollama unreachable ({type(exc).__name__}); summaries use the template",
            facts={"model": summarizer.model},
        )
    if facts["pulled"] != "yes":
        state = HealthState.DEGRADED
        detail = "model not pulled; summaries fall back to the template"
    elif facts["allowed_not_pulled"]:
        state = HealthState.DEGRADED
        detail = "an allowed model is not pulled; picking it falls back to the template"
    else:
        state, detail = HealthState.UP, "every allowed model pulled"
    return ComponentCheck(
        component=Component.SUMMARY_MODEL,
        state=state,
        required=False,
        latency_ms=elapsed_ms(started),
        detail=detail,
        facts=facts,
    )


def probe_audit_log(audit: AuditLog, verify: bool) -> ComponentCheck:
    """Check the audit database accepts writes and, when `verify`, that its chain is intact."""
    started = time.perf_counter()
    if not audit.writable():
        return ComponentCheck(
            component=Component.AUDIT_LOG,
            state=HealthState.DOWN,
            required=True,
            latency_ms=elapsed_ms(started),
            detail="audit database is not writable",
        )
    if not verify:
        return ComponentCheck(
            component=Component.AUDIT_LOG,
            state=HealthState.UP,
            required=True,
            latency_ms=elapsed_ms(started),
            detail="writable",
        )
    chain = audit.verify()
    return ComponentCheck(
        component=Component.AUDIT_LOG,
        state=HealthState.UP if chain.valid else HealthState.DOWN,
        required=True,
        latency_ms=elapsed_ms(started),
        detail="writable; hash chain intact"
        if chain.valid
        else f"hash chain broken at seq {chain.broken_at_seq}",
        facts={"rows_checked": str(chain.checked)},
    )


def probe_policy(policy: Policy, path: Path) -> ComponentCheck:
    """Report the loaded policy, and flag a file on disk that changed since it was loaded."""
    loaded = policy.source.sha256
    facts = {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "sha256": loaded,
    }
    if not path.is_file():
        state, detail = (
            HealthState.DEGRADED,
            "policy file is gone from disk; the loaded copy serves",
        )
    elif file_sha256(path) != loaded:
        state, detail = HealthState.DEGRADED, "policy file changed since start; restart to load it"
    else:
        state, detail = HealthState.UP, "loaded copy matches the file on disk"
    return ComponentCheck(
        component=Component.POLICY, state=state, required=True, detail=detail, facts=facts
    )


def probe_request_store(dirs: tuple[Path, ...]) -> ComponentCheck:
    """Check the request form directories exist and count the forms they hold."""
    present = [d for d in dirs if d.is_dir()]
    count = count_request_files(present)
    return ComponentCheck(
        component=Component.REQUEST_STORE,
        state=HealthState.UP if present else HealthState.DOWN,
        required=True,
        detail=f"{count} request forms in {len(present)} of {len(dirs)} directories",
        facts={"forms": str(count)},
    )


def probe_mcp(url: str, timeout_seconds: float) -> ComponentCheck:
    """GET the MCP server's health route."""
    started = time.perf_counter()
    try:
        ok = httpx.get(url, timeout=timeout_seconds).status_code == 200
        detail = "health route answered" if ok else "health route did not return 200"
    except httpx.HTTPError as exc:
        ok, detail = False, f"unreachable ({type(exc).__name__})"
    return ComponentCheck(
        component=Component.MCP,
        state=HealthState.UP if ok else HealthState.DEGRADED,
        required=False,
        latency_ms=elapsed_ms(started),
        detail=detail,
    )


@dataclass(frozen=True)
class HealthProbes:
    """Everything the probes need, bound once at startup."""

    fhir: FhirClient
    summarizer: Summarizer
    audit: AuditLog
    policy: Policy
    policy_path: Path
    request_dirs: tuple[Path, ...]
    timeout_seconds: float
    mcp_health_url: str | None
    started_monotonic: float

    def readiness(self) -> list[ComponentCheck]:
        """The cheap checks behind GET /ready: the required components only."""
        return [
            probe_fhir(self.fhir, self.timeout_seconds),
            probe_audit_log(self.audit, verify=False),
            probe_policy(self.policy, self.policy_path),
            probe_request_store(self.request_dirs),
        ]

    def details(self) -> HealthReport:
        """Every check, including the model, the MCP server, and a full audit chain verify."""
        checks = [
            probe_fhir(self.fhir, self.timeout_seconds),
            probe_audit_log(self.audit, verify=True),
            probe_policy(self.policy, self.policy_path),
            probe_request_store(self.request_dirs),
            probe_summary_model(self.summarizer, self.timeout_seconds),
        ]
        if self.mcp_health_url:
            checks.append(probe_mcp(self.mcp_health_url, self.timeout_seconds))
        return HealthReport(
            state=overall_state(checks),
            checked_at=datetime.now(UTC),
            uptime_seconds=round(time.monotonic() - self.started_monotonic, 1),
            components=checks,
        )
