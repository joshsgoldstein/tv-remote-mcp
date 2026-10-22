"""Experimental BRAVIA JSON-RPC and IRCC adapter, with explicit PSK setup."""

import json
import re
import ssl
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .network_tv import NetworkIntegration
from .ssdp import NoRedirect


class SonyClient:
    def __init__(self, tv, psk):
        self.tv = tv
        self.psk = psk

    def post(self, path, data, headers=None):
        scheme = "https" if self.tv.port == 443 else "http"
        opener = build_opener(
            ProxyHandler({}), NoRedirect(), HTTPSHandler(context=ssl._create_unverified_context())
        )
        request = Request(
            f"{scheme}://{self.tv.host}:{self.tv.port}/sony/{path}",
            data=data,
            headers={"X-Auth-PSK": self.psk, **(headers or {})},
        )
        try:
            self.guard()
            with opener.open(request, timeout=5) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise RuntimeError("Sony response exceeded the size limit")
            return raw
        except OSError:
            raise RuntimeError(
                "Sony connection or authorization failed. Check the TV's IP control settings and saved key."
            ) from None

    def rpc(self, service, method, params=None):
        raw = self.post(
            service,
            json.dumps(
                {"method": method, "params": params or [], "id": 1, "version": "1.0"}
            ).encode(),
            {"Content-Type": "application/json"},
        )
        try:
            data = json.loads(raw)
            if "error" in data or not isinstance(data.get("result"), list):
                raise RuntimeError(
                    "Sony rejected this API call. Check model support and authorization."
                )
            return data["result"]
        except (ValueError, TypeError, AttributeError):
            raise RuntimeError("Sony returned an invalid API response") from None

    def identity(self):
        info = self.rpc("system", "getSystemInformation")[0]
        return str(info.get("serial") or info.get("macAddr") or "")

    def button(self, code):
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9+/=]{1,128}", code):
            raise RuntimeError("Sony returned an invalid remote-control code")
        xml = (
            '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            '<s:Body><u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">'
            f"<IRCCCode>{code}</IRCCCode></u:X_SendIRCC></s:Body></s:Envelope>"
        )
        self.post(
            "IRCC",
            xml.encode(),
            {
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPACTION": '"urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"',
            },
        )


class SonyIntegration(NetworkIntegration):
    id = "sony_bravia"
    name = "Sony BRAVIA (experimental)"
    manufacturer = "Sony"
    supported_actions = ("pair", "key", "power", "apps", "launch")
    pairing_message = "Enable IP control and pre-shared-key authentication on the Sony TV. Enter that key in the secure setup dialog. PIN pairing is not implemented."
    keys = {
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "enter": "Confirm",
        "back": "Return",
        "home": "Home",
        "menu": "Options",
        "exit": "Exit",
        "source": "Input",
        "guide": "GGuide",
        "info": "Display",
        "volume_up": "VolumeUp",
        "volume_down": "VolumeDown",
        "mute": "Mute",
        "channel_up": "ChannelUp",
        "channel_down": "ChannelDown",
        "play": "Play",
        "pause": "Pause",
        "stop": "Stop",
        "rewind": "Rewind",
        "forward": "Forward",
        "red": "Red",
        "green": "Green",
        "yellow": "Yellow",
        "blue": "Blue",
        **{str(i): f"Num{i}" for i in range(10)},
    }
    action_schemas = {k: v for k, v in NetworkIntegration.action_schemas.items() if k != "text"}
    action_schemas["pair"] = {
        "type": "object",
        "properties": {
            "psk": {
                "type": "string",
                "format": "password",
                "writeOnly": True,
                "minLength": 1,
                "maxLength": 128,
            }
        },
        "required": [],
        "additionalProperties": False,
    }

    def execute(self, device_id, action, parameters):
        data = self.validate(action, parameters)
        with self.gate(device_id) as tv:
            if action == "power" and data.power == "on" and tv.mac:
                return self.wake(tv)
            credential = self.store.credential(self.id, device_id)
            psk = (
                parameters.get("psk", credential.get("psk"))
                if action == "pair"
                else credential.get("psk")
            )
            if not isinstance(psk, str) or not re.fullmatch(r"[\x20-\x7e]{1,128}", psk):
                if action == "power" and data.power == "on" and tv.mac:
                    return self.wake(tv)
                raise ValueError(
                    "Enter the Sony TV's pre-shared key using the setup dialog or device-pair CLI"
                )
            client = SonyClient(tv, psk)
            client.guard = lambda: self.record(device_id, command=True)
            try:
                identity = client.identity()
                self.identity(tv, identity)
                self.record(device_id, command=True)
                if action == "pair":
                    self.store.save_credential(self.id, device_id, {"psk": psk}, identity)
                    return {"status": "connected", "token_saved": True}
                if action == "power":
                    if data.power == "on" and tv.mac:
                        return self.wake(tv)
                    client.rpc("system", "setPowerStatus", [{"status": data.power == "on"}])
                elif action == "key":
                    codes = {
                        item["name"]: item["value"]
                        for item in client.rpc("system", "getRemoteControllerInfo")[1]
                    }
                    code = codes.get(self.keys[data.key])
                    if code is None:
                        raise ValueError("This Sony TV does not advertise that remote key")
                    for _ in range(data.times):
                        self.record(device_id, command=True)
                        client.button(code)
                elif action in ("apps", "launch"):
                    apps = client.rpc("appControl", "getApplicationList")[0]
                    if action == "apps":
                        return {
                            "apps": [
                                {"app_id": item["uri"], "name": item.get("title", item["uri"])}
                                for item in apps
                                if item.get("uri")
                            ]
                        }
                    if not any(item.get("uri") == data.app_id for item in apps):
                        raise ValueError("Use an app ID returned by this TV's apps action")
                    self.record(device_id, command=True)
                    client.rpc("appControl", "setActiveApp", [{"uri": data.app_id}])
            except (KeyError, IndexError, TypeError):
                raise RuntimeError(
                    "Sony returned an unsupported API response. Check model compatibility."
                ) from None
            return {"status": "command_sent"}
