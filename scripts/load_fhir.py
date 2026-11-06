import copy
import json
import sys
import time
from pathlib import Path

import httpx

from app.config import REPO_ROOT, FhirSettings
from app.fhir_client import FhirClient

URN_PREFIX = "urn:uuid:"
BUNDLE_DIRS = ("bundles", "synthea")
SHARED_BUNDLE_PREFIXES = ("hospitalInformation", "practitionerInformation")
WAIT_SECONDS = 600
COUNTED_TYPES = (
    "Patient",
    "Condition",
    "Observation",
    "MedicationRequest",
    "AllergyIntolerance",
    "DocumentReference",
)


def _rewrite_references(node, targets: dict[str, str]):
    if isinstance(node, dict):
        return {
            key: targets.get(value, value)
            if key == "reference" and isinstance(value, str)
            else _rewrite_references(value, targets)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_references(item, targets) for item in node]
    return node


def to_idempotent_bundle(bundle: dict) -> dict:
    """Turn POST + urn:uuid entries into PUT Type/<uuid> and repoint references to match."""
    entries = bundle.get("entry", [])
    targets: dict[str, str] = {}
    for entry in entries:
        full_url = entry.get("fullUrl", "")
        resource = entry["resource"]
        if entry["request"]["method"] == "POST" and full_url.startswith(URN_PREFIX):
            target = f"{resource['resourceType']}/{full_url.removeprefix(URN_PREFIX)}"
            targets[full_url] = target
            conditional = entry["request"].get("ifNoneExist")
            if conditional:
                targets[f"{resource['resourceType']}?{conditional}"] = target

    rewritten = []
    for entry in entries:
        resource = copy.deepcopy(entry["resource"])
        target = targets.get(entry.get("fullUrl", ""))
        if target:
            resource["id"] = target.split("/", 1)[1]
            entry = {**entry, "request": {"method": "PUT", "url": target}}
        rewritten.append({**entry, "resource": _rewrite_references(resource, targets)})
    return {**bundle, "entry": rewritten}


def wait_for_fhir(client: FhirClient, seconds: float = WAIT_SECONDS) -> None:
    deadline = time.monotonic() + seconds
    while not client.ping():
        if time.monotonic() > deadline:
            raise TimeoutError(f"FHIR server not ready after {seconds:.0f}s")
        time.sleep(3)


def bundle_paths(resources_dir: Path) -> list[Path]:
    """Synthea shared bundles first: patient bundles resolve Practitioner?identifier= against them."""
    paths = sorted(p for d in BUNDLE_DIRS for p in (resources_dir / d).glob("*.json"))
    return sorted(paths, key=lambda p: not p.name.startswith(SHARED_BUNDLE_PREFIXES))


def load_bundle(client: FhirClient, path: Path) -> int:
    bundle = to_idempotent_bundle(json.loads(path.read_text(encoding="utf-8")))
    response = client.http.post("", json=bundle, timeout=300)
    response.raise_for_status()
    return len(bundle["entry"])


def resource_counts(client: FhirClient) -> dict[str, int]:
    counts = {}
    for resource_type in COUNTED_TYPES:
        response = client.http.get(
            resource_type,
            params={"_summary": "count"},
            headers={"Cache-Control": "no-cache"},
        )
        response.raise_for_status()
        counts[resource_type] = response.json()["total"]
    return counts


def main() -> int:
    settings = FhirSettings()
    client = FhirClient(settings)
    wait_for_fhir(client)
    paths = bundle_paths(REPO_ROOT / "resources")
    for path in paths:
        try:
            entries = load_bundle(client, path)
        except httpx.HTTPError as exc:
            print(f"FAILED {path.name}: {exc}", file=sys.stderr)
            return 1
        print(f"loaded {path.name}: {entries} entries")
    print("counts " + json.dumps(resource_counts(client)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
