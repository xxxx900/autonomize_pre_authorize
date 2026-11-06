"""Print the raw facts the hand audit reads, straight from the Synthea bundle files.

Imports nothing from app/, so the hand audit does not inherit the engine's parsing.
Run: docker compose -p <project> run --rm --no-deps api python -m eval.audit_facts
"""

import json
import sys
from pathlib import Path

SYNTHEA = Path(__file__).resolve().parent.parent / "resources" / "synthea"
REQUESTS = Path(__file__).resolve().parent / "synthea_requests"
WATCH_CONDITION_WORDS = ("diabet", "pancrea", "thyroid", "neoplasia", "kidney", "renal")
HBA1C, EGFR = "4548-4", "33914-3"


def codes(concept: dict | None) -> list[dict]:
    return (concept or {}).get("coding", [])


def status(resource: dict) -> str:
    found = codes(resource.get("clinicalStatus"))
    return found[0].get("code", "") if found else ""


def facts(bundle: dict) -> dict:
    resources = [e["resource"] for e in bundle["entry"]]
    patient = next(r for r in resources if r["resourceType"] == "Patient")

    def of(kind: str) -> list[dict]:
        return [r for r in resources if r["resourceType"] == kind]

    def observations(loinc: str) -> list[tuple]:
        return sorted(
            (
                r.get("effectiveDateTime", "")[:10],
                (r.get("valueQuantity") or {}).get("value"),
                f"Observation/{r['id']}",
            )
            for r in of("Observation")
            if any(c.get("code") == loinc for c in codes(r.get("code")))
        )

    return {
        "patient": f"Patient/{patient['id']}",
        "birthDate": patient.get("birthDate"),
        "deceasedDateTime": patient.get("deceasedDateTime"),
        "conditions": sorted(
            (
                r.get("onsetDateTime", "")[:10],
                c.get("system", "").rsplit("/", 1)[-1],
                c.get("code"),
                c.get("display"),
                status(r),
                f"Condition/{r['id']}",
            )
            for r in of("Condition")
            for c in codes(r.get("code"))
            if any(w in c.get("display", "").lower() for w in WATCH_CONDITION_WORDS)
        ),
        "hba1c": observations(HBA1C),
        "egfr": observations(EGFR)[-3:],
        "metformin_requests": sorted(
            (
                r.get("authoredOn", "")[:10],
                r.get("status"),
                [c.get("code") for c in codes(r.get("medicationCodeableConcept"))],
                ((r.get("dispenseRequest") or {}).get("validityPeriod") or {}).get("end"),
                f"MedicationRequest/{r['id']}",
            )
            for r in of("MedicationRequest")
            if "metformin" in json.dumps(r.get("medicationCodeableConcept", {})).lower()
        ),
        "medication_requests_with_validity_period": sum(
            1
            for r in of("MedicationRequest")
            if (r.get("dispenseRequest") or {}).get("validityPeriod")
        ),
        "allergies": [
            (status(r), [c.get("code") for c in codes(r.get("code"))], f"AllergyIntolerance/{r['id']}")
            for r in of("AllergyIntolerance")
        ],
    }


def main() -> int:
    by_patient = {
        json.loads(p.read_text("utf-8"))["member"]["patient_id"]: p.stem
        for p in sorted(REQUESTS.glob("*.json"))
    }
    for path in sorted(SYNTHEA.glob("*.json")):
        bundle = json.loads(path.read_text("utf-8"))
        if not any(e["resource"]["resourceType"] == "Patient" for e in bundle["entry"]):
            continue
        found = facts(bundle)
        request = by_patient.get(found["patient"].split("/", 1)[1], "no request")
        sys.stdout.write(f"## {request} {path.name}\n{json.dumps(found, indent=1)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
