"""A thin client for the Ollama HTTP API: chat, warm-up, and the probes the health check uses."""

import httpx
from pydantic import BaseModel

KEEP_ALIVE = "30m"
WARM_UP_TIMEOUT_SECONDS = 300.0


class ChatMessage(BaseModel):
    """The assistant message inside an Ollama chat response."""

    content: str


class ChatResponse(BaseModel):
    """The part of an Ollama /api/chat response the service reads."""

    message: ChatMessage


class OllamaClient:
    """Calls one Ollama server. Each call names the model it wants."""

    def __init__(
        self,
        url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Open a connection pool to the server at `url`."""
        self._http = httpx.Client(base_url=url, timeout=timeout_seconds, transport=transport)

    def chat(self, model: str, messages: list[dict[str, str]], output_schema: dict) -> str:
        """Run one deterministic chat turn and return the raw reply text.

        Raises httpx.HTTPError on transport or status faults and ValueError on a malformed body.
        """
        response = self._http.post(
            "/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "format": output_schema,
                "keep_alive": KEEP_ALIVE,
                "options": {"temperature": 0, "seed": 7, "num_predict": 300},
            },
        )
        response.raise_for_status()
        return ChatResponse.model_validate_json(response.content).message.content

    def warm_up(self, model: str) -> None:
        """Load `model` into memory. Raises httpx.HTTPError when Ollama refuses or fails."""
        self._http.post(
            "/api/generate",
            json={"model": model, "prompt": "", "keep_alive": KEEP_ALIVE},
            timeout=WARM_UP_TIMEOUT_SECONDS,
        ).raise_for_status()

    def get_json(self, path: str, timeout_seconds: float) -> dict:
        """GET a JSON endpoint such as /api/version, /api/tags, or /api/ps."""
        response = self._http.get(path, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the connection pool."""
        self._http.close()
