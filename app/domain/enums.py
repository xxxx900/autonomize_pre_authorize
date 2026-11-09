"""Every closed set of values the service uses, in one place."""

from enum import StrEnum


class Status(StrEnum):
    """The finding for one policy criterion. The policy file defines each meaning."""

    MET = "met"
    NOT_MET = "not_met"
    MISSING = "missing"
    CONFLICTING = "conflicting"


class Route(StrEnum):
    """Where a packet goes next. The service never approves or denies."""

    EVIDENCE_COMPLETE = "evidence_complete"
    CLINICIAN_REVIEW = "clinician_review"


class CriterionId(StrEnum):
    """The five criteria of policy MP-SYN-021."""

    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"


class SummarySource(StrEnum):
    """Who wrote the packet summary: the language model or the fixed template."""

    MODEL = "model"
    TEMPLATE = "template"


class SummaryFallback(StrEnum):
    """Why the template summary replaced the model summary."""

    NOT_CONFIGURED = "not_configured"
    UNREACHABLE = "unreachable"
    MODEL_ERROR = "model_error"
    BAD_OUTPUT = "bad_output"
    REJECTED = "rejected"


class ResourceType(StrEnum):
    """The FHIR R4 resource types the service reads."""

    PATIENT = "Patient"
    CONDITION = "Condition"
    OBSERVATION = "Observation"
    MEDICATION_REQUEST = "MedicationRequest"
    ALLERGY_INTOLERANCE = "AllergyIntolerance"
    DOCUMENT_REFERENCE = "DocumentReference"


class FhirAuthMode(StrEnum):
    """How the service authenticates to the FHIR server."""

    NONE = "none"
    BEARER = "bearer"
    SMART = "smart"


class Role(StrEnum):
    """The roles a bearer token can map to."""

    NURSE = "nurse"
    ADMIN = "admin"


class AuditAction(StrEnum):
    """What a caller, or the service itself, did. One audit row per action."""

    EVIDENCE_READ = "evidence.read"
    POLICY_READ = "policy.read"
    AUDIT_READ = "audit.read"
    HEALTH_READ = "health.read"
    CATALOG_READ = "catalog.read"
    MCP_REQUEST = "mcp.request"
    SERVICE_START = "service.start"


class Outcome(StrEnum):
    """How an audited action ended."""

    OK = "ok"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    ERROR = "error"


class HealthState(StrEnum):
    """The state of one component, or of the service as a whole."""

    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"


class Component(StrEnum):
    """The parts of the stack a health check probes."""

    FHIR = "fhir"
    SUMMARY_MODEL = "summary_model"
    AUDIT_LOG = "audit_log"
    POLICY = "policy"
    REQUEST_STORE = "request_store"
    MCP = "mcp"
