"""Replica of the Claude voice agent's Reminders MCP surface (stdio).

Serves the exact five reminder_*_v0 tools plus the user_time_v0 stub they
depend on, backed by real EventKit. Run under an isolated Claude Code instance
(see run.py) so a test agent drives the same tool surface the voice agent has —
no other tools — to exercise reminders-bridge end to end.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import ekstore
from tools import SPECS

server = Server("reminders")
_TOOLS = [
    Tool(name=s["name"], description=s["description"], inputSchema=s["inputSchema"])
    for s in SPECS
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _TOOLS


def _user_time() -> dict[str, Any]:
    now = dt.datetime.now().astimezone()
    off = now.utcoffset()
    return {
        "time": now.isoformat(),
        "timezone": now.tzname() or "",
        "utc_offset_seconds": int(off.total_seconds()) if off else 0,
        "timestamp": now.timestamp(),
        "status": "success",
    }


def _dispatch(name: str, a: dict[str, Any]) -> dict[str, Any]:
    if name == "reminder_list_search_v0":
        return ekstore.list_lists(a.get("searchText"))
    if name == "reminder_search_v0":
        return ekstore.search(
            searchText=a.get("searchText"),
            listId=a.get("listId"),
            listName=a.get("listName"),
            status=a.get("status", "incomplete"),
            dateFrom=a.get("dateFrom"),
            dateTo=a.get("dateTo"),
            limit=a.get("limit", 100),
        )
    if name == "reminder_create_v0":
        return ekstore.create(a.get("reminderLists", []))
    if name == "reminder_update_v0":
        return ekstore.update(a.get("reminderUpdates", []))
    if name == "reminder_delete_v0":
        return ekstore.delete(a.get("reminderDeletions", []))
    if name == "user_time_v0":
        return _user_time()
    raise ValueError(f"unknown tool: {name}")


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        result = _dispatch(name, arguments or {})
    except Exception as e:  # surface as a tool-level error, not a crash
        result = {"status": "error", "error": f"{type(e).__name__}: {e}"}
    return [TextContent(type="text", text=json.dumps(result))]


async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
