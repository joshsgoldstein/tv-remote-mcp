"""Common LG/Sony inventory, validation, and persistent command gate."""

import socket
from contextlib import contextmanager
from copy import deepcopy

from pydantic import Field

from ..config import TV, Store
from ..control import KEYS
from ..discovery import wake
from . import Device
from .samsung import ACTION_FIELDS, ACTION_REQUIRED, Action
from .ssdp import discover

ACTIONS = ("pair", "key", "power", "apps", "launch", "text")
KEY_ALIASES = {value: key for key, value in KEYS.items()}


class TVAction(Action):
    app_id: str = Field(default="", max_length=2048)


class NetworkIntegration:
    id = ""
    name = ""
    manufacturer = ""
    supported_actions = ACTIONS
    pairing_message = ""
    action_schemas = {
        action: {
            "type": "object",
            "properties": {
                key: TVAction.model_json_schema()["properties"][key]
                for key in ACTION_FIELDS[action]
            },
            "required": ACTION_REQUIRED.get(action, []),
            "additionalProperties": False,
        }
        for action in ACTIONS
    }

    def __init__(self, store: Store):
        self.store = store
        self.action_schemas = deepcopy(self.action_schemas)
        self.action_schemas["power"]["properties"]["power"]["enum"] = ["on", "off"]
        self.action_schemas["key"]["properties"]["key"]["enum"] = list(self.keys)

    def record(self, device_id, command=False):
        return self.store.network_tv(self.id, device_id, command=command)

    def devices(self):
        result = []
        for tv in self.store.load().devices:
            if tv.integration != self.id:
                continue
            credential = self.store.credential(self.id, tv.id)
            caps = ["remote", "power", "apps", "pairing"]
            if "text" in self.supported_actions:
                caps.append("text")
            if tv.mac or self.id == "sony_bravia":
                caps.append("wake")
            result.append(
                Device(
                    id=tv.id,
                    name=tv.name,
                    manufacturer=self.manufacturer,
                    category="television",
                    model=tv.model,
                    enabled=tv.enabled,
                    paired=bool(credential),
                    capabilities=caps,
                    actions=list(self.supported_actions),
                    details={
                        "host": tv.host,
                        "mac": tv.mac,
                        "port": tv.port,
                        "auth": "psk" if self.id == "sony_bravia" else "prompt",
                        "wake_method": "wol" if tv.mac else "network",
                        "wake_requires_pairing": not bool(tv.mac),
                        "keys": list(self.keys),
                        "experimental": True,
                        "pairing_message": self.pairing_message,
                    },
                )
            )
        return result

    def discover(self, save=False):
        found = discover(self.store.load().subnet, self.id)
        if save:
            self.store.merge_network(found)
        return {"found": [tv.model_dump() for tv in found], "saved": save}

    def status(self, device_id):
        # Opening a TCP socket does not register, pair, wake, or send a command.
        tv = self.record(device_id)
        try:
            with socket.create_connection((tv.host, tv.port), timeout=2):
                reachable = True
        except OSError:
            reachable = False
        return {
            "reachable": reachable,
            "power": None,
            "note": "TCP reachability only. Power and identity are not confirmed.",
        }

    def set_enabled(self, device_id, enabled):
        return self.store.set_network_enabled(self.id, device_id, enabled)

    @contextmanager
    def gate(self, device_id):
        # Direct adapter callers must enforce switches too, including pairing and wake.
        self.record(device_id, command=True)  # Validate identity before constructing a lock path.
        with self.store.lock(f"{self.id}-{device_id}"):
            yield self.record(device_id, command=True)

    def validate(self, action, parameters):
        allowed = set(ACTION_FIELDS.get(action, ()))
        if self.id == "sony_bravia" and action == "pair":
            allowed.add("psk")
        if action not in self.supported_actions or set(parameters) - allowed:
            raise ValueError("Unsupported action or parameters. Check list_integrations.")
        if any(key not in parameters for key in ACTION_REQUIRED.get(action, [])):
            raise ValueError("Missing required action parameters")
        data = TVAction.model_validate(
            {"action": action, **{k: v for k, v in parameters.items() if k != "psk"}}
        )
        if action == "power" and data.power == "toggle":
            raise ValueError("Use explicit power on or off for this integration")
        if action == "key":
            data.key = KEY_ALIASES.get(data.key, data.key.lower())
            if data.key not in self.keys:
                raise ValueError("This integration does not support that remote key")
        if action == "launch" and not data.app_id.strip():
            raise ValueError("App ID is required")
        if action == "text" and not data.text:
            raise ValueError("Text is required")
        return data

    def wake(self, tv):
        # Reuse the bounded private-subnet WOL implementation. No TV auth is needed.
        self.record(tv.id, command=True)
        return wake(TV(id=tv.id, name=tv.name, host=tv.host, mac=tv.mac), self.store.load().subnet)

    def identity(self, tv, identity):
        if not identity or (tv.device_id and tv.device_id != identity):
            raise ValueError(
                "TV identity could not be verified. Check the saved address before pairing again."
            )
