# A smart-home platform, with adapters per protocol

Home Control's goal is one web dashboard and assistant interface for the home's
devices. Samsung is the first integration, not the boundary of the product.
Televisions, thermostats, lights, plugs, and other categories can share inventory,
authorization state, routing, and persistent control switches. Their controls
and pairing flows remain capability-specific.

## What is implemented

- `integrations.Integration`: the adapter contract.
- `integrations.Device`: public device identity, category, manufacturer,
  capabilities, actions, enabled/paired state, and non-secret display details.
- `home.Home`: registry, qualified device IDs, discovery/status/action routing,
  and shared master/per-device checks immediately before adapter execution.
- `integrations.samsung.SamsungIntegration`: adapter around the existing Samsung
  controller, including validated action parameters and schemas for assistants.
- Generic MCP tools: list_integrations, list_devices, discover_devices,
  device_status, and device_action. Existing Samsung tools continue working.
- Generic web routes under `/api/devices/{integration:id}/` and
  `/api/integrations/{integration_id}/discover`. The dashboard reads the shared
  inventory and shows controls according to capabilities.

The current registration includes Samsung only. LG, Sony, and ecobee entries in
the catalog are **planned**, not runnable stubs. A planned integration request
fails before contacting a device. Installation requires reviewed adapter code;
there is no runtime download or arbitrary plugin execution endpoint.

## Why separate adapters

| Integration | Device interface | Status in this repository |
| --- | --- | --- |
| Samsung | Local Samsung WebSocket remote and Frame art channels via samsungtvws; on-screen pairing | Implemented; physical command validation pending pairing |
| LG webOS | webOS SSAP over WebSockets with its own pairing/client key | Planned |
| Sony BRAVIA | Model-dependent Sony REST APIs and IRCC-IP remote commands; device-specific authentication | Planned |
| ecobee | Separate thermostat authorization/API and thermostat capabilities | Planned; establish an available access route first |

Sources: [Samsung library](https://github.com/xchwarze/samsung-tv-ws-api),
[LG client implementation](https://github.com/home-assistant-libs/aiowebostv),
[Sony REST specifications](https://pro-bravia.sony.net/remote-display-control/rest-api/structure/),
[Sony IRCC-IP](https://pro-bravia.sony.net/remote-display-control/ircc-ip/),
[ecobee developer access](https://www.ecobee.com/en-us/developers/).
Sony's cited documentation covers BRAVIA Professional Displays; verify the actual
consumer model's APIs before implementing. Neither manufacturer nor operating
system alone guarantees a capability. ecobee currently reports that new developer
registrations are unavailable; recheck before choosing an integration route.

## Contract

Each adapter supplies `id`, `name`, `action_schemas`, and these methods:

```python
def devices() -> list[Device]: ...
def discover(save: bool = False) -> dict: ...
def status(device_id: str) -> dict: ...
def execute(device_id: str, action: str, parameters: dict) -> dict: ...
def set_enabled(device_id: str, enabled: bool) -> dict: ...
```

`devices()` reads local inventory only. It must return the current persisted
per-device switch every time; never cache enabled state across requests.
`set_enabled()` persists locally without a network command. Use the shared
Store's config lock when updating state. The Home registry owns the shared
master switch and re-reads it after obtaining the command lock. All adapter
commands, including pairing and wake, must run through `Home.execute()`.
Any legacy/direct entry point must enforce the same switches (the existing
Samsung controller already does). No MCP tool may re-enable a switch.

IDs such as `samsung:frame` and `lg_webos:living_room` prevent collisions between
adapters. Native IDs are stable local identifiers, not IP addresses or credentials.
Credentials stay in private local state and must never appear in Device.details,
status responses, action schemas, errors, or logs.

Capabilities describe control groups (`remote`, `power`, `apps`, `text`, `art`,
`pairing`, `wake`); actions name exact operations. Advertise only what this device
can support, and check model/firmware when discovering or connecting. A potential
capability is not a guarantee of successful command delivery. Vendor extensions
such as Frame art stay separate; don't make thermostats implement TV methods.

`action_schemas` maps action names to JSON Schemas for their parameters. Enforce
those shapes inside the adapter; the schema isn't validation by itself. Common
TV actions should use the same parameters across adapters (e.g. `power` with
`{"power":"off"}`, `apps` with `{}`, `launch` with `{"app_id":"..."}`).
Never infer support from a brand name or silently substitute another operation.

Pairing is explicit. Listing/status must not open an authorization prompt.
Return `command_sent` for delivery without confirmed physical state; return
reported state separately when the vendor can read it. Never assume a toggle
is idempotent. Missing/unreachable means unknown rather than off.

## Add an integration

1. Confirm the protocol and authentication for real target models. Implement the
   contract in a separate module. Keep credentials in private local storage.
2. Define validated, persistent configuration for its devices; preserve existing
   Samsung records, token IDs, and switches. The current `tvs` config collection
   remains the Samsung adapter's storage, not a template for every future device.
3. Register the adapter explicitly in `create_home`. Its available catalog entry
   automatically replaces the corresponding planned entry.
4. Supply capability and parameter schemas. Reuse common UI controls where the
   semantics match. Add category-specific widgets for new capabilities; do not
   shoehorn temperature setpoints into a TV remote. The generic fallback currently
   displays metadata and directs users to the advertised assistant actions.
5. Add contract tests with synthetic devices: ID collisions, unsupported actions,
   authentication failures, persistent per-device/master switches, queued requests,
   read-only discovery/status, and no leaked credentials. Test both web and MCP.
6. Validate supported operations on authorized hardware before claiming support.

The package, config directory, and repository retain their original `tv-remote-mcp`
identifiers for existing installations. New `home-control`, `home-control-web`,
and `home-control-mcp` entry points are aliases; existing commands remain valid.
