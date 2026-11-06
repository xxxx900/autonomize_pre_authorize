"""Measure candidate summary models on the seven packets. Runs inside the compose network."""

import json
import os
import statistics
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.packet import EvidencePacket
from app.policy import load_policy
from app.record import RequestForm, record_from_resources
from app.rules import evaluate
from app.safety import faithfulness_problems, forbidden_words
from app.summary import PROMPT_VERSION, Summarizer, SummaryOutput

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "resources"
RESULTS = Path(__file__).resolve().parent / "results"
REQUEST_IDS = [f"PA-00{i}" for i in range(1, 8)]
TIMEOUT_SECONDS = 180.0


def packets() -> list[EvidencePacket]:
    policy = load_policy(RESOURCES / "policy_MP-SYN-021.json")
    out = []
    for rid in REQUEST_IDS:
        bundle = json.loads((RESOURCES / "bundles" / f"{rid}.json").read_text("utf-8"))
        form = json.loads((RESOURCES / "requests" / f"{rid}.json").read_text("utf-8"))
        record = record_from_resources([e["resource"] for e in bundle["entry"]])
        out.append(evaluate(record, RequestForm.from_json(form), policy))
    return out


def one_run(summarizer: Summarizer, packet: EvidencePacket) -> dict:
    started = time.perf_counter()
    try:
        raw = summarizer.ask(packet)
    except (httpx.HTTPError, ValueError) as exc:
        return {"latency_s": time.perf_counter() - started, "error": type(exc).__name__}
    latency = time.perf_counter() - started
    try:
        text = SummaryOutput.model_validate_json(raw).text
    except ValidationError:
        return {"latency_s": latency, "schema_valid": False, "raw": raw[:200]}
    return {
        "latency_s": latency,
        "schema_valid": True,
        "faithfulness_problems": faithfulness_problems(text, packet),
        "forbidden": forbidden_words(text),
        "text": text,
    }


def summarize_model(model: str, url: str, runs: int, items: list[EvidencePacket]) -> dict:
    summarizer = Summarizer(url, model, TIMEOUT_SECONDS)
    one_run(summarizer, items[0])
    results = [
        {"request_id": p.request_id, "run": i + 1, **one_run(summarizer, p)}
        for p in items
        for i in range(runs)
    ]
    summarizer.close()
    n = len(results)
    valid = [r for r in results if r.get("schema_valid")]
    faithful = [r for r in valid if not r["faithfulness_problems"]]
    return {
        "model": model,
        "n": n,
        "schema_valid_rate": len(valid) / n,
        "faithful_rate": len(faithful) / n,
        "forbidden_word_hits": sum(len(r["forbidden"]) for r in valid),
        "accepted_rate": sum(1 for r in faithful if not r["forbidden"]) / n,
        "median_latency_s": round(statistics.median(r["latency_s"] for r in results), 2),
        "failures": [
            r for r in results if not r.get("schema_valid") or r.get("faithfulness_problems")
        ][:12],
        "results": results,
    }


def digest(url: str, model: str) -> str | None:
    tags = httpx.get(f"{url}/api/tags", timeout=30).json()["models"]
    return next((t["digest"][:12] for t in tags if t["name"] == model), None)


def markdown(report: dict) -> str:
    lines = [
        f"Prompt `{report['prompt_version']}`, {report['runs']} runs x {len(REQUEST_IDS)} packets, "
        "temperature 0, CPU, one warm-up call per model not counted.",
        "",
        "| Model | Digest | Valid schema | Faithful | Forbidden hits | Accepted | Median latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in report["models"]:
        lines.append(
            f"| `{m['model']}` | `{m['digest']}` | {m['schema_valid_rate']:.0%} | "
            f"{m['faithful_rate']:.0%} | {m['forbidden_word_hits']} | {m['accepted_rate']:.0%} | "
            f"{m['median_latency_s']} s |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    url = os.environ["OLLAMA_URL"]
    runs = int(os.environ.get("MEASURE_RUNS", "5"))
    stem = os.environ.get("MEASURE_OUTPUT", "models")
    models = os.environ["MEASURE_MODELS"].split()
    items = packets()
    report = {"prompt_version": PROMPT_VERSION, "runs": runs, "models": []}
    for model in models:
        result = summarize_model(model, url, runs, items)
        result["digest"] = digest(url, model)
        report["models"].append(result)
        print(markdown({**report, "models": [result]}).splitlines()[-1], flush=True)
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
        (RESULTS / f"{stem}.md").write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
