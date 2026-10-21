# Instructions for coding and setup agents

This is a local Samsung TV controller with an MCP server and a browser panel.
Read README.md and docs/AGENT_SETUP.md before setting it up for someone.

## Boundaries

- Run the server on a Linux/macOS computer on the TV's home LAN. SSH and Tailscale
  are optional transports; do not assume the user has either.
- Support Samsung TVs and The Frame only. Other devices, including ecobee, are
  future integrations; do not claim they work or improvise thermostat commands.
- Never bypass a device or master kill switch. Re-enable only when the user asks.
  New integrations must enforce both switches in their shared controller,
  including wake, pairing, and all command paths, with persistent state.
- Preserve existing config, tokens, TV IDs, MCP client entries, and server services.
- Never commit real device addresses/IDs/MACs, pairing tokens, private hostnames,
  logs with personal data, or screenshots of a user's real device inventory.
- Do not expose the panel publicly. Default to localhost. Private remote access
  is optional and must be explicitly requested; never enable Tailscale Funnel.
- Pair only when someone is ready to choose Allow on the TV. Do not retry
  endlessly. Report installation as complete and pairing as pending if absent.
- Commands are requests, not proof of physical state. Do not claim mocked tests
  verified real hardware. Do not send test power/volume/artwork commands without
  the user's request. Status reads and inventory checks are appropriate setup checks.

## Development

Python 3.10+, uv with uv.lock. UI is static HTML/CSS/JS packaged in
src/tv_remote_mcp/static; no Node build or external assets are needed.
The web, CLI, and MCP entry points share Controller and Store. Keep validation
and enforcement there, not only in frontend disabled buttons.

Run `uv sync --locked`, `uv run pytest -q`, `uv run ruff check src tests scripts`,
`uv run ruff format --check src tests scripts`, `node --check src/tv_remote_mcp/static/app.js`
(if Node is available), `sh -n scripts/connect.sh scripts/deploy.sh`, and `uv build`.
Tests must use temporary stores and synthetic devices; never a home inventory.
`PYTHONPATH=src uv run python tests/preview_web.py` starts a sample-device panel
on localhost:8766 for browser QA; label it a demo and stop it after use.

Before publishing, inspect staged files for private state, verify the wheel
contains the static assets, and distinguish tested, deployed, and pending work.
