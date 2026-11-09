"""Runs the agent for every supplied request and compares it with the HTTP endpoint."""

import asyncio
import json
import os
import sys

import httpx

from agent.agent import run_agent, settings_from_env

REQUEST_IDS = [f"PA-00{n}" for n in range(1, 8)]


def view(packet: dict) -> dict:
    """The parts of a packet the agent and the API must agree on: statuses and route."""
    return {
        "statuses": {c["id"]: c["status"] for c in packet["criteria"]},
        "route": packet["route"],
    }


async def main() -> int:
    """Run the agent for each supplied request and compare it with the HTTP endpoint."""
    api = os.environ.get("API_URL", "http://localhost:8000")
    headers = {"Authorization": f"Bearer {os.environ['NURSE_TOKEN']}"}
    failures = 0
    for request_id in REQUEST_IDS:
        run = await run_agent(request_id, **settings_from_env())
        agent_packet = json.loads(run.packet_text)
        endpoint = httpx.get(
            f"{api}/requests/{request_id}/evidence", headers=headers, timeout=120
        ).json()
        same_view = view(agent_packet) == view(endpoint)
        identical = agent_packet == endpoint
        failures += not (same_view and identical)
        row = " ".join(f"{k}={v}" for k, v in view(agent_packet)["statuses"].items())
        sys.stdout.write(
            f"{request_id} {row} route={agent_packet['route']} "
            f"statuses_match={same_view} packet_identical={identical}\n"
        )
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
