from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from .config import NetworkTV
from .control import Controller
from .home import create_home


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Home Control setup and diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("devices")
    sub.add_parser("integrations")
    sub.add_parser("device-status").add_argument("device_id")
    generic_scan = sub.add_parser("discover-devices")
    generic_scan.add_argument("integration_id")
    generic_scan.add_argument("--save", action="store_true")
    add = sub.add_parser("add-device")
    add.add_argument("integration", choices=["lg_webos", "sony_bravia"])
    add.add_argument("id")
    add.add_argument("host")
    add.add_argument("--name", required=True)
    add.add_argument("--port", type=int)
    add.add_argument("--mac")
    sub.add_parser("device-pair").add_argument("device_id")
    scan = sub.add_parser("discover")
    scan.add_argument("--save", action="store_true")
    for command in ("status", "pair", "art-status"):
        sub.add_parser(command).add_argument("tv_id")
    for command in ("enable", "disable"):
        switch = sub.add_parser(command)
        switch.add_argument("tv_id", help="TV ID, or all for the master switch")
    key = sub.add_parser("key")
    key.add_argument("tv_id")
    key.add_argument("key")
    key.add_argument("--times", type=int, default=1)
    args = parser.parse_args()
    control = Controller()
    home = create_home(control)
    try:
        if args.command == "add-device":
            device = NetworkTV(
                integration=args.integration,
                id=args.id,
                name=args.name,
                host=args.host,
                port=args.port or (3001 if args.integration == "lg_webos" else 80),
                mac=args.mac,
            )
            control.store.merge_network([device])
            result = {"status": "saved"}
        elif args.command == "device-pair":
            integration, device = home.resolve(args.device_id)
            parameters = {}
            if integration.id == "sony_bravia":
                parameters["psk"] = getpass.getpass("Sony TV pre-shared key (hidden): ")
            else:
                print("Choose Allow on the TV now (25 second timeout).", file=sys.stderr)
            result = home.execute(args.device_id, "pair", parameters)
        elif args.command == "devices":
            result = home.devices()
        elif args.command == "integrations":
            result = home.catalog()
        elif args.command == "device-status":
            result = home.status(args.device_id)
        elif args.command == "discover-devices":
            result = home.discover(args.integration_id, args.save)
        elif args.command == "list":
            result = control.list_tvs()
        elif args.command == "discover":
            result = control.discover(args.save)
        elif args.command in ("enable", "disable"):
            if ":" in args.tv_id:
                result = home.set_enabled(args.tv_id, args.command == "enable")
            else:
                result = control.store.set_enabled(
                    args.command == "enable", None if args.tv_id == "all" else args.tv_id
                )
        elif args.command == "status":
            result = control.status(args.tv_id)
        elif args.command == "pair":
            print(
                "Select Allow for Samsung TV Remote MCP on the TV now (25 second timeout).",
                file=sys.stderr,
            )
            result = control.pair(args.tv_id)
        elif args.command == "art-status":
            result = control.art_status(args.tv_id)
        else:
            result = control.key(args.tv_id, args.key, args.times)
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
