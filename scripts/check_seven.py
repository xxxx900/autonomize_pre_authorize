"""Asserts the plan section 5 outcomes for the seven supplied requests over HTTP.

Doubles as the eval smoke: exits non-zero on any mismatch. Reads API_URL and NURSE_TOKEN.
"""

import os
import sys

import httpx

MET, NOT_MET, MISSING, CONFLICTING = "met", "not_met", "missing", "conflicting"
COMPLETE, REVIEW = "evidence_complete", "clinician_review"

EXPECTED: dict[str, tuple[dict[str, str], str]] = {
    "PA-001": ({"C1": MET, "C2": MET, "C3": MET, "C4": MET, "C5": MET}, COMPLETE),
    "PA-002": ({"C1": MET, "C2": MISSING, "C3": MET, "C4": MET, "C5": MET}, REVIEW),
    "PA-003": ({"C1": MET, "C2": MET, "C3": NOT_MET, "C4": MET, "C5": MET}, REVIEW),
    "PA-004": ({"C1": MET, "C2": MET, "C3": CONFLICTING, "C4": MET, "C5": MET}, REVIEW),
    "PA-005": ({"C1": MET, "C2": MET, "C3": MET, "C4": NOT_MET, "C5": MET}, REVIEW),
    "PA-006": ({"C1": MET, "C2": CONFLICTING, "C3": MET, "C4": MET, "C5": MET}, REVIEW),
    "PA-007": ({"C1": NOT_MET, "C2": MET, "C3": MET, "C4": MET, "C5": MET}, REVIEW),
}


def main() -> int:
    """Fetch each supplied request and compare statuses and route with the plan."""
    base = os.environ.get("API_URL", "http://localhost:8000")
    headers = {"Authorization": f"Bearer {os.environ['NURSE_TOKEN']}"}
    failures = 0
    for request_id, (statuses, route) in EXPECTED.items():
        response = httpx.get(f"{base}/requests/{request_id}/evidence", headers=headers, timeout=30)
        if response.status_code != 200:
            sys.stdout.write(f"FAIL {request_id} http {response.status_code}\n")
            failures += 1
            continue
        packet = response.json()
        got = {c["id"]: c["status"] for c in packet["criteria"]}
        ok = got == statuses and packet["route"] == route
        failures += not ok
        sys.stdout.write(f"{'ok  ' if ok else 'FAIL'} {request_id} {got} route={packet['route']}\n")
    sys.stdout.write(f"{len(EXPECTED) - failures}/{len(EXPECTED)} match plan section 5\n")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
