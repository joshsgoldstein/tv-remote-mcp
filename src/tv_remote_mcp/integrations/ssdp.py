"""Bounded read-only UPnP discovery for LG and Sony TVs."""

import socket
import xml.etree.ElementTree as ET
from ipaddress import IPv4Address, IPv4Network
from time import monotonic
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from ..config import NetworkTV, Settings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def description(location: str, sender: str, subnet: str) -> NetworkTV | None:
    url = urlsplit(location)
    network = IPv4Network(subnet)
    if (
        url.scheme != "http"
        or url.hostname != sender
        or IPv4Address(sender) not in network
        or url.port not in (None, 80, 8080, 52323)
        or url.username
        or url.password
        or url.fragment
    ):
        return None
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(location, timeout=1) as response:
        data = response.read(65537)
    if len(data) > 65536 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        return None
    root = ET.fromstring(data)
    values = {node.tag.rsplit("}", 1)[-1]: node.text or "" for node in root.iter()}
    manufacturer = values.get("manufacturer", "").lower()
    if "lg" in manufacturer and "mediarenderer" in values.get("deviceType", "").lower():
        integration, identifier, port = "lg_webos", "lg", 3001
    elif "sony" in manufacturer and "mediarenderer" in values.get("deviceType", "").lower():
        integration, identifier, port = "sony_bravia", "sony", 80
    else:
        return None
    return NetworkTV(
        integration=integration,
        id=identifier,
        name=values.get("friendlyName") or identifier.upper(),
        host=sender,
        port=port,
        model=values.get("modelName"),
        discovery_id=values.get("UDN"),
    )


def discover(subnet: str, integration: str) -> list[NetworkTV]:
    Settings(subnet=subnet)
    deadline = monotonic() + 4
    locations, found = set(), {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.3)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        message = (
            "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
            'MAN: "ssdp:discover"\r\nMX: 2\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n'
        )
        sock.sendto(message.encode(), ("239.255.255.250", 1900))
        for _ in range(128):
            if monotonic() >= deadline:
                break
            try:
                data, (sender, _) = sock.recvfrom(8192)
            except socket.timeout:
                continue
            for line in data.decode("utf-8", errors="replace").splitlines():
                if line.lower().startswith("location:"):
                    location = line.split(":", 1)[1].strip()
                    if location in locations or len(locations) >= 16:
                        continue
                    locations.add(location)
                    try:
                        tv = description(location, sender, subnet)
                        if tv and tv.integration == integration:
                            found[tv.host] = tv
                    except (OSError, ValueError, ET.ParseError):
                        continue
    result = sorted(found.values(), key=lambda tv: tv.host)
    for number, tv in enumerate(result, 1):
        tv.id = ("lg" if integration == "lg_webos" else "sony") + (
            f"-{number}" if number > 1 else ""
        )
    return result
