<p align="center">
  <img src="docs/assets/banner.svg" alt="Home Control — Your home. One control plane." width="85%">
</p>

<p align="center">
  <a href="#get-started"><img src="https://img.shields.io/badge/Get_started-Copy_setup_prompt-171717?style=for-the-badge" alt="Get started: copy the setup prompt below"></a>
  <a href="docs/DOCKER.md"><img src="https://img.shields.io/badge/Run_with-Docker-525252?style=for-the-badge" alt="Run with Docker"></a>
</p>

## Get started

Use the copy button on this prompt, then paste it into your coding assistant:

```text
Set up https://github.com/joshsgoldstein/tv-remote-mcp for me.
Read AGENTS.md and docs/AGENT_SETUP.md first. Interview me about where and
how I want it deployed: a temporary laptop session, an always-on home computer,
or Docker; and whether I want the web dashboard, MCP assistant control, or both.
Reuse answers I've already given. Preserve my settings and kill switches.
Complete the setup I choose, give me the URL and start/stop instructions,
and leave device pairing pending if I can't approve it on the TV.
Keep the dashboard private.
```

Your assistant will help choose an option that fits how you want to use it.
For manual installation, jump to [Quick start](#quick-start),
[occasional laptop use](docs/LAPTOP.md), or [Docker](docs/DOCKER.md).
See the [agent setup guide](docs/AGENT_SETUP.md) for the full interview and runbook.

<p align="center">
  <a href="https://github.com/joshsgoldstein/tv-remote-mcp/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/joshsgoldstein/tv-remote-mcp/ci.yml?branch=main&amp;style=flat-square&amp;label=build" alt="Build status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-171717?style=flat-square" alt="MIT license"></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Python-3.10%2B-171717?style=flat-square" alt="Python 3.10 and newer"></a>
  <a href="docs/DOCKER.md"><img src="https://img.shields.io/badge/deploy-Docker-171717?style=flat-square" alt="Docker deployment"></a>
</p>

<p align="center">
  <a href="#get-started"><strong>Get started</strong></a> ·
  <a href="docs/DOCKER.md">Docker</a> ·
  <a href="docs/AGENT_SETUP.md">Agent setup</a> ·
  <a href="docs/HOW_IT_WORKS.md">How it works</a> ·
  <a href="docs/INTEGRATIONS.md">Integrations</a> ·
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

**Home Control is an open-source control plane for your smart home.** Manage
devices through a web dashboard or an MCP-compatible assistant, with shared
inventory, device-specific controls, and persistent kill switches. Run it on a
laptop or an always-on computer on your home network.

The platform is built around **integrations and capabilities**, so TVs,
thermostats, lights, and other devices can share one interface while keeping
their own protocols and authorization. **Samsung TVs and The Frame are the first
implemented integration.** LG, Sony, and ecobee adapters are planned.

<p align="center">
  <img src="docs/control-panel.png" alt="Home Control dashboard showing sample devices, integration selection, remote controls, and kill switches" width="80%">
  <br><sub>Dashboard preview with sample devices. Available controls depend on the installed integration and device.</sub>
</p>

| One dashboard | Assistant-ready | You stay in control |
| --- | --- | --- |
| Discover devices and show controls based on capabilities. | Shared device tools, parameter schemas, and an agent setup runbook. | Persistent device/master kill switches enforced in the backend. |

> **Early release:** Samsung discovery, status, and MCP connectivity have been
> checked on hardware. Physical remote, apps, wake, and Art Mode operations still
> await verification after on-screen pairing. Other integrations are not yet implemented.

## Requirements

- A device supported by an implemented integration. Currently: Samsung Tizen-era
  TVs with local control; Art Mode needs The Frame. LG, Sony, and ecobee are planned.
- A Linux or macOS laptop, desktop, or server with Python 3.10+ and [uv](https://docs.astral.sh/uv/).
- **The machine running this server must be on the same home network as its local devices.**
  A laptop connected to your home Wi-Fi works. For ongoing availability, use a
  computer/server that stays powered on and connected. Guest-network isolation
  or separate VLANs may prevent the devices from communicating.
- Someone at the TV to accept the initial pairing request.

The Python server uses POSIX file locks; Windows server hosting is not supported.
Older Orsay-only Samsung TVs are not implemented.

## Quick start

Choose [Docker Compose](docs/DOCKER.md) for a container, or the native setup below.
A [laptop session](docs/LAPTOP.md) is a good option for occasional use; an
always-on home computer keeps controls available while your laptop is away.
If you prefer to hand setup to an assistant, use the [ready-to-paste prompt](#get-started).

Run these commands on the laptop or computer that is connected to the TV's home
network:

```sh
git clone https://github.com/joshsgoldstein/tv-remote-mcp.git
cd tv-remote-mcp
uv sync --locked
```

### Open the web panel

```sh
uv run --locked home-control-web
```

Open **http://127.0.0.1:8765** on the same computer. Keep that command running;
Ctrl+C stops the panel. No frontend build or cloud account is required.

Choose an available integration under **Discover with**, then use **Home network**
to set your subnet and **Find devices** to discover its devices. For Samsung,
use **Pair television** when someone is ready to choose Allow on the TV.
For a television, the panel includes a directional remote, volume, channels, playback, power,
app launching, text entry, and Frame Art Mode with artwork selection.
It shares saved TVs and pairing tokens with MCP.

### Use your laptop only when you need it

You can run Home Control in the background on your everyday laptop while you're
using it at home. Start it when needed, open the dashboard, then stop it when
you're done. Your devices, pairing tokens, and kill switches stay saved for next
time. No always-on server is required for this option.

See [the laptop session guide](docs/LAPTOP.md) for copy-and-paste start/stop
commands. The laptop must be awake and connected to the devices' home Wi-Fi;
sleeping or leaving home makes control unavailable until it reconnects.
For assistant-only use, your MCP client starts the server on demand, so the web
panel does not need to run.

### Device kill switches

**Disable device** blocks one device. **Disable all controls** blocks every device,
including newly discovered ones, until the master switch is re-enabled.
Both are saved on disk and enforced by the shared backend for web, CLI, and MCP
commands, including pairing, Wake-on-LAN, and Art Mode. Rediscovery and restarts
preserve them. Enabling the master switch does not enable a disabled device.
The assistant has no MCP tool to re-enable either switch.

Inventory, discovery, and basic status reads remain available. These switches
cannot recall an in-flight command, cut physical power, or block other device apps.
You can also operate them locally:

```sh
uv run home-control disable all
uv run home-control disable samsung:frame
# Only when you want control restored:
uv run home-control enable all
uv run home-control enable samsung:frame
```

### Discover and pair from the terminal

The default discovery subnet is `192.168.1.0/24`. If your home LAN uses a different
subnet, create or edit `~/.config/tv-remote-mcp/config.json` before discovery:

```json
{
  "subnet": "192.168.1.0/24",
  "tvs": []
}
```

Turn on your TVs, then run:

```sh
uv run tv-remote discover --save
uv run tv-remote list
```

Pair each TV using its returned ID, for example:

```sh
uv run tv-remote pair frame
```

Within 25 seconds, select **Allow** for **Samsung TV Remote MCP** on the TV.
Tokens are saved locally and reused. If pairing times out, rerun it when someone
is ready to approve; the installation remains available.

For denied or repeated prompts, look in the TV's **Device Connection Manager →
Device List**, and consider **Access Notification → First Time Only** if the
firmware offers it. Menu paths differ by model. See the
[upstream pairing notes](https://github.com/xchwarze/samsung-tv-ws-api#samsung-tv-keeps-asking-for-permission).

Sleeping TVs may not respond to discovery. Turn them on and scan again.
Non-Frame TVs usually receive ID `samsung`; use the returned ID rather than
assuming a name. Friendly `name` fields can be edited in the config; keep paired
`id` values stable because they identify token files.

### Connect your assistant

On the same computer, configure your MCP client to launch the server. For Codex,
replace the example path with the absolute path to your checkout:

```sh
codex mcp add home_control -- uv --directory /absolute/path/to/tv-remote-mcp run --locked home-control-mcp
```

Alternatively, merge [examples/codex.toml](examples/codex.toml) into your Codex
configuration. Other stdio MCP clients can use [examples/mcp.json](examples/mcp.json).
Replace the example path, and use an absolute path to `uv` if your desktop app
cannot find it. See the [official Codex MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Reconnect or reload the client after adding the server. It starts the server
process when needed; you do not need to leave a separate terminal running.
A sleeping laptop or one that leaves your home network cannot control the TVs.

Example requests:

- “List my devices and available integrations.”
- “Check the Frame's status.”
- “Lower the bedroom TV's volume three steps.”
- “Put the Frame into Art Mode.”
- “List the Frame's artwork and display this content ID.”

### Using an always-on computer/server

You can install this same package on a home desktop, mini PC, Raspberry Pi, or
server instead. The **MCP server must still run inside the TV's home network**.
An MCP client running on that computer uses the local setup above. If the client
runs on a different computer, it needs a transport to the home host; the optional
SSH setup below provides one. MCP uses stdio; the optional web panel serves a separate browser API, not HTTP MCP.

## Optional private browser access

The panel binds to localhost by default. To use it away from home, keep it on
an always-on home computer and use a private VPN. With Tailscale installed and
authorized, get that computer's actual MagicDNS hostname from `tailscale status`.
Replace `your-home-host.your-tailnet.ts.net` below with that hostname:

```sh
uv run home-control-web --external-origin https://your-home-host.your-tailnet.ts.net
# In another terminal on the same computer:
tailscale serve --bg --https=443 http://127.0.0.1:8765
```

Open that HTTPS hostname from a device connected to the same tailnet. Inspect
`tailscale serve status` first so you don't replace an existing service; choose
another HTTPS port and include it in the external origin if necessary. Tailscale
may require an administrator to enable HTTPS/Serve. Access follows your tailnet's
access policy; anyone permitted to reach this service can operate its controls.
The app remains bound to loopback, trusts only the exact configured origin, and
does not trust arbitrary forwarded headers. **Do not enable Tailscale Funnel.**
Stop this mapping with `tailscale serve --https=443 off`; stop the app separately.
See [Tailscale Serve documentation](https://tailscale.com/kb/1312/serve).

Advanced direct LAN hosting requires `TV_REMOTE_WEB_TOKEN` (a private random
value of at least 24 characters) plus `--host <server-lan-ip>` and
`--allow-host <server-lan-ip>`. Supply the token via a private environment file,
not a committed config or URL. The browser requests it and retains it only in
memory. Plain LAN HTTP does not encrypt this token; prefer private HTTPS above.
Never expose this service through router port forwarding or a public proxy.

## Integrations

| Integration | Status | Connection |
| --- | --- | --- |
| Samsung TVs / The Frame | Implemented; live control verification pending pairing | Local WebSocket remote / Art Mode |
| LG webOS | Planned | Separate webOS adapter and pairing |
| Sony BRAVIA | Planned | Separate, model-dependent Sony API adapter |
| ecobee thermostats | Planned | Separate thermostat authorization and capabilities |
| Lights, plugs, other devices | Future integrations | Device/protocol-specific adapters |

`list_integrations` distinguishes available adapters from planned entries and
returns action parameter schemas. `list_devices` returns each device's category,
capabilities, supported actions, and enabled/paired state. The browser uses the
same registry; unsupported actions are rejected before contacting a device.

See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) for the implemented adapter
contract, vendor references, testing requirements, and how to add a device type.
No LG, Sony, or thermostat commands are implemented yet.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_integrations` | Available/planned adapters and action parameter schemas |
| `list_devices` | Cross-integration inventory with qualified IDs and capabilities |
| `discover_devices` | Discover through one available integration; optionally save |
| `device_status` | Read status through the device's adapter |
| `device_action` | Run an advertised action through the shared command gate |
| `list_tvs` | Saved IDs, models, addresses, and token availability |
| `discover_tvs` | Discover TVs; `save=True` registers them and refreshes addresses |
| `tv_status` | Read reachability, identity, and reported power without pairing |
| `pair_tv` | Request on-screen authorization and save a token |
| `list_remote_keys` | List supported buttons |
| `press_key` | Navigation, volume, mute, channels, playback, and source; 1–20 repeats |
| `set_power` | Wake-on-LAN, power off, or explicit toggle |
| `send_text` | Type into the active TV text field |
| `list_apps` | Request installed app IDs where firmware supports it |
| `launch_app` | Launch an installed app by ID |
| `get_art_mode` | Read The Frame's Art Mode state |
| `set_art_mode` | Set Art Mode and read back its state |
| `list_artwork` | List artwork and content IDs |
| `select_artwork` | Display existing artwork |
| `upload_artwork` | Upload a staged PNG/JPEG and return its content ID |

The remaining TV-specific tools are compatibility conveniences for the Samsung
adapter. New integrations use the shared device interface. For example:

```text
list_devices()
device_action(device_id="samsung:frame", action="apps", parameters={})
```

Look up `list_integrations` for the required parameters and `list_devices` for
supported actions. Pairing is still required for commands that need authorization.

### Upload artwork

Place an image in the artwork directory on the computer running the server:

```sh
mkdir -p ~/.config/tv-remote-mcp/artwork
cp photo.jpg ~/.config/tv-remote-mcp/artwork/
```

Then call `upload_artwork(tv_id="frame", filename="photo.jpg")`, followed by
`select_artwork` with the returned content ID. Images must be PNG/JPEG, at most
20 MiB, and inside the config directory's `artwork` subdirectory.
Uploading does not automatically display or delete artwork.

## Configuration and behavior

The app uses `home-control`, `home-control-web`, and `home-control-mcp` commands.
The original `tv-remote*` commands, repository/package name, config paths, and TV
IDs remain compatible with existing installations. No token migration is needed.

| Setting | Default |
| --- | --- |
| `TV_REMOTE_CONFIG` | `~/.config/tv-remote-mcp/config.json` |
| `TV_REMOTE_STATE` | `state/` alongside the config file |
| Discovery subnet | `192.168.1.0/24` |
| Samsung remote port | `8002` (TLS); `8001` supported when configured |

Environment overrides apply on the machine running the server. The configuration
schema is in [config.py](src/tv_remote_mcp/config.py); discovery fills in the TV
records automatically.

- **Power and Art Mode are separate.** Reported `PowerState=on` does not distinguish
  playback from Art Mode. A Frame power toggle may switch between them.
- **Wake is a request.** Enable Power On with Mobile on the TV if available.
  Wake-on-LAN support depends on the TV/network. A Frame may wake into Art Mode.
- **Frame power-off uses a three-second power-button hold.** Avoid blindly
  retrying toggles or mute.
- **Command delivery is not visible-state confirmation.** Buttons and app launches
  return `command_sent`. Unreachable status means unknown, not definitely off.
- **Firmware support varies.** App enumeration and Art Mode commands may differ
  across models. Real hardware validation is still pending for these actions.
- **Discovery preserves existing TVs.** It retains offline records and keeps
  friendly names/token IDs when a recognized TV changes its DHCP address.
  Commands check device identity before sending. DHCP reservations can help.
- **Pairing tokens stay local.** Token files use mode `0600`, the created state
  directory uses `0700`, and upstream token logging is suppressed. A saved token
  can still be revoked by the TV.
- **Discovery is bounded** to a private IPv4 subnet of `/24` or smaller. There are
  no arbitrary shell-execution tools or service-menu keys.
- **TV TLS uses a self-signed certificate.** The Samsung client accepts it on the
  LAN. The optional SSH transport authenticates and encrypts remote client connections.

## Development

```sh
uv sync --locked
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv build
```

Tests mock hardware. CI checks Python 3.10 and 3.13 on Linux and builds the package.
See [CONTRIBUTING.md](CONTRIBUTING.md) for test and compatibility-report guidance.

After updating the code and running `uv sync --locked`, reconnect MCP sessions
to load the updated server.

## Optional: access a home server over SSH

This is for an assistant on a different computer, including when you are away
from home. It is not needed when the assistant and MCP server run together on
a laptop connected to home Wi-Fi. The server itself always stays on the home LAN.

Set up key-based SSH to your home host. For access away from home, use an existing
private VPN such as Tailscale. An example `~/.ssh/config` entry:

```sshconfig
Host tv-home
    HostName your-home-host
    User your-user
    IdentityFile ~/.ssh/id_ed25519
```

The deployment script requires Python 3.10+ with `venv` on that host:

```sh
ssh -o BatchMode=yes tv-home hostname
sh scripts/deploy.sh tv-home
ssh tv-home '~/tv-remote-mcp/.venv/bin/tv-remote discover --save'
ssh tv-home '~/tv-remote-mcp/.venv/bin/tv-remote pair frame'
```

It installs into `~/tv-remote-mcp/.venv` and preserves existing settings/tokens.
Edit the config **on that host** if its discovery subnet differs from the default.

Use [examples/codex-ssh.toml](examples/codex-ssh.toml) or
[examples/mcp-ssh.json](examples/mcp-ssh.json) to connect your client. Replace the
SSH alias as needed. The MCP process starts no network listener;
SSH carries MCP's stdin/stdout stream.

Verify the connection using only Python's standard library on the client:

```sh
python3 scripts/smoke.py --host tv-home --tv-id frame
```

This initializes MCP, lists tools, reads status, and confirms rejection of an
unsupported key. Omit `--tv-id` to test before registering TVs. Re-run the deploy
script to update, then reconnect MCP sessions. For artwork, copy the file into
`~/.config/tv-remote-mcp/artwork/` on the home host before calling `upload_artwork`.

## License and dependencies

This project's original code is [MIT licensed](LICENSE).
[samsungtvws](https://github.com/xchwarze/samsung-tv-ws-api) is an external
LGPL-3.0 dependency and retains its own license. The
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) is MIT licensed.
