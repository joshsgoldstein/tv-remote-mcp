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
                assert {item["id"] for item in catalog.structuredContent["result"]} == {
                    "samsung",
                    "lg_webos",
                    "sony_bravia",
                }
                planned = await session.call_tool(
                    "discover_devices", {"integration_id": "not_installed"}
                )
                assert planned.isError
                bad_key = await session.call_tool(
                    "press_key", {"tv_id": "unused", "key": "KEY_FACTORY"}
                )
                assert bad_key.isError
                assert "Unsupported key" in bad_key.content[0].text

    asyncio.run(check())


def test_mcp_vendor_inventory_and_disabled_commands(tmp_path):
    from tv_remote_mcp.config import NetworkTV, Settings, Store

    store = Store(tmp_path / "config.json")
    store.save(
        Settings(
            controls_enabled=False,
            devices=[
                NetworkTV(integration="lg_webos", id="lg", name="Sample LG", host="192.168.1.20"),
                NetworkTV(
                    integration="sony_bravia",
                    id="sony",
                    name="Sample Sony",
                    host="192.168.1.21",
                    port=80,
                ),
            ],
        )
    )

    async def check():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tv_remote_mcp.server"],
            env={
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "TV_REMOTE_CONFIG": str(store.path),
                "TV_REMOTE_STATE": str(tmp_path / "state"),
            },
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=15)
            ) as session:
                await session.initialize()
                result = await session.call_tool("list_devices", {})
                assert {d["id"] for d in result.structuredContent["result"]} == {
                    "lg_webos:lg",
                    "sony_bravia:sony",
                }
                for device_id in ["lg_webos:lg", "sony_bravia:sony"]:
                    result = await session.call_tool(
                        "device_action",
                        {"device_id": device_id, "action": "pair", "parameters": {}},
                    )
                    assert result.isError
                    assert "kill switch" in result.content[0].text

    asyncio.run(check())
