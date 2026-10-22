from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TV(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")
    name: str
    host: str
    mac: str | None = None
    device_id: str | None = None
    model: str | None = None
    enabled: bool = True
    frame: bool = False
    port: int = Field(default=8002)

    @field_validator("host")
    @classmethod
    def valid_host(cls, value: str) -> str:
        ip = IPv4Address(value)
        if not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            raise ValueError("TV host must be a private LAN IPv4 address")
        return str(ip)

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if value not in (8001, 8002):
            raise ValueError("Samsung WebSocket port must be 8001 or 8002")
        return value

    @field_validator("mac")
    @classmethod
    def valid_mac(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.replace("-", ":").upper()
        if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", value):
            raise ValueError("Invalid MAC address")
        if value == "00:00:00:00:00:00" or int(value[:2], 16) & 1:
            raise ValueError("MAC must be a unicast device address")
        return value


class NetworkTV(BaseModel):
    """LG/Sony inventory. Secrets live in separate private files."""

    model_config = ConfigDict(extra="forbid")
    integration: Literal["lg_webos", "sony_bravia"]
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")
    name: str = Field(min_length=1, max_length=100)
    host: str
    port: int = Field(default=3001)
    mac: str | None = None
    model: str | None = None
    discovery_id: str | None = None
    device_id: str | None = None
    enabled: bool = True

    _host = field_validator("host")(TV.valid_host.__func__)
    _mac = field_validator("mac")(TV.valid_mac.__func__)

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if value not in (80, 443, 3000, 3001):
            raise ValueError("Use port 3000/3001 for LG or 80/443 for Sony")
        return value

    @model_validator(mode="after")
    def integration_port(self):
        if self.port not in ((3000, 3001) if self.integration == "lg_webos" else (80, 443)):
            raise ValueError("Device port does not match the integration")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    controls_enabled: bool = True
    subnet: str = "192.168.1.0/24"
    tvs: list[TV] = Field(default_factory=list)
    devices: list[NetworkTV] = Field(default_factory=list)

    @field_validator("subnet")
    @classmethod
    def valid_subnet(cls, value: str) -> str:
        network = IPv4Network(value, strict=True)
        if not network.is_private or network.prefixlen < 24 or network.is_loopback:
            raise ValueError("Discovery requires a private IPv4 subnet of /24 or smaller")
        return str(network)

    @field_validator("tvs")
    @classmethod
    def unique_tvs(cls, value: list[TV]) -> list[TV]:
        if len({tv.id for tv in value}) != len(value):
            raise ValueError("TV IDs must be unique")
        return value

    @field_validator("devices")
    @classmethod
    def unique_devices(cls, value: list[NetworkTV]) -> list[NetworkTV]:
        if len({(d.integration, d.id) for d in value}) != len(value):
            raise ValueError("Device IDs must be unique within each integration")
        if any(
            d.port not in ((3000, 3001) if d.integration == "lg_webos" else (80, 443))
            for d in value
        ):
            raise ValueError("Device port does not match the integration")
        return value


class Store:
    def __init__(self, path: Path | None = None):
        self.path = (
            path
            or Path(
                os.environ.get("TV_REMOTE_CONFIG", "~/.config/tv-remote-mcp/config.json")
            ).expanduser()
        )
        self.state = Path(os.environ.get("TV_REMOTE_STATE", str(self.path.parent / "state")))

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        return Settings.model_validate_json(self.path.read_text())

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".config-")
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(settings.model_dump_json(indent=2) + "\n")
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def tv(self, tv_id: str) -> TV:
        settings = self.load()
        for tv in settings.tvs:
            if tv.id == tv_id:
                return tv
        raise ValueError(f"Unknown TV {tv_id!r}. Use list_tvs or discover_tvs first.")

    def set_enabled(self, enabled: bool, tv_id: str | None = None) -> dict:
        with self.lock("config"):
            settings = self.load()
            if tv_id is None:
                settings.controls_enabled = enabled
            else:
                tv = next((tv for tv in settings.tvs if tv.id == tv_id), None)
                if tv is None:
                    raise ValueError(f"Unknown TV {tv_id!r}")
                tv.enabled = enabled
            self.save(settings)
        return {"tv": tv_id, "enabled": enabled}

    def require_enabled(self, tv_id: str) -> TV:
        settings = self.load()
        tv = next((tv for tv in settings.tvs if tv.id == tv_id), None)
        if tv is None:
            raise ValueError(f"Unknown TV {tv_id!r}")
        if not settings.controls_enabled or not tv.enabled:
            raise ValueError(
                "Device controls are disabled by a kill switch. Re-enable in the web panel or local CLI."
            )
        return tv

    def network_tv(self, integration: str, device_id: str, *, command: bool = False) -> NetworkTV:
        settings = self.load()
        for device in settings.devices:
            if device.integration == integration and device.id == device_id:
                if command and (not settings.controls_enabled or not device.enabled):
                    raise ValueError("Device controls are disabled by a kill switch")
                return device
        raise ValueError("Unknown device. Discover it or add its IP address first.")

    def set_network_enabled(self, integration: str, device_id: str, enabled: bool) -> dict:
        with self.lock("config"):
            settings = self.load()
            device = next(
                (d for d in settings.devices if d.integration == integration and d.id == device_id),
                None,
            )
            if device is None:
                raise ValueError("Unknown device")
            device.enabled = enabled
            self.save(settings)
        return {"id": f"{integration}:{device_id}", "enabled": enabled}

    def merge_network(self, found: list[NetworkTV]) -> list[NetworkTV]:
        with self.lock("config"):
            settings = self.load()
            for device in found:
                existing = next(
                    (
                        d
                        for d in settings.devices
                        if d.integration == device.integration
                        and (
                            (device.discovery_id and d.discovery_id == device.discovery_id)
                            or d.host == device.host
                        )
                    ),
                    None,
                )
                if existing:
                    existing.host = device.host
                    existing.discovery_id = device.discovery_id or existing.discovery_id
                    existing.model = device.model or existing.model
                    existing.mac = device.mac or existing.mac
                else:
                    used = {d.id for d in settings.devices if d.integration == device.integration}
                    base, count = device.id, 2
                    while device.id in used:
                        device = device.model_copy(update={"id": f"{base[:40]}-{count}"})
                        count += 1
                    settings.devices.append(device)
            self.save(settings)
            return settings.devices

    def credential_path(self, integration: str, device_id: str) -> Path:
        self.network_tv(integration, device_id)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        return self.state / f"{integration}-{device_id}.credential.json"

    def credential(self, integration: str, device_id: str) -> dict:
        path = self.credential_path(integration, device_id)
        return json.loads(path.read_text()) if path.exists() else {}

    def save_credential(self, integration: str, device_id: str, data: dict, identity: str) -> None:
        path = self.credential_path(integration, device_id)
        fd, name = tempfile.mkstemp(dir=self.state, prefix=".credential-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
        with self.lock("config"):
            settings = self.load()
            for device in settings.devices:
                if device.integration == integration and device.id == device_id:
                    device.device_id = identity
            self.save(settings)

    def token_path(self, tv: TV) -> Path:
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        return self.state / f"{tv.id}.token"

    @contextmanager
    def lock(self, name: str):
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state / f"{name}.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def merge(self, discovered: list[TV]) -> list[TV]:
        with self.lock("config"):
            settings = self.load()
            for found in discovered:
                existing = next(
                    (
                        tv
                        for tv in settings.tvs
                        if (
                            (found.device_id and tv.device_id == found.device_id)
                            or (found.mac and tv.mac == found.mac)
                            or (not tv.device_id and not tv.mac and tv.host == found.host)
                        )
                    ),
                    None,
                )
                if existing:
                    # Keep friendly names and token identity when DHCP changes the IP.
                    replacement = found.model_copy(
                        update={
                            "id": existing.id,
                            "name": existing.name,
                            "enabled": existing.enabled,
                        }
                    )
                    settings.tvs[settings.tvs.index(existing)] = replacement
                else:
                    used = {tv.id for tv in settings.tvs}
                    base, number = found.id, 2
                    while found.id in used:
                        found = found.model_copy(update={"id": f"{base}-{number}"})
                        number += 1
                    settings.tvs.append(found)
            self.save(settings)
            return settings.tvs

    def public(self, tv: TV) -> dict:
        token = self.token_path(tv)
        return {
            **json.loads(tv.model_dump_json()),
            "token_saved": token.exists() and token.stat().st_size > 0,
        }
