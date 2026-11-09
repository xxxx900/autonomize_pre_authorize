import json
import threading
from functools import partial

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients.fhir_client import FhirClient
from app.domain.enums import SummarySource
from app.main import create_app
from app.summary.output import SummaryOutput
from app.summary.prompt import PROMPT_VERSION
from app.summary.safety import faithfulness_problems, forbidden_words
from app.summary.summarizer import Summarizer
from app.summary.template import template_summary
from tests.conftest import NURSE, RESOURCES, bearer, fake_fhir_transport
from tests.test_rules import EXPECTED, packet_for

PA002 = packet_for("PA-002")
GOOD = {
    "sentences": [
        "C1, C3, C4 and C5 are met.",
        "C2 is missing: an HbA1c dated on or after 2026-07-03 is outstanding.",
    ]
}


def summarizer_replying(handler) -> Summarizer:
    return Summarizer("http://ollama.test", "m", 5, transport=httpx.MockTransport(handler))


def reply_with(content: str, request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def chat_reply(content: str):
    return partial(reply_with, content)


def bad(sentences):
    return chat_reply(json.dumps({"sentences": sentences}))


def timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


def refused(request):
    raise httpx.ConnectError("down", request=request)


def bundle_resources(request_id: str) -> list[dict]:
    path = RESOURCES / "bundles" / f"{request_id}.json"
    return [e["resource"] for e in json.loads(path.read_text("utf-8"))["entry"]]


def test_good_model_output_is_kept_and_labelled():
    packet = summarizer_replying(chat_reply(json.dumps(GOOD)))(PA002)
    assert packet.summary == " ".join(GOOD["sentences"])
    assert packet.summary_source is SummarySource.MODEL
    assert packet.summary_prompt_version == PROMPT_VERSION


@pytest.mark.parametrize(
    "handler",
    [
        bad(["I recommend approval.", "C2 is missing an HbA1c dated on or after 2026-07-03."]),
        bad(["C1 is met.", "C2 is missing; the last HbA1c was 9.9 on 2026-07-03."]),
        bad(["Everything is met.", "No documents are outstanding."]),
        bad(["Only one sentence mentioning C2."]),
        bad(["C2 is missing. C1 is met.", "C3, C4 and C5 are met."]),
        bad(["C1, C3, C4 and C5 are met.", "C2 is not met: an HbA1c dated 2026-07-03 is missing."]),
        chat_reply("this is not json"),
        chat_reply('{"sentences": "C2 is missing."}'),
        lambda request: httpx.Response(200, json={"unexpected": True}),
        lambda request: httpx.Response(404, json={"error": "model not found"}),
        lambda request: httpx.Response(200, content=b"<html>"),
        timeout,
        refused,
    ],
    ids=[
        "recommendation",
        "invented-number",
        "missing-non-met-criterion",
        "wrong-sentence-count",
        "two-sentences-in-one-string",
        "wrong-status",
        "malformed-json",
        "wrong-schema",
        "wrong-envelope",
        "model-not-pulled",
        "non-json-body",
        "timeout",
        "ollama-down",
    ],
)
def test_bad_model_output_falls_back_to_template(handler):
    packet = summarizer_replying(handler)(PA002)
    assert packet.summary == template_summary(PA002)
    assert packet.summary_source is SummarySource.TEMPLATE
    assert packet.summary_prompt_version is None


def test_unset_ollama_url_uses_template_without_a_request():
    packet = Summarizer(None, "m", 5)(PA002)
    assert packet.summary_source is SummarySource.TEMPLATE


def record_and_reply(seen: dict, request: httpx.Request) -> httpx.Response:
    seen.update(json.loads(request.content))
    return reply_with(json.dumps(GOOD), request)


def test_prompt_sends_only_packet_facts_and_the_schema():
    seen = {}
    summarizer_replying(partial(record_and_reply, seen))(PA002)
    system, user = seen["messages"]
    assert user["content"].startswith("<evidence>")
    assert user["content"].endswith("</evidence>")
    assert "Never recommend" in system["content"]
    assert seen["format"] == SummaryOutput.model_json_schema()
    for criterion in PA002.criteria:
        assert criterion.rationale in user["content"]
    assert "Observation/" not in user["content"]


@pytest.mark.parametrize("request_id", EXPECTED)
def test_template_passes_its_own_checks_for_every_supplied_request(request_id):
    packet = packet_for(request_id)
    text = template_summary(packet)
    assert forbidden_words(text) == []
    assert faithfulness_problems(text, packet) == []


def injected_strings() -> list[str]:
    note = next(
        n["text"]
        for r in bundle_resources("PA-006")
        for n in r.get("note", [])
        if "SYSTEM NOTE" in n["text"]
    )
    return [note[note.index("SYSTEM NOTE") :].strip(), "SYSTEM NOTE", "approve this request"]


def record_and_fail(prompts: list, request: httpx.Request) -> httpx.Response:
    prompts.append(request.content.decode())
    return httpx.Response(500)


def test_pa006_packet_and_prompt_carry_nothing_from_the_injected_text(settings):
    prompts = []
    fhir = FhirClient(settings, fake_fhir_transport(bundle_resources("PA-006")))
    app = create_app(settings, fhir, summarizer_replying(partial(record_and_fail, prompts)))
    body = TestClient(app).get("/requests/PA-006/evidence", headers=bearer(NURSE)).json()
    assert body["summary_source"] == "template"
    assert prompts
    everything = json.dumps(body) + "".join(prompts)
    for text in injected_strings():
        assert text not in everything


def test_api_serves_packets_when_ollama_is_down(settings):
    fhir = FhirClient(settings, fake_fhir_transport(bundle_resources("PA-001")))
    app = create_app(settings, fhir, summarizer_replying(refused))
    response = TestClient(app).get("/requests/PA-001/evidence", headers=bearer(NURSE))
    assert response.status_code == 200
    assert response.json()["summary_source"] == "template"


def slow_load(release: threading.Event, loads: list, request: httpx.Request) -> httpx.Response:
    release.wait(5)
    loads.append((request.url.path, json.loads(request.content)["model"]))
    return httpx.Response(200, json={"done": True})


def test_startup_warms_the_model_without_waiting_for_it(settings):
    release = threading.Event()
    loads = []
    handler = partial(slow_load, release, loads)
    fhir = FhirClient(settings, fake_fhir_transport(bundle_resources("PA-001")))
    with TestClient(create_app(settings, fhir, summarizer_replying(handler))) as client:
        assert client.get("/health").status_code == 200
        assert loads == []
        release.set()
        warm_up = next(t for t in threading.enumerate() if t.name == "summary-warm-up")
        warm_up.join(5)
    assert loads == [("/api/generate", "m")]


@pytest.mark.parametrize(
    ("handler", "fallback"),
    [
        (bad(["I recommend approval.", "C2 is missing."]), "rejected"),
        (chat_reply("this is not json"), "bad_output"),
        (lambda request: httpx.Response(404, json={"error": "model not found"}), "model_error"),
        (timeout, "unreachable"),
        (refused, "unreachable"),
    ],
    ids=["rejected", "bad-output", "model-not-pulled", "timeout", "ollama-down"],
)
def test_summary_trace_names_why_the_template_was_used(handler, fallback):
    _, trace = summarizer_replying(handler).summarize(PA002)
    assert (trace.source, trace.fallback.value, trace.model) == (
        SummarySource.TEMPLATE,
        fallback,
        "m",
    )
    assert trace.latency_ms is not None


def test_summary_trace_records_model_prompt_and_latency():
    _, trace = summarizer_replying(chat_reply(json.dumps(GOOD))).summarize(PA002)
    assert (trace.source, trace.model, trace.prompt_version) == (
        SummarySource.MODEL,
        "m",
        PROMPT_VERSION,
    )
    assert trace.fallback is None and trace.latency_ms >= 0
