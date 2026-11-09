"""Write the packet summary with the model, or fall back to the template, and trace which."""

import logging
import time

import httpx

from app.clients.ollama import OllamaClient
from app.domain.enums import SummaryFallback, SummarySource
from app.domain.packet import EvidencePacket, SummaryTrace
from app.ops.logs import log_event
from app.ops.timing import elapsed_ms
from app.summary.output import Rejected, SummaryOutput, check_output
from app.summary.prompt import PROMPT_VERSION, build_prompt
from app.summary.template import template_summary

logger = logging.getLogger("pa.summary")


def fallback_reason(exc: Exception) -> SummaryFallback:
    """Classify why the model summary was not used."""
    if isinstance(exc, Rejected):
        return SummaryFallback.REJECTED
    if isinstance(exc, httpx.HTTPStatusError):
        return SummaryFallback.MODEL_ERROR
    if isinstance(exc, httpx.HTTPError):
        return SummaryFallback.UNREACHABLE
    return SummaryFallback.BAD_OUTPUT


def apply_summary(packet: EvidencePacket, text: str, trace: SummaryTrace) -> EvidencePacket:
    """Return the packet with the summary text and its labels set."""
    return packet.model_copy(
        update={
            "summary": text,
            "summary_source": trace.source,
            "summary_prompt_version": trace.prompt_version,
        }
    )


class Summarizer:
    """Summarizes packets with Ollama; with no URL it always uses the template.

    `model` is the default. `choices` are further models a caller may ask for by name; any
    other name is refused, so a caller can never make Ollama pull or run an unvetted model.
    """

    def __init__(
        self,
        url: str | None,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        choices: tuple[str, ...] = (),
    ) -> None:
        """Create the Ollama client, or none when `url` is unset."""
        self.model = model
        self.models = tuple(dict.fromkeys((model, *choices)))
        self.client = OllamaClient(url, timeout_seconds, transport) if url else None

    def offers(self, model: str) -> bool:
        """True when `model` is the default or one of the allowed choices."""
        return model in self.models

    def ask(self, packet: EvidencePacket, model: str | None = None) -> str:
        """Raw model output. Raises httpx.HTTPError or ValueError on transport or shape faults."""
        assert self.client is not None
        return self.client.chat(
            model or self.model, build_prompt(packet), SummaryOutput.model_json_schema()
        )

    def from_model(self, packet: EvidencePacket, model: str) -> str:
        """The model's summary, parsed and checked. Raises on any fault."""
        text = SummaryOutput.model_validate_json(self.ask(packet, model)).text
        check_output(text, packet)
        return text

    def summarize(
        self, packet: EvidencePacket, model: str | None = None
    ) -> tuple[str, SummaryTrace]:
        """The summary text and a trace naming its source, model, latency, and any fallback.

        `model` must be one `offers` accepts; the caller checks, so None means the default.
        """
        model = model or self.model
        if self.client is None:
            trace = SummaryTrace(
                source=SummarySource.TEMPLATE, fallback=SummaryFallback.NOT_CONFIGURED
            )
            return template_summary(packet), trace
        started = time.perf_counter()
        try:
            text = self.from_model(packet, model)
        except (httpx.HTTPError, ValueError) as exc:
            reason = fallback_reason(exc)
            log_event(logger, event="summary_fallback", summary_fallback=reason.value)
            trace = SummaryTrace(
                source=SummarySource.TEMPLATE,
                model=model,
                latency_ms=elapsed_ms(started),
                fallback=reason,
            )
            return template_summary(packet), trace
        trace = SummaryTrace(
            source=SummarySource.MODEL,
            model=model,
            prompt_version=PROMPT_VERSION,
            latency_ms=elapsed_ms(started),
        )
        return text, trace

    def warm_up(self) -> None:
        """Load the model into Ollama memory so the first evidence request does not pay for it."""
        if self.client is None:
            return
        started = time.perf_counter()
        try:
            self.client.warm_up(self.model)
        except httpx.HTTPError as exc:
            logger.warning("summary model warm-up failed: %s", type(exc).__name__)
            return
        logger.info("summary model warm-up done in %.1f s", time.perf_counter() - started)

    def close(self) -> None:
        """Close the Ollama connection pool, if any."""
        if self.client:
            self.client.close()

    def __call__(self, packet: EvidencePacket) -> EvidencePacket:
        """Return the packet with its summary filled in."""
        return apply_summary(packet, *self.summarize(packet))
