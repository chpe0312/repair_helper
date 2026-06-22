"""M2 — L3 über den In-Memory-FastMCP-Client ansprechen.

Beweist: der State-MCP-Server startet und beantwortet Tool-Calls nachweislich,
ohne Subprozess und ohne Live-Modell.
"""

from __future__ import annotations

import asyncio

from fastmcp import Client

from store import server


def _call(tmp_path):
    server.configure(str(tmp_path / "mcp.sqlite"))

    async def run():
        async with Client(server.mcp) as client:
            tools = {t.name for t in await client.list_tools()}
            started = await client.call_tool(
                "start_session", {"board_id": "A1708", "symptom": "kein Power"}
            )
            sid = started.data["id"]
            await client.call_tool(
                "log_step",
                {
                    "session_id": sid,
                    "measurement_point": "PPBUS_G3H @ TP",
                    "evidence": "measured",
                    "net": "PPBUS_G3H",
                    "designator": "U7800",
                    "confidence": 85,
                },
            )
            full = await client.call_tool("get_session", {"session_id": sid})
            await client.call_tool(
                "add_known_failure",
                {"board_id": "A1708", "symptom": "kein PP3V3_S5", "source": "manual"},
            )
            kfs = await client.call_tool(
                "list_known_failures", {"board_id": "A1708"}
            )
            return tools, started.data, full.data, kfs.data

    return asyncio.run(run())


def test_state_server_answers_tool_calls(tmp_path):
    tools, started, full, kfs = _call(tmp_path)
    # Alle erwarteten Tools registriert.
    assert {
        "start_session",
        "get_session",
        "list_sessions",
        "update_session",
        "log_step",
        "add_known_failure",
        "get_known_failure",
        "list_known_failures",
        "update_known_failure",
        "delete_known_failure",
    } <= tools
    assert started["board_id"] == "A1708"
    assert started["status"] == "open"
    assert len(full["steps"]) == 1
    step = full["steps"][0]
    assert step["net"] == "PPBUS_G3H"
    assert step["designator"] == "U7800"
    assert step["evidence"] == "measured"
    assert step["confidence"] == 85
    assert len(kfs) == 1
    assert kfs[0]["symptom"] == "kein PP3V3_S5"
