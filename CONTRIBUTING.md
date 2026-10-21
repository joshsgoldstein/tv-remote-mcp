# Contributing

Start with an issue describing the TV model, firmware version, expected behavior,
and what actually happened. Do not include pairing tokens, private network
inventories, MAC addresses, or unredacted debug logs.

## Development

Python 3.10+ on Linux or macOS is required. The server uses POSIX file locks.

```sh
uv sync --locked
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv build
```

Unit tests mock the TVs and require no hardware. For an optional real MCP session
over SSH, deploy to your own home host and run:

```sh
python3 scripts/smoke.py --host tv-home --tv-id frame
```

This test reads status and verifies rejection of an unsupported key. It does not
pair, wake, switch off, or change content on a TV.

Keep fixes focused, add regression tests for behavior changes, and distinguish
mock verification from results observed on real hardware. Compatibility reports
for Samsung models and Frame Art Mode are especially useful.

After changing dependencies, update the lockfile and pip export together:

```sh
uv lock
uv export --format requirements-txt --no-dev --no-emit-project --no-hashes -o requirements.txt
```

## Browser panel and device switches

Read [AGENTS.md](AGENTS.md) and the [setup runbook](docs/AGENT_SETUP.md) when improving onboarding. Use `PYTHONPATH=src uv run python tests/preview_web.py` for a synthetic two-TV preview at http://127.0.0.1:8766. It never controls hardware. Stop it after testing. Check desktop and mobile layouts and `node --check src/tv_remote_mcp/static/app.js` after UI changes. Keep screenshots synthetic. Kill switches must be enforced by the shared controller, including Wake-on-LAN and commands waiting on locks; frontend disabled buttons alone are insufficient.

## Integration architecture

Home Control is a general smart-home platform. Read [the adapter contract](docs/INTEGRATIONS.md) before adding a vendor or device type. Samsung is the first integration; keep vendor protocols inside adapters and shared inventory, capability routing, and kill switches in Home. Mark new integrations planned until implemented, and distinguish mocked tests from real hardware verification.
