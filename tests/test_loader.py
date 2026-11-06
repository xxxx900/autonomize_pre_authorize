import json

from scripts.load_fhir import bundle_paths, to_idempotent_bundle

PATIENT = "11111111-1111-1111-1111-111111111111"
CONDITION = "22222222-2222-2222-2222-222222222222"
PRACTITIONER = "33333333-3333-3333-3333-333333333333"


def synthea_bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "fullUrl": f"urn:uuid:{PRACTITIONER}",
                "resource": {"resourceType": "Practitioner"},
                "request": {
                    "method": "POST",
                    "url": "Practitioner",
                    "ifNoneExist": "identifier=http://hl7.org/fhir/sid/us-npi|999",
                },
            },
            {
                "fullUrl": f"urn:uuid:{PATIENT}",
                "resource": {"resourceType": "Patient"},
                "request": {"method": "POST", "url": "Patient"},
            },
            {
                "fullUrl": f"urn:uuid:{CONDITION}",
                "resource": {
                    "resourceType": "Condition",
                    "subject": {"reference": f"urn:uuid:{PATIENT}"},
                    "recorder": {
                        "reference": "Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|999"
                    },
                    "evidence": [{"detail": [{"reference": "Observation/already-relative"}]}],
                },
                "request": {"method": "POST", "url": "Condition"},
            },
        ],
    }


def test_post_entries_become_puts_with_stable_ids():
    out = to_idempotent_bundle(synthea_bundle())
    assert [(e["request"]["method"], e["request"]["url"]) for e in out["entry"]] == [
        ("PUT", f"Practitioner/{PRACTITIONER}"),
        ("PUT", f"Patient/{PATIENT}"),
        ("PUT", f"Condition/{CONDITION}"),
    ]
    assert [e["resource"]["id"] for e in out["entry"]] == [PRACTITIONER, PATIENT, CONDITION]


def test_references_point_at_the_rewritten_ids():
    condition = to_idempotent_bundle(synthea_bundle())["entry"][2]["resource"]
    assert condition["subject"]["reference"] == f"Patient/{PATIENT}"
    assert condition["recorder"]["reference"] == f"Practitioner/{PRACTITIONER}"
    assert condition["evidence"][0]["detail"][0]["reference"] == "Observation/already-relative"
    assert "urn:uuid" not in json.dumps(condition)


def test_rewrite_is_deterministic_and_leaves_input_untouched():
    bundle = synthea_bundle()
    before = json.dumps(bundle)
    assert to_idempotent_bundle(bundle) == to_idempotent_bundle(bundle)
    assert json.dumps(bundle) == before


def test_already_idempotent_bundle_is_unchanged(resources_dir):
    for path in bundle_paths(resources_dir):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        assert to_idempotent_bundle(bundle) == bundle
