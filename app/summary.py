import logging
import time

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.packet import EvidencePacket, Status, SummarySource
from app.safety import evidence_text, faithfulness_problems, forbidden_words, sentence_count

PROMPT_VERSION = "summary-v4"
WARM_UP_TIMEOUT_SECONDS = 300.0

SYSTEM_RULE = (
    "You write a two-sentence factual summary of a prior-authorization evidence packet for a "
    "nurse. Use only the facts between the <evidence> tags. Describe what the evidence shows: "
    "which criteria are met and which are not met, missing or conflicting, and what documents "
    "are outstanding. Name every criterion that is not met by its id, such as C2, and use the "
    "status exactly as given in the evidence; never describe a met criterion as unmet. Each of "
    "the two strings must be exactly one sentence. Never recommend, approve, deny, or say "
    "whether the request should or should not proceed. Never state a number or date that is "
    "not in the evidence. Reply as JSON with a sentences array holding exactly two strings of "
    "plain prose with no brackets. The first string states which criteria have status met. "
    "The second string states each remaining criterion with its exact status word (not_met, "
    "missing or conflicting) and the document or value still outstanding."
)

logger = logging.getLogger("pa.summary")


class SummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentences: list[str] = Field(min_length=2, max_length=2)

    @field_validator("sentences")
    @classmethod
    def _one_sentence_each(cls, value: list[str]) -> list[str]:
        if any(not s.strip() or sentence_count(s) > 1 for s in value):
            raise ValueError("each entry must be one non-empty sentence")
        return value

    @property
    def text(self) -> str:
        return " ".join(s.strip() for s in self.sentences)


class _Message(BaseModel):
    content: str


class _ChatResponse(BaseModel):
    message: _Message


class Rejected(ValueError):
    """Model output parsed but failed a safety or faithfulness check."""


def build_prompt(packet: EvidencePacket) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_RULE},
        {"role": "user", "content": f"<evidence>\n{evidence_text(packet)}\n</evidence>"},
    ]


def check_output(text: str, packet: EvidencePacket) -> None:
    problems = [f"forbidden word: {w}" for w in forbidden_words(text)]
    problems += faithfulness_problems(text, packet)
    if problems:
        raise Rejected("; ".join(problems))


def template_summary(packet: EvidencePacket) -> str:
    met = [c.id for c in packet.criteria if c.status is Status.MET]
    first = f"Met: {', '.join(met)}." if met else "No criterion is met."
    open_items = [
        f"{c.id} is {c.status.value.replace('_', ' ')} ({c.rationale})"
        for c in packet.criteria
        if c.status is not Status.MET
    ]
    second = "; ".join(open_items) + "." if open_items else "No criterion is open."
    return f"{first} {second}"


class Summarizer:
    def __init__(
        self,
        url: str | None,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self._client = (
            httpx.Client(base_url=url, timeout=timeout_seconds, transport=transport)
            if url
            else None
        )

    def ask(self, packet: EvidencePacket) -> str:
        """Raw model output. Raises httpx.HTTPError or ValueError on transport or shape faults."""
        assert self._client is not None
        response = self._client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": build_prompt(packet),
                "stream": False,
                "format": SummaryOutput.model_json_schema(),
                "keep_alive": "30m",
                "options": {"temperature": 0, "seed": 7, "num_predict": 300},
            },
        )
        response.raise_for_status()
        return _ChatResponse.model_validate_json(response.content).message.content

    def from_model(self, packet: EvidencePacket) -> str:
        text = SummaryOutput.model_validate_json(self.ask(packet)).text
        check_output(text, packet)
        return text

    def warm_up(self) -> None:
        """Load the model into Ollama memory so the first evidence request does not pay for it."""
        if self._client is None:
            return
        started = time.perf_counter()
        try:
            self._client.post(
                "/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": "30m"},
                timeout=WARM_UP_TIMEOUT_SECONDS,
            ).raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("summary model warm-up failed: %s", type(exc).__name__)
            return
        logger.info("summary model warm-up done in %.1f s", time.perf_counter() - started)

    def close(self) -> None:
        if self._client:
            self._client.close()

    def __call__(self, packet: EvidencePacket) -> EvidencePacket:
        if self._client:
            try:
                return packet.model_copy(
                    update={
                        "summary": self.from_model(packet),
                        "summary_source": SummarySource.MODEL,
                        "summary_prompt_version": PROMPT_VERSION,
                    }
                )
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("summary fallback: %s", type(exc).__name__)
        return packet.model_copy(
            update={"summary": template_summary(packet), "summary_source": SummarySource.TEMPLATE}
        )
