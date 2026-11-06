import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

PACKET_TOOL = "get_evidence_packet"
MAX_STEPS = 6
SYSTEM_PROMPT = (
    "You help a nurse review prior-authorization requests. You only report evidence and never "
    "recommend, approve or deny. To answer you must call the get_evidence_packet tool with the "
    "request id you are given. After the tool result arrives, write at most two plain sentences "
    "about which criteria need attention. Do not restate the whole packet."
)


@dataclass(frozen=True)
class AgentRun:
    request_id: str
    packet_text: str
    narration: str
    tool_calls: tuple[str, ...]


def ollama_tools(mcp_tools) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema},
        }
        for t in mcp_tools
    ]


def chat(client: httpx.AsyncClient, model: str, messages: list[dict], tools: list[dict]):
    return client.post(
        "/api/chat",
        json={"model": model, "messages": messages, "tools": tools, "stream": False},
    )


async def run_agent(request_id: str, mcp_url: str, mcp_token: str, ollama_url: str, model: str):
    packet_text: str | None = None
    calls: list[str] = []
    narration = ""
    mcp_http = httpx.AsyncClient(headers={"Authorization": f"Bearer {mcp_token}"}, timeout=120)
    async with (
        mcp_http,
        streamable_http_client(mcp_url, http_client=mcp_http) as (read, write, _),
        ClientSession(read, write) as session,
        httpx.AsyncClient(base_url=ollama_url, timeout=600) as ollama,
    ):
        await session.initialize()
        tools = ollama_tools((await session.list_tools()).tools)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Review prior-authorization request {request_id}."},
        ]
        for _ in range(MAX_STEPS):
            response = await chat(ollama, model, messages, tools)
            response.raise_for_status()
            message = response.json()["message"]
            messages.append(message)
            requested = message.get("tool_calls") or []
            if not requested:
                narration = message.get("content", "").strip()
                if packet_text is None:
                    messages.append(
                        {"role": "user", "content": f"Call {PACKET_TOOL} for {request_id} now."}
                    )
                    continue
                break
            for call in requested:
                name = call["function"]["name"]
                arguments = call["function"]["arguments"]
                calls.append(f"{name}({json.dumps(arguments)})")
                result = await session.call_tool(name, arguments)
                text = "".join(c.text for c in result.content if c.type == "text")
                if name == PACKET_TOOL and not result.isError:
                    packet_text = text
                messages.append({"role": "tool", "tool_name": name, "content": text})
    if packet_text is None:
        raise RuntimeError(f"model never obtained a packet via {PACKET_TOOL}; calls={calls}")
    return AgentRun(request_id, packet_text, narration, tuple(calls))


def render(run: AgentRun) -> str:
    return (
        f"tool calls: {', '.join(run.tool_calls)}\n"
        f"--- TOOL RESULT, verbatim from {PACKET_TOOL} ---\n"
        f"{run.packet_text}\n"
        f"--- MODEL NARRATION, not evidence, written by the model ---\n"
        f"{run.narration}"
    )


def settings_from_env() -> dict[str, str]:
    return {
        "mcp_url": os.environ.get("MCP_URL", "http://localhost:8001/mcp"),
        "mcp_token": os.environ["MCP_TOKEN"],
        "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        "model": os.environ.get("AGENT_MODEL", "qwen2.5:3b"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ReAct agent over the PA evidence MCP tools")
    parser.add_argument("request_id")
    run = asyncio.run(run_agent(parser.parse_args().request_id, **settings_from_env()))
    sys.stdout.write(render(run) + "\n")


if __name__ == "__main__":
    main()
