"""Run the 7 supplied and 10 Synthea requests through the live endpoint and compare statuses.

Expected statuses: plan section 5 for PA-001 to PA-007, the hand audit in
eval/synthea_expected.json for SYN-001 to SYN-010. Writes eval/results/eval.json and eval.md.

Two checks run outside the API, so they do not rely on the API's word: every cited source is
fetched directly from FHIR, and the served summary is re-checked for forbidden words and for
any fact not in the packet. Reads API_URL, NURSE_TOKEN, and FHIR_BASE_URL.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

from app.domain.packet import EvidencePacket
from app.summary.safety import cited_sources, faithfulness_problems, forbidden_words
from scripts.check_seven import EXPECTED as PLAN_EXPECTED

EVAL_DIR = Path(__file__).resolve().parent
RESULTS = EVAL_DIR / "results"
CRITERIA = ("C1", "C2", "C3", "C4", "C5")
TIMEOUT_SECONDS = 120.0


def expected_statuses() -> dict[str, dict[str, str]]:
    """Expected status per criterion for every request, from the plan and the hand audit."""
    audit = json.loads((EVAL_DIR / "synthea_expected.json").read_text("utf-8"))["requests"]
    expected = {rid: dict(statuses) for rid, (statuses, _) in PLAN_EXPECTED.items()}
    expected |= {rid: {cid: s for cid, (s, _) in crit.items()} for rid, crit in audit.items()}
    return expected


def sources_resolved(fhir: httpx.Client, packet: EvidencePacket) -> dict[str, int]:
    """GET every resource the packet cites straight from FHIR and count the ones that answer."""
    refs = cited_sources(packet)
    found = sum(fhir.get(f"/{r.resource_type}/{r.id}").status_code == 200 for r in refs)
    return {"resolved": found, "cited": len(refs)}


def summary_problems(packet: EvidencePacket) -> list[str]:
    """Forbidden words and unfaithful facts in the served summary; empty means faithful."""
    text = packet.summary or ""
    return [f"forbidden word: {w}" for w in forbidden_words(text)] + faithfulness_problems(
        text, packet
    )


def run_one(client: httpx.Client, fhir: httpx.Client, request_id: str) -> dict:
    """Fetch one packet from the live API, then check its sources and summary independently."""
    started = time.perf_counter()
    response = client.get(f"/requests/{request_id}/evidence")
    latency = round(time.perf_counter() - started, 2)
    if response.status_code != 200:
        return {"request_id": request_id, "http": response.status_code, "latency_s": latency}
    packet = response.json()
    parsed = EvidencePacket.model_validate(packet)
    return {
        "request_id": request_id,
        "http": 200,
        "latency_s": latency,
        "statuses": {c["id"]: c["status"] for c in packet["criteria"]},
        "sources": {
            c["id"]: [f"{s['resource_type']}/{s['id']}" for s in c["sources"]]
            for c in packet["criteria"]
        },
        "rationales": {c["id"]: c["rationale"] for c in packet["criteria"]},
        "route": packet["route"],
        "summary_source": packet["summary_source"],
        "summary_problems": summary_problems(parsed),
        "sources_check": sources_resolved(fhir, parsed),
        "flagged_documents": len(packet["flagged_documents"]),
    }


def mismatches(row: dict, expected: dict[str, str]) -> list[str]:
    """Each criterion where the engine disagrees with the expected status."""
    if row["http"] != 200:
        return [f"http {row['http']}"]
    return [
        f"{cid} engine {row['statuses'][cid]}, expected {expected[cid]}"
        for cid in CRITERIA
        if row["statuses"][cid] != expected[cid]
    ]


def markdown(rows: list[dict], expected: dict[str, dict[str, str]]) -> str:
    """Render the eval results as a Markdown table."""
    lines = [
        "Engine status per criterion. A cell reads `engine (expected X)` where the engine "
        "disagrees with the expected status.",
        "",
        "`Sources resolve` counts cited resources fetched directly from FHIR. `Faithful` re-runs "
        "the forbidden-word and faithfulness checks on the served summary.",
        "",
        "| Request | " + " | ".join(CRITERIA) + " | Route | Sources resolve | Summary | Faithful"
        " | Flagged docs | Latency |",
        "|---|" + "---|" * (len(CRITERIA) + 6),
    ]
    agree = dict.fromkeys(CRITERIA, 0)
    for row in rows:
        want = expected[row["request_id"]]
        if row["http"] != 200:
            lines.append(
                f"| {row['request_id']} | http {row['http']} |" + " |" * (len(CRITERIA) + 5)
            )
            continue
        cells = []
        for cid in CRITERIA:
            got = row["statuses"][cid]
            agree[cid] += got == want[cid]
            cells.append(got if got == want[cid] else f"**{got}** (expected {want[cid]})")
        sources = row["sources_check"]
        faithful = "yes" if not row["summary_problems"] else "; ".join(row["summary_problems"])
        lines.append(
            f"| {row['request_id']} | " + " | ".join(cells) + f" | {row['route']} | "
            f"{sources['resolved']}/{sources['cited']} | {row['summary_source']} | {faithful} | "
            f"{row['flagged_documents']} | {row['latency_s']} s |"
        )
    lines.append(
        "| Agreement | "
        + " | ".join(f"{agree[c]}/{len(rows)}" for c in CRITERIA)
        + " | | | | | | |"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run every request, write eval.json and eval.md, and exit non-zero on any mismatch."""
    base = os.environ.get("API_URL", "http://localhost:8000")
    headers = {"Authorization": f"Bearer {os.environ['NURSE_TOKEN']}"}
    fhir_base = os.environ.get("FHIR_BASE_URL", "http://localhost:8080/fhir")
    expected = expected_statuses()
    with (
        httpx.Client(base_url=base, headers=headers, timeout=TIMEOUT_SECONDS) as client,
        httpx.Client(base_url=fhir_base, timeout=TIMEOUT_SECONDS) as fhir,
    ):
        rows = [run_one(client, fhir, rid) for rid in expected]
    for row in rows:
        row["mismatches"] = mismatches(row, expected[row["request_id"]])
        sys.stdout.write(f"{row['request_id']} {row.get('statuses')} {row['mismatches']}\n")
    RESULTS.mkdir(exist_ok=True)
    report = {"api_url": base, "expected": expected, "results": rows}
    (RESULTS / "eval.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "eval.md").write_text(markdown(rows, expected), encoding="utf-8")
    disagreeing = sum(1 for r in rows if r["mismatches"])
    sys.stdout.write(f"{len(rows) - disagreeing}/{len(rows)} requests match expected statuses\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
