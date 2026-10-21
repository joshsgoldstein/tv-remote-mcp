"""Exercise the packaged MCP interface without contacting any TV."""

import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_tools_and_empty_inventory(tmp_path):
    async def check():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tv_remote_mcp.server"],
            env={
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "TV_REMOTE_CONFIG": str(tmp_path / "config.json"),
                "TV_REMOTE_STATE": str(tmp_path / "state"),
            },
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=15)
            ) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert len(names) == 20
                assert {
                    "list_tvs",
                    "pair_tv",
                    "set_art_mode",
                    "upload_artwork",
                    "list_devices",
                    "device_action",
                    "list_integrations",
                } <= names
                inventory = await session.call_tool("list_tvs", {})
                assert not inventory.isError
                assert inventory.structuredContent == {"result": []}
                devices = await session.call_tool("list_devices", {})
                assert devices.structuredContent == {"result": []}
                catalog = await session.call_tool("list_integrations", {})
                assert catalog.structuredContent["result"][0]["id"] == "samsung"
                planned = await session.call_tool(
                    "discover_devices", {"integration_id": "lg_webos"}
                )
                assert planned.isError
                bad_key = await session.call_tool(
                    "press_key", {"tv_id": "unused", "key": "KEY_FACTORY"}
                )
                assert bad_key.isError
                assert "Unsupported key" in bad_key.content[0].text

    asyncio.run(check())
