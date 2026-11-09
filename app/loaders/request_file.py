"""Find and parse request form JSON files."""

import json
import re
from collections.abc import Iterable
from pathlib import Path

from app.domain.request_form import RequestForm

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def parse_request_form(raw: dict) -> RequestForm:
    """Map the submitted form's JSON layout onto a RequestForm."""
    return RequestForm(
        request_id=raw["request_id"],
        request_date=raw["request_date"],
        policy_id=raw["policy_id"],
        patient_id=raw["member"]["patient_id"],
        requested_medication=raw["requested_medication"]["rxnorm"],
        diagnosis_claimed=raw["diagnosis_claimed"]["snomed"],
        attestation=raw.get("prescriber_attestation", {}),
    )


def find_request_file(request_id: str, dirs: Iterable[Path]) -> Path:
    """Return the first `<request_id>.json` in the given directories.

    Raises FileNotFoundError for an id that is malformed (so it cannot escape the directory)
    or that no directory holds.
    """
    if not REQUEST_ID_PATTERN.match(request_id):
        raise FileNotFoundError(request_id)
    path = next((p for d in dirs if (p := d / f"{request_id}.json").is_file()), None)
    if path is None:
        raise FileNotFoundError(request_id)
    return path


def load_request_form(request_id: str, dirs: Iterable[Path]) -> RequestForm:
    """Find a request file by id and parse it."""
    path = find_request_file(request_id, dirs)
    return parse_request_form(json.loads(path.read_text(encoding="utf-8")))


def list_request_ids(dirs: Iterable[Path]) -> list[str]:
    """Every request id the service can serve, sorted, for the worksheet's request picker."""
    return sorted({p.stem for d in dirs if d.is_dir() for p in d.glob("*.json")})


def count_request_files(dirs: Iterable[Path]) -> int:
    """Count the request forms the service can serve, for the health report."""
    return sum(len(list(d.glob("*.json"))) for d in dirs if d.is_dir())
