# Instructions for coding and setup agents

This is Home Control, a general smart-home control plane with MCP and a web dashboard.
Samsung TVs are the first integration, not the product boundary.
Read README.md and docs/AGENT_SETUP.md before setting it up for someone.
Before deployment, follow the user interview in docs/AGENT_SETUP.md: establish
where it runs, temporary laptop versus always-on availability, native versus
Docker installation, and dashboard/MCP preferences. Reuse answers already given;
do not silently choose a host, background service, or installation method.
Use docs/LAPTOP.md for occasional laptop sessions. Architecture is documented in
docs/HOW_IT_WORKS.md.

## Boundaries

- Run the server on a Linux/macOS computer on the TV's home LAN. SSH and Tailscale
  are optional transports; do not assume the user has either.
- Build new device support through the Integration contract in docs/INTEGRATIONS.md.
  Samsung is implemented. LG webOS and Sony BRAVIA PSK adapters are experimental.
  Read docs/TV_VENDORS.md before setting them up. Other devices are not implemented.
  Do not claim unimplemented adapters work or improvise device commands.
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

## Writing for users

Use ASD-STE100 Simplified Technical English as inspiration, not a compliance claim.
Use short sentences and common words. Give one action per instruction.
Use the same name for the same thing. Do not use em dashes.
Keep README.md short. Put detailed procedures in the linked docs.
Keep deployment choices in docs/AGENT_SETUP.md. Do not skip the user interview.

## Development

Python 3.10+, uv with uv.lock. UI is static HTML/CSS/JS packaged in
src/tv_remote_mcp/static; no Node build or external assets are needed.
The web, CLI, and MCP share Home, Integration adapters, and Store. Samsung retains
its Controller for backward compatibility. Keep validation and kill-switch
enforcement in the shared backend, not only in frontend disabled buttons.

Run `uv sync --locked`, `uv run pytest -q`, `uv run ruff check src tests scripts`,
`uv run ruff format --check src tests scripts`, `node --check src/tv_remote_mcp/static/app.js`
(if Node is available), `sh -n scripts/connect.sh scripts/deploy.sh`, and `uv build`.
Tests must use temporary stores and synthetic devices; never a home inventory.
`PYTHONPATH=src uv run python tests/preview_web.py` starts a sample-device panel
on localhost:8766 for browser QA; label it a demo and stop it after use.

For Docker changes, read docs/DOCKER.md, build the image, and run scripts/container_smoke.py
inside an isolated container with an empty inventory. Verify persistence after restart.
Never run that smoke script against a user's existing device store.

Before publishing, inspect staged files for private state, verify the wheel
contains the static assets, and distinguish tested, deployed, and pending work.
