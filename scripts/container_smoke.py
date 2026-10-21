"""Run only inside a disposable, empty-inventory test container."""

import argparse
import asyncio
import json
import os
import urllib.error
import urllib.request
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def request(path, data=None):
    headers = {"Authorization": "Bearer " + os.environ["TV_REMOTE_WEB_TOKEN"]}
    encoded = None
    if data is not None:
        headers.update({"Content-Type": "application/json", "X-TV-Remote": "1"})
        encoded = json.dumps(data).encode()
    req = urllib.request.Request("http://127.0.0.1:8765" + path, data=encoded, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


async def mcp_check():
    async with stdio_client(StdioServerParameters(command="home-control-mcp")) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=10)
        ) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert {"list_devices", "list_integrations", "device_action"} <= names
            result = await session.call_tool("list_devices", {})
            assert result.structuredContent == {"result": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-disabled", action="store_true")
    args = parser.parse_args()
    assert os.getuid() == 10001, "Container must run as the unprivileged image user"
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/api/state", timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 401, "Anonymous inventory access must be rejected"
    else:
        raise AssertionError("Inventory must require authentication")
    state = request("/api/state")
    assert not state["devices"], "Refusing to test a container with real device inventory"
    assert state["integrations"][0]["id"] == "samsung"
    if args.expect_disabled:
        assert state["controls_enabled"] is False, "Switch must survive a container restart"
    else:
        request("/api/controls", {"enabled": False})
        assert request("/api/state")["controls_enabled"] is False
        asyncio.run(mcp_check())
    print("Container smoke check passed")


if __name__ == "__main__":
    main()
