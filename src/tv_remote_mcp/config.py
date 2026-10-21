from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    controls_enabled: bool = True
    subnet: str = "192.168.1.0/24"
    tvs: list[TV] = Field(default_factory=list)

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
