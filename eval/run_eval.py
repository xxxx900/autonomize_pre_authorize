"""Run the 7 supplied and 10 Synthea requests through the live endpoint and compare statuses.

Expected statuses: plan section 5 for PA-001 to PA-007, the hand audit in
eval/synthea_expected.json for SYN-001 to SYN-010. Writes eval/results/eval.json and eval.md.
Reads API_URL and NURSE_TOKEN.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

from scripts.check_seven import EXPECTED as PLAN_EXPECTED

EVAL_DIR = Path(__file__).resolve().parent
RESULTS = EVAL_DIR / "results"
CRITERIA = ("C1", "C2", "C3", "C4", "C5")
TIMEOUT_SECONDS = 120.0


def expected_statuses() -> dict[str, dict[str, str]]:
    audit = json.loads((EVAL_DIR / "synthea_expected.json").read_text("utf-8"))["requests"]
    expected = {rid: dict(statuses) for rid, (statuses, _) in PLAN_EXPECTED.items()}
    expected |= {rid: {cid: s for cid, (s, _) in crit.items()} for rid, crit in audit.items()}
    return expected


def run_one(client: httpx.Client, request_id: str) -> dict:
    started = time.perf_counter()
    response = client.get(f"/requests/{request_id}/evidence")
    latency = round(time.perf_counter() - started, 2)
    if response.status_code != 200:
        return {"request_id": request_id, "http": response.status_code, "latency_s": latency}
    packet = response.json()
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
        "flagged_documents": len(packet["flagged_documents"]),
    }


def mismatches(row: dict, expected: dict[str, str]) -> list[str]:
    if row["http"] != 200:
        return [f"http {row['http']}"]
    return [
        f"{cid} engine {row['statuses'][cid]}, expected {expected[cid]}"
        for cid in CRITERIA
        if row["statuses"][cid] != expected[cid]
    ]


def markdown(rows: list[dict], expected: dict[str, dict[str, str]]) -> str:
    lines = [
        "Engine status per criterion. A cell reads `engine (expected X)` where the engine "
        "disagrees with the expected status.",
        "",
        "| Request | " + " | ".join(CRITERIA) + " | Route | Summary | Flagged docs | Latency |",
        "|---|" + "---|" * (len(CRITERIA) + 4),
    ]
    agree = dict.fromkeys(CRITERIA, 0)
    for row in rows:
        want = expected[row["request_id"]]
        if row["http"] != 200:
            lines.append(
                f"| {row['request_id']} | http {row['http']} |" + " |" * (len(CRITERIA) + 3)
            )
            continue
        cells = []
        for cid in CRITERIA:
            got = row["statuses"][cid]
            agree[cid] += got == want[cid]
            cells.append(got if got == want[cid] else f"**{got}** (expected {want[cid]})")
        lines.append(
            f"| {row['request_id']} | " + " | ".join(cells) + f" | {row['route']} | "
            f"{row['summary_source']} | {row['flagged_documents']} | {row['latency_s']} s |"
        )
    lines.append(
        "| Agreement | " + " | ".join(f"{agree[c]}/{len(rows)}" for c in CRITERIA) + " | | | | |"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    base = os.environ.get("API_URL", "http://localhost:8000")
    headers = {"Authorization": f"Bearer {os.environ['NURSE_TOKEN']}"}
    expected = expected_statuses()
    with httpx.Client(base_url=base, headers=headers, timeout=TIMEOUT_SECONDS) as client:
        rows = [run_one(client, rid) for rid in expected]
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
