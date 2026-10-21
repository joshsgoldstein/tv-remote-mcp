"""Samsung is one integration, not the platform's device model."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..control import Controller
from . import Device


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal[
        "pair",
        "key",
        "power",
        "text",
        "apps",
        "launch",
        "art_status",
        "art_mode",
        "art_list",
        "art_select",
    ]
    key: str = ""
    times: int = Field(default=1, ge=1, le=20)
    power: Literal["on", "off", "toggle"] = "on"
    text: str = Field(default="", max_length=500)
    app_id: str = Field(default="", max_length=128)
    app_type: Literal["DEEP_LINK", "NATIVE_LAUNCH"] = "DEEP_LINK"
    enabled: bool = False
    content_id: str = Field(default="", max_length=128)


ACTION_FIELDS = {
    "pair": (),
    "key": ("key", "times"),
    "power": ("power",),
    "text": ("text",),
    "apps": (),
    "launch": ("app_id", "app_type"),
    "art_status": (),
    "art_mode": ("enabled",),
    "art_list": (),
    "art_select": ("content_id",),
}
ACTION_REQUIRED = {
    "key": ["key"],
    "power": ["power"],
    "text": ["text"],
    "launch": ["app_id"],
    "art_mode": ["enabled"],
    "art_select": ["content_id"],
}


class SamsungIntegration:
    id = "samsung"
    name = "Samsung TVs & The Frame"
    action_schemas = {
        action: {
            "type": "object",
            "properties": {key: Action.model_json_schema()["properties"][key] for key in fields},
            "required": ACTION_REQUIRED.get(action, []),
            "additionalProperties": False,
        }
        for action, fields in ACTION_FIELDS.items()
    }

    def __init__(self, controller: Controller):
        self.controller = controller

    def devices(self) -> list[Device]:
        result = []
        for tv in self.controller.list_tvs():
            capabilities = ["remote", "power", "apps", "text", "pairing"]
            actions = ["pair", "key", "power", "apps", "launch", "text"]
            if tv["mac"]:
                capabilities.append("wake")
            if tv["frame"]:
                capabilities.append("art")
                actions.extend(["art_status", "art_mode", "art_list", "art_select"])
            result.append(
                Device(
                    id=tv["id"],
                    name=tv["name"],
                    category="television",
                    manufacturer="Samsung",
                    model=tv["model"],
                    enabled=tv["enabled"],
                    paired=tv["token_saved"] or tv["port"] == 8001,
                    capabilities=capabilities,
                    actions=actions,
                    details={
                        **{key: tv[key] for key in ("host", "mac", "frame", "port", "token_saved")},
                        "pairing_message": "Choose Allow for Samsung TV Remote MCP on the TV. Waiting up to 25 seconds.",
                    },
                )
            )
        return result

    def discover(self, save: bool = False) -> dict:
        return self.controller.discover(save)

    def status(self, device_id: str) -> dict:
        return self.controller.status(device_id)

    def set_enabled(self, device_id: str, enabled: bool) -> dict:
        return self.controller.store.set_enabled(enabled, device_id)

    def execute(self, device_id: str, action: str, parameters: dict) -> dict:
        if action not in ACTION_FIELDS or set(parameters) - set(ACTION_FIELDS[action]):
            raise ValueError("Unsupported parameters for this action; consult list_integrations")
        if any(key not in parameters for key in ACTION_REQUIRED.get(action, [])):
            raise ValueError("Missing required action parameters; consult list_integrations")
        if "action" in parameters:
            raise ValueError("Action must be specified separately from parameters")
        data = Action.model_validate({"action": action, **parameters})
        control = self.controller
        operations = {
            "pair": (control.pair, (device_id,)),
            "key": (control.key, (device_id, data.key, data.times)),
            "power": (control.power, (device_id, data.power)),
            "text": (control.text, (device_id, data.text)),
            "apps": (control.apps, (device_id,)),
            "launch": (control.launch, (device_id, data.app_id, data.app_type)),
            "art_status": (control.art_status, (device_id,)),
            "art_mode": (control.set_art_mode, (device_id, data.enabled)),
            "art_list": (control.list_art, (device_id,)),
            "art_select": (control.select_art, (device_id, data.content_id)),
        }
        func, args = operations[data.action]
        return func(*args)
