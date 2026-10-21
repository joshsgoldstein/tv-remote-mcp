"""Vendor-neutral routing shared by web and MCP. Integrations are explicit code registrations."""

from __future__ import annotations

import hashlib
import re

from .config import Store
from .control import Controller
from .integrations import Device, Integration
from .integrations.samsung import SamsungIntegration

# Roadmap entries are visible but cannot be invoked as installed integrations.
PLANNED = (
    {"id": "lg_webos", "name": "LG webOS", "status": "planned"},
    {"id": "sony_bravia", "name": "Sony BRAVIA", "status": "planned"},
    {"id": "ecobee", "name": "ecobee thermostats", "status": "planned"},
)


class Home:
    def __init__(self, store: Store, integrations: list[Integration]):
        self.store = store
        self.integrations = {}
        for integration in integrations:
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", integration.id):
                raise ValueError("Invalid integration ID")
            if integration.id in self.integrations:
                raise ValueError("Duplicate integration ID")
            self.integrations[integration.id] = integration

    def catalog(self) -> list[dict]:
        return [
            {
                "id": item.id,
                "name": item.name,
                "status": "available",
                "action_schemas": item.action_schemas,
            }
            for item in self.integrations.values()
        ] + [item for item in PLANNED if item["id"] not in self.integrations]

    def integration(self, integration_id: str) -> Integration:
        if integration_id not in self.integrations:
            raise ValueError(f"Integration {integration_id!r} is not installed")
        return self.integrations[integration_id]

    def resolve(self, device_id: str) -> tuple[Integration, Device]:
        integration_id, separator, native_id = device_id.partition(":")
        if not separator:
            raise ValueError("Use a qualified device ID from list_devices, such as samsung:frame")
        integration = self.integration(integration_id)
        devices = integration.devices()
        if len({item.id for item in devices}) != len(devices):
            raise ValueError("Integration returned duplicate device IDs")
        for device in devices:
            if device.id == native_id:
                return integration, device
        raise ValueError(f"Unknown device {device_id!r}")

    def devices(self) -> list[dict]:
        result = []
        for integration in self.integrations.values():
            for device in integration.devices():
                result.append(
                    {
                        **device.model_dump(),
                        "id": f"{integration.id}:{device.id}",
                        "native_id": device.id,
                        "integration": integration.id,
                    }
                )
        if len({item["id"] for item in result}) != len(result):
            raise ValueError("Integration returned duplicate device IDs")
        return result

    def status(self, device_id: str) -> dict:
        integration, device = self.resolve(device_id)
        return {**integration.status(device.id), "id": device_id, "integration": integration.id}

    def discover(self, integration_id: str, save: bool = False) -> dict:
        return self.integration(integration_id).discover(save)

    def set_enabled(self, device_id: str, enabled: bool) -> dict:
        integration, device = self.resolve(device_id)
        return integration.set_enabled(device.id, enabled)

    def execute(self, device_id: str, action: str, parameters: dict) -> dict:
        # The per-device gate is rechecked after waiting, before any adapter call.
        lock = "home-" + hashlib.sha256(device_id.encode()).hexdigest()
        with self.store.lock(lock):
            integration, device = self.resolve(device_id)
            if not self.store.load().controls_enabled or not device.enabled:
                raise ValueError("Device controls are disabled by a kill switch")
            if action not in device.actions:
                raise ValueError(f"Action {action!r} is not supported by this device")
            return integration.execute(device.id, action, parameters)


def create_home(controller: Controller | None = None) -> Home:
    controller = controller or Controller()
    return Home(controller.store, [SamsungIntegration(controller)])
