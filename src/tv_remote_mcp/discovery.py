from __future__ import annotations

import html
import json
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from ipaddress import IPv4Network
from urllib.error import URLError
from urllib.request import HTTPSHandler, ProxyHandler, build_opener

from .config import TV, Settings


def device_info(host: str, timeout: float = 2, port: int = 8001) -> dict:
    # Samsung TVs use self-signed certificates. These endpoints are LAN-only.
    handlers = [ProxyHandler({})]
    if port == 8002:
        handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
    opener = build_opener(*handlers)
    scheme = "https" if port == 8002 else "http"
    with opener.open(f"{scheme}://{host}:{port}/api/v2/", timeout=timeout) as response:
        data = json.loads(response.read(128 * 1024))
    device = data.get("device", {}) if isinstance(data, dict) else {}
    if not isinstance(device, dict) or "samsung" not in str(device.get("type", "")).lower():
        raise ValueError("Endpoint is not a Samsung TV")
    return data


def probe(host: str) -> TV | None:
    for port in (8001, 8002):
        try:
            data = device_info(host, timeout=0.8, port=port)
            device = data["device"]
            is_frame = str(device.get("FrameTVSupport", "false")).lower() == "true"
            mac = device.get("wifiMac")
            if mac in (None, "", "00:00:00:00:00:00"):
                mac = None
            return TV(
                id="frame" if is_frame else "samsung",
                name=html.unescape(device.get("name") or data.get("name") or "Samsung TV"),
                host=host,
                mac=mac,
                device_id=device.get("id"),
                model=device.get("modelName"),
                frame=is_frame,
                port=8002 if str(device.get("TokenAuthSupport")).lower() == "true" else port,
            )
        except (OSError, URLError, ValueError):
            continue
    return None


def discover(subnet: str) -> list[TV]:
    Settings(subnet=subnet)  # Bound the scan to a private /24 or smaller.
    hosts = [str(ip) for ip in IPv4Network(subnet).hosts()]
    with ThreadPoolExecutor(max_workers=32) as executor:
        found = [tv for tv in executor.map(probe, hosts) if tv is not None]
    # Assign deterministic distinct IDs even before saving.
    counts: dict[str, int] = {}
    for tv in found:
        base = tv.id
        counts[base] = counts.get(base, 0) + 1
        if counts[base] > 1:
            tv.id = f"{base}-{counts[base]}"
    return found


def wake(tv: TV, subnet: str) -> dict:
    if not tv.mac:
        raise ValueError("No MAC saved for this TV; discover it while powered on first")
    network = IPv4Network(subnet)
    if tv.host not in [str(ip) for ip in network.hosts()]:
        raise ValueError("TV must be in the configured subnet for Wake-on-LAN")
    packet = b"\xff" * 6 + bytes.fromhex(tv.mac.replace(":", "")) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (str(network.broadcast_address), 9))
    return {
        "tv": tv.id,
        "status": "wake_packet_sent",
        "note": "Wake is not confirmed; check tv_status after a few seconds. Power On with Mobile must be enabled on the TV.",
    }
