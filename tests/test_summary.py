import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.fhir_client import FhirClient
from app.main import create_app
from app.packet import SummarySource
from app.safety import faithfulness_problems, forbidden_words
from app.summary import PROMPT_VERSION, Summarizer, SummaryOutput, template_summary
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


def chat_reply(content: str):
    def handler(request):
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    return handler


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


def test_prompt_sends_only_packet_facts_and_the_schema():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return chat_reply(json.dumps(GOOD))(request)

    summarizer_replying(handler)(PA002)
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


def test_pa006_packet_and_prompt_carry_nothing_from_the_injected_text(settings):
    prompts = []

    def handler(request):
        prompts.append(request.content.decode())
        return httpx.Response(500)

    fhir = FhirClient(settings, fake_fhir_transport(bundle_resources("PA-006")))
    app = create_app(settings, fhir, summarizer_replying(handler))
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
