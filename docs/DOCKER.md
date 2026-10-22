# Run Home Control in Docker

The container runs the same web dashboard, adapters, MCP tools, and kill switches
as a native installation. Build it from this repository; no prebuilt registry
image is published yet. Use a Docker host on the devices' home LAN. A cloud VPS
cannot discover your home devices just because the app is containerized.

## Start the web dashboard

Install Docker Engine with the Compose plugin (Linux) or Docker Desktop (macOS).
From this checkout, create a private access token without overwriting an existing
.env file:

```sh
if [ ! -e .env ]; then
  (umask 077; printf 'TV_REMOTE_WEB_TOKEN=%s\n' "$(openssl rand -hex 32)" > .env)
fi
docker compose up -d --build
docker compose ps
```

Open **http://127.0.0.1:8765** and paste the token from your local `.env` file.
The port is published only on the Docker host's loopback interface. The app
also checks the token, Host, and Origin. Don't share or commit the token.
If port 8765 is already in use, change only the left port in compose.yaml,
for example `127.0.0.1:8767:8765`, then open that port.

In the panel, set **Home network** to the physical home LAN subnet, choose an
available integration, and click **Find devices**. Container-internal subnets
such as 172.17.0.0/16 are not the TV network. Authorize pairing on the device when
ready. Samsung is implemented. LG and Sony adapters are experimental. See
[TV setup](TV_VENDORS.md) for authorization and model limits.

## Persistence and updates

The named volume `home-control_home-control-data` stores `/data/config.json`,
`/data/state` (pairing tokens and locks), and `/data/artwork`. The volume is shared
by web and MCP processes in this Compose project. Containers run as UID/GID 10001.
Named-volume ownership is initialized by the image; a custom bind mount needs
write permission for that UID. Do not make credential directories world-writable.

```sh
docker compose stop                       # stop; preserve data
docker compose start                      # resume
docker compose down                       # remove containers; preserve data
docker compose up -d --build               # rebuild after updating the checkout
```

Do not add `--volumes` to down unless you intend to erase device settings and
pairing tokens. Back up the named volume before migrations. The container does
not import an existing native installation automatically; use one active store
per home, or deliberately migrate the existing config/state with private file
permissions while both installations are stopped. Existing kill switches must
be preserved during migration.

## Networking: Linux versus Docker Desktop

The default bridge configuration works for reachable unicast LAN endpoints,
including Samsung's bounded TCP discovery. Broadcast Wake-on-LAN may not cross
the container bridge. Future multicast discovery protocols may have the same
limitation. Don't claim wake or discovery works until tested on that network.

On **Linux**, use the standalone host-network Compose file when the integration
needs home-LAN broadcasts:

```sh
docker compose down
docker compose -f compose.host.yaml up -d --build
```

It uses the same named volume and binds the web app to 127.0.0.1. There is no
published `ports` mapping in host mode. Use the same `-f compose.host.yaml` for
later commands. Never start both stacks at once. See
[Docker's host-network driver documentation](https://docs.docker.com/engine/network/drivers/host/).

On **Docker Desktop**, containers run behind a VM network. Use the default bridge
setup first; it is not equivalent to native Linux host networking. If discovery
or wake is blocked by that network, run the app natively on the home computer or
on a Linux home server. Docker Desktop's optional host networking does not imply
identical broadcast behavior. See
[Docker Desktop networking](https://docs.docker.com/desktop/features/networking/).

For private remote browser access, a Tailscale Serve proxy on the Docker host can
forward to the published localhost port. Add the exact HTTPS origin and hostname
to the container command using the `--external-origin` option only when the app
binds to loopback (the Linux host-network setup). The default bridge app binds
0.0.0.0 internally, so it intentionally rejects that option. Keep the access token.
Do not enable Tailscale Funnel or public router port forwarding.

## MCP from the same running container

An MCP client can start a separate stdio process inside the running service:

```json
{
  "mcpServers": {
    "home_control": {
      "command": "docker",
      "args": [
        "compose", "--project-directory", "/absolute/path/to/tv-remote-mcp",
        "exec", "-T", "home-control", "home-control-mcp"
      ]
    }
  }
}
```

Replace the checkout path. For host-network mode, add `-f` and the absolute path
to compose.host.yaml before `exec`. No TTY: MCP needs clean stdin/stdout. This
process shares the web panel's persisted switches and pairing tokens. Restart
MCP sessions after rebuilding. Docker daemon access is needed on that computer.

Useful local commands:

```sh
docker compose exec -T home-control home-control integrations
docker compose exec -T home-control home-control devices
docker compose exec -T home-control home-control disable all
# Explicitly re-enable only when wanted:
docker compose exec -T home-control home-control enable all
```

For a standalone MCP-only container, use the same image and volume with
`--entrypoint home-control-mcp`, `-i` (not `-t`), and no HTTP port publishing.
The web access token is for the HTTP panel; it is not Samsung's pairing token.
