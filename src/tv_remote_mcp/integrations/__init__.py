"""Integration contracts for Home Control. Adapters own vendor-specific protocols."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class Device(BaseModel):
    """Public inventory only. Credentials must never be put in this model."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")
    name: str
    category: str
    manufacturer: str
    model: str | None = None
    enabled: bool = True
    paired: bool = False
    capabilities: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    # Non-secret, integration-specific display fields (e.g. LAN address).
    details: dict = Field(default_factory=dict)


class Integration(Protocol):
    id: str
    name: str
    action_schemas: dict[str, dict]

    def devices(self) -> list[Device]:
        """Read saved inventory locally. Never trigger pairing or network commands."""
        ...

    def discover(self, save: bool = False) -> dict: ...
    def status(self, device_id: str) -> dict: ...
    def execute(self, device_id: str, action: str, parameters: dict) -> dict: ...
    def set_enabled(self, device_id: str, enabled: bool) -> dict:
        """Persist the device switch locally. Never send a physical command."""
        ...
