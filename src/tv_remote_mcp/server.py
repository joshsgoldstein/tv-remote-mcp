from __future__ import annotations

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .control import KEYS, Controller
from .home import create_home

mcp = FastMCP(
    "Home Control MCP",
    instructions=(
        "Smart-home control plane. Start with list_integrations and list_devices. "
        "Only available integrations work; planned entries are not implemented. "
        "Use capabilities and actions advertised by each device. Respect all kill switches. "
        "Use explicit TV IDs. Only pair_tv should trigger first-time pairing. "
        "Command sent is not confirmation of visible state. Never retry a toggle blindly. "
        "The Frame's Art Mode is separate from standby power."
    ),
)
controller = Controller()
home = create_home(controller)
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


@mcp.tool(annotations=READ)
def list_integrations() -> list[dict]:
    """List available adapters and planned integrations. Planned adapters cannot be used."""
    return home.catalog()


@mcp.tool(annotations=READ)
def list_devices() -> list[dict]:
    """List devices across integrations with qualified IDs, capabilities, actions, and switch state."""
    return home.devices()


@mcp.tool(annotations=READ)
def device_status(device_id: str) -> dict:
    """Read status through the device's adapter using an ID from list_devices."""
    return home.status(device_id)


@mcp.tool(annotations=WRITE)
def discover_devices(integration_id: str, save: bool = False) -> dict:
    """Discover through one available integration. Does not pair. Save registers discovered devices."""
    return home.discover(integration_id, save)


@mcp.tool(annotations=WRITE)
def device_action(device_id: str, action: str, parameters: dict) -> dict:
    """Run an advertised device action through the shared kill-switch gate. Explicit pair action requires someone at the device; never use it merely to check status. Adapter validates parameters. For Samsung: key {key: home}, power {power: on/off/toggle}, apps {}, launch {app_id: ...}, text {text: ...}, art_mode {enabled: true/false}."""
    return home.execute(device_id, action, parameters)


@mcp.tool(annotations=READ)
def list_tvs() -> list[dict]:
    """List saved TV IDs, models, addresses, Frame support, and whether a token is saved."""
    return controller.list_tvs()


@mcp.tool(annotations=WRITE)
def discover_tvs(save: bool = False) -> dict:
    """Discover Samsung TVs on the home subnet; save=True registers them and refreshes IPs. Sleeping TVs may be missed."""
    return controller.discover(save)


@mcp.tool(annotations=READ)
def tv_status(tv_id: str) -> dict:
    """Check reachability and reported power without pairing. Unreachable does not mean off."""
    return controller.status(tv_id)


@mcp.tool(annotations=WRITE)
def pair_tv(tv_id: str) -> dict:
    """Request TV authorization. Someone must select Allow for Samsung TV Remote MCP on that TV within 25 seconds."""
    return controller.pair(tv_id)


@mcp.tool(annotations=READ)
def list_remote_keys() -> dict[str, str]:
    """List supported navigation, volume, channel, media, and source buttons."""
    return KEYS


@mcp.tool(annotations=WRITE)
def press_key(tv_id: str, key: str, times: int = 1) -> dict:
    """Send a remote key 1–20 times. Use volume_up/down or mute; mute is a toggle."""
    return controller.key(tv_id, key, times)


@mcp.tool(annotations=WRITE)
def set_power(tv_id: str, action: Literal["on", "off", "toggle"]) -> dict:
    """On sends Wake-on-LAN (may leave Frame in Art Mode); off uses a long press on Frame. Toggle may switch TV/Art Mode."""
    return controller.power(tv_id, action)


@mcp.tool(annotations=WRITE)
def send_text(tv_id: str, text: str) -> dict:
    """Type up to 500 characters into the currently focused TV text field."""
    return controller.text(tv_id, text)


@mcp.tool(annotations=READ)
def list_apps(tv_id: str) -> dict:
    """List installed app IDs when supported by the TV firmware; requires pairing."""
    return controller.apps(tv_id)


@mcp.tool(annotations=WRITE)
def launch_app(
    tv_id: str, app_id: str, app_type: Literal["DEEP_LINK", "NATIVE_LAUNCH"] = "DEEP_LINK"
) -> dict:
    """Launch an installed app by ID; use NATIVE_LAUNCH for native apps."""
    return controller.launch(tv_id, app_id, app_type)


@mcp.tool(annotations=READ)
def get_art_mode(tv_id: str) -> dict:
    """Read The Frame's Art Mode state; requires pairing and Frame support."""
    return controller.art_status(tv_id)


@mcp.tool(annotations=WRITE)
def set_art_mode(tv_id: str, enabled: bool) -> dict:
    """Enable or disable The Frame's Art Mode and read back its state."""
    return controller.set_art_mode(tv_id, enabled)


@mcp.tool(annotations=READ)
def list_artwork(tv_id: str) -> dict:
    """List artwork on The Frame and its content IDs."""
    return controller.list_art(tv_id)


@mcp.tool(annotations=WRITE)
def select_artwork(tv_id: str, content_id: str) -> dict:
    """Display an existing artwork from list_artwork on The Frame."""
    return controller.select_art(tv_id, content_id)


@mcp.tool(annotations=WRITE)
def upload_artwork(tv_id: str, filename: str, matte: str = "none") -> dict:
    """Upload a PNG/JPEG already in the remote config/artwork directory (max 20 MiB). Returns an ID; does not select it."""
    return controller.upload_art(tv_id, filename, matte)


def main() -> None:
    os.umask(0o077)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
