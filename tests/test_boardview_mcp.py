"""M3 — L1 (Boardview) über den In-Memory-FastMCP-Client ansprechen.

Beweist (analog zu test_store_mcp.py für L3): der L1-MCP-Server beantwortet
Tool-Calls nachweislich. Board wird name-agnostisch via Fixture geladen.
"""

from __future__ import annotations

import asyncio

from fastmcp import Client

import boardview_mcp


def _call(library):
    boardview_mcp.LIB = library  # Server an die echte Library hängen
    library.active = library.resolve("A1708")

    async def run():
        async with Client(boardview_mcp.mcp) as client:
            tools = {t.name for t in await client.list_tools()}
            info = await client.call_tool("board_info", {})
            net = await client.call_tool("get_net", {"net": "PPBUS_G3H"})
            return tools, info.data, net.data

    return asyncio.run(run())


def test_l1_server_answers_tool_calls(library):
    tools, info, net = _call(library)
    assert {
        "list_boards",
        "select_board",
        "board_info",
        "get_net",
        "get_part",
        "shared_nets",
        "find_testpoints",
        "nearest_parts",
        "search",
    } <= tools
    assert info["parts"] == 2838
    assert net["part_count"] == 35
