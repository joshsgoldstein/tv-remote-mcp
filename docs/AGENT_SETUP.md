# Set this up for a nontechnical user

This is Home Control, a general smart-home platform. Read docs/INTEGRATIONS.md;
Samsung is the first available adapter. LG, Sony, and ecobee remain planned.
Never configure a roadmap entry as if it were implemented.

You are the user's setup assistant. Complete the work available on their computer,
then explain only what they need to do. Use the user's existing authorization;
ask concise questions only for information or permission you actually lack.

## 1. Interview the user about deployment

Before installing dependencies, starting a server, changing MCP configuration,
or creating services, have a short deployment conversation. Cloning and reading
this repository is preparation, not a reason to choose a deployment for them.
Reuse explicit answers and existing authorization from the conversation; ask only
for decisions that are still missing. Read-only OS/network checks can help you
present relevant options. Do not ask the user for facts you can safely inspect.

Ask in plain language, preferably together with simple choices:

1. **Where should it run, and when should it be available?** Offer this laptop
   only while they're using it, or an existing always-on home computer/server.
   Explain that the host must be on the devices' home network. A temporary laptop
   session is a complete option; it needs the laptop awake and on home Wi-Fi.
   An always-on host keeps controls available when the laptop sleeps or leaves.
2. **How would they like to use it?** Offer the web dashboard, their assistant
   through MCP, or both. If MCP is wanted, identify their actual client and where
   it runs. If both are wanted, explain that they are separate processes sharing
   settings, and stopping the dashboard doesn't disconnect the assistant.
3. **Do they have a preferred installation method?** Recommend native Python/uv
   for a simple laptop session. Offer Docker when they already use it or prefer
   a container. Explain that Docker still needs a home-network host and may
   affect broadcast discovery/wake. If they have no preference, recommend the
   simplest method for the host they chose and confirm that choice in the recap.

Ask about access from another computer or away from home only if they need it.
Private remote access needs explicit authorization and an existing or deliberately
configured private transport. Keep localhost as the default. Do not assume SSH,
Tailscale, a cloud account, Docker, or an always-on server is available.

Recap the selected host, availability, installation method, and dashboard/MCP
choices in one sentence, then proceed using their answers. This is a deployment
choice, not a separate approval gate for every command. Do not repeat questions
that the user has already answered. If they ask for advice, give a recommendation
and resolve the remaining choice before starting deployment.

For a temporary laptop session, follow docs/LAPTOP.md and provide its start/stop
commands. Keep its terminal available. Do not install a login/startup service for
this mode. For continuous availability, agree on the service behavior before
creating it. Preserve services already installed.

Linux/macOS native hosting is supported. If the current computer is away from
home, explain that local discovery/control must wait until it reconnects, or use
an already-authorized host inside the home LAN. Prepare locally if that's their
choice; leave hardware discovery and pairing pending as needed.

## 2. Install without replacing personal settings

If the user prefers a container, follow docs/DOCKER.md. Build from the checkout,
create a private .env token without overwriting existing settings, and keep
/data in a named volume. Explain Docker networking limits and verify health,
authentication, and persistence before claiming success. A prebuilt registry
image has not been published. Do not start both native and container versions
against different stores and imply their switches/tokens are synchronized.

For native installation:

Check for Git, Python 3.10+, and uv. Use the official uv installation instructions
linked in README.md if missing, respecting the user's installation permissions.
Clone https://github.com/joshsgoldstein/tv-remote-mcp.git into an appropriate user
folder, or use the existing checkout. Run `uv sync --locked` there. If updating,
inspect local changes first; never reset or overwrite them.

The default config is ~/.config/tv-remote-mcp/config.json. Read existing settings
before changes, preserve devices and enabled flags, and do not print tokens.
Inspect the home network interface/routing table to determine its IPv4 subnet;
do not assume 192.168.1.0/24. Discovery accepts a private /24 or smaller subnet.
If the LAN is larger, choose the relevant /24 with the user rather than scanning
an entire corporate or unrelated network. Avoid VPN interface subnets.

## 3. Open the panel and discover devices

Start `uv run --locked home-control-web` from the checkout. Open
http://127.0.0.1:8765 on that same computer. Keep the process running while using
the panel. Use Home network to set the correct discovery subnet, select an available adapter under Discover with, then Find
devices. Alternatively run `uv run --locked tv-remote discover --save`.
Use returned IDs, not guessed names. Missing TVs may be asleep or isolated on
guest Wi-Fi. Explain this and ask the user to turn them on; keep saved records.

## 4. Pair with the person at the TV

First ask whether someone can accept an on-screen request now. If yes, use Pair
television or `uv run --locked tv-remote pair <returned-id>` and have them choose
Allow for Samsung TV Remote MCP within 25 seconds. Confirm token_saved afterward.
If no one is present, leave pairing pending. Do not disable TV authorization or
claim a settings change can replace an initial approval on every firmware.

## 5. Connect their assistant if requested

Detect which MCP client the user uses and read its current configuration. Use
the local examples in examples/ and replace the checkout path with its absolute
path. Find the actual uv executable, since desktop apps may have a different PATH.
Merge just this server entry, preserving other servers and settings. For Codex:

```sh
codex mcp add home_control -- uv --directory /absolute/path/to/tv-remote-mcp run --locked home-control-mcp
```

If home_control or the legacy samsung_tvs entry already exists, inspect and update
that entry instead of creating duplicate server processes. The MCP
client starts its own stdio process. The web panel is a separate optional
process sharing the same configuration and tokens. The HTTP panel is NOT an
HTTP MCP endpoint. Reload the MCP client and verify list_integrations, list_devices, and device_status.
Do not send control commands merely to prove setup worked.

## 6. Explain the switches and availability

Show Disable device and Disable all controls. They persist across restart,
rediscovery, and MCP sessions. They block commands, pairing, wake, and Art Mode
operations from this project. Inventory/discovery/basic status remain readable.
A switch cannot recall a command already sent, turn off physical power, or
prevent the Samsung remote or another app from controlling the device.
Only explicitly requested re-enabling is allowed. MCP has no tool to re-enable.
The local fallback is `uv run home-control disable all` or `disable <integration:device-id>`;
`enable` reverses the requested switch only.

For an always-on install, offer an OS service only if wanted. A Linux user
service can use the absolute .venv/bin/tv-remote-web path with Restart=on-failure,
After=network-online.target, and WantedBy=default.target. Verify `systemctl --user`
works and lingering is enabled if it must survive logout/reboot. Do not claim
reboot persistence unless verified. macOS uses launchd. Preserve other services.

Private access from a phone or another computer is optional. Follow
docs/REFERENCE.md, under Optional private browser access.
Do not put a personal tailnet URL or credentials into this public repository.

## 7. Finish with evidence the user understands

Report the actual clickable web URL, where the server runs, whether it stays
running, discovered TVs, paired versus pending TVs, and connected MCP client.
Give the exact start/stop commands for their installation. For a laptop session,
identify the terminal that owns the background process and how to stop it; closing
the browser alone does not stop the panel. State any remaining
manual action. Do not call the setup fully paired when a token is absent.
