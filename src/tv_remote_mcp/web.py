"""Local browser control panel. Shares the MCP server's controller and token store."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from .config import Settings
from .control import Controller
from .home import Home, create_home
from .integrations.samsung import Action

STATIC = Path(__file__).parent / "static"


class Switch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool


class Network(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subnet: str


class BrowserGuard(BaseHTTPMiddleware):
    """Reject cross-origin requests and DNS rebinding before any controller call."""

    def __init__(
        self, app, allowed_hosts: set[str], access_token: str | None, external_origin: str | None
    ):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts
        self.access_token = access_token
        self.external_origin = external_origin

    async def dispatch(self, request, call_next):
        if request.url.hostname not in self.allowed_hosts:
            return JSONResponse({"error": "Unrecognized host"}, status_code=403)
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if origin and origin not in {expected, self.external_origin}:
            return JSONResponse({"error": "Cross-origin requests are not allowed"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"error": "Cross-site requests are not allowed"}, status_code=403)
        if request.url.path.startswith("/api/"):
            if self.access_token:
                supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
                if not secrets.compare_digest(supplied.encode(), self.access_token.encode()):
                    return JSONResponse({"error": "Enter the server access token"}, status_code=401)
            if request.method != "GET":
                if request.headers.get("x-tv-remote") != "1":
                    return JSONResponse({"error": "Missing request header"}, status_code=403)
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    return JSONResponse({"error": "Use application/json"}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response


async def body(request: Request) -> dict:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 16 * 1024:
            raise ValueError("Request is too large")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def create_app(
    controller: Controller | None = None,
    *,
    allowed_hosts: set[str] | None = None,
    access_token: str | None = None,
    external_origin: str | None = None,
    home: Home | None = None,
) -> Starlette:
    control = controller or Controller()
    hub = home or create_home(control)
    if home is not None:
        control = Controller(home.store)

    async def index(request):
        return FileResponse(STATIC / "index.html")

    async def state(request):
        settings = await run_in_threadpool(control.store.load)
        tvs = await run_in_threadpool(control.list_tvs)
        return JSONResponse(
            {
                "subnet": settings.subnet,
                "controls_enabled": settings.controls_enabled,
                "tvs": tvs,
                "devices": await run_in_threadpool(hub.devices),
                "integrations": hub.catalog(),
            }
        )

    async def network(request):
        data = Network.model_validate(await body(request))
        validated = Settings(subnet=data.subnet)

        def save():
            with control.store.lock("config"):
                settings = control.store.load()
                settings.subnet = validated.subnet
                control.store.save(settings)

        await run_in_threadpool(save)
        return JSONResponse({"subnet": validated.subnet})

    async def switch(request):
        data = Switch.model_validate(await body(request))
        return JSONResponse(
            await run_in_threadpool(
                control.store.set_enabled, data.enabled, request.path_params.get("tv_id")
            )
        )

    async def discover(request):
        await body(request)
        result = await run_in_threadpool(control.discover, True)
        return JSONResponse(result)

    async def status(request):
        return JSONResponse(await run_in_threadpool(control.status, request.path_params["tv_id"]))

    async def action(request):
        data = Action.model_validate(await body(request))
        tv_id = request.path_params["tv_id"]
        parameters = data.model_dump(exclude={"action"}, exclude_unset=True)
        return JSONResponse(
            await run_in_threadpool(hub.execute, f"samsung:{tv_id}", data.action, parameters)
        )

    async def device_switch(request):
        data = Switch.model_validate(await body(request))
        return JSONResponse(
            await run_in_threadpool(hub.set_enabled, request.path_params["device_id"], data.enabled)
        )

    async def device_status(request):
        return JSONResponse(await run_in_threadpool(hub.status, request.path_params["device_id"]))

    async def device_action(request):
        payload = await body(request)
        action = payload.pop("action", None)
        if not isinstance(action, str):
            raise ValueError("Provide an action from this device's advertised actions")
        return JSONResponse(
            await run_in_threadpool(hub.execute, request.path_params["device_id"], action, payload)
        )

    async def integration_discover(request):
        await body(request)
        return JSONResponse(
            await run_in_threadpool(hub.discover, request.path_params["integration_id"], True)
        )

    async def bad_input(request, exc):
        if isinstance(exc, ValidationError):
            message = "; ".join(error["msg"] for error in exc.errors(include_input=False))
        else:
            message = str(exc)
        return JSONResponse({"error": message}, status_code=400)

    async def unavailable(request, exc):
        message = (
            str(exc) if isinstance(exc, RuntimeError) else "Device or local storage is unavailable"
        )
        return JSONResponse({"error": message}, status_code=503)

    app = Starlette(
        routes=[
            Route("/", index),
            Route("/api/state", state),
            Route("/api/devices/{device_id}/controls", device_switch, methods=["POST"]),
            Route("/api/devices/{device_id}/status", device_status),
            Route("/api/devices/{device_id}/action", device_action, methods=["POST"]),
            Route(
                "/api/integrations/{integration_id}/discover",
                integration_discover,
                methods=["POST"],
            ),
            Route("/api/network", network, methods=["POST"]),
            Route("/api/controls", switch, methods=["POST"]),
            Route("/api/tvs/{tv_id}/controls", switch, methods=["POST"]),
            Route("/api/discover", discover, methods=["POST"]),
            Route("/api/tvs/{tv_id}/status", status),
            Route("/api/tvs/{tv_id}/action", action, methods=["POST"]),
        ],
        exception_handlers={ValueError: bad_input, RuntimeError: unavailable, OSError: unavailable},
    )
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.add_middleware(
        BrowserGuard,
        allowed_hosts=allowed_hosts or {"localhost", "127.0.0.1", "::1"},
        access_token=access_token,
        external_origin=external_origin,
    )
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Home Control: a local smart-home control panel")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address; default: localhost only")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        help="Additional browser hostname/IP when sharing on the LAN",
    )
    parser.add_argument(
        "--external-origin",
        help="Exact HTTPS origin of a trusted private reverse proxy; loopback binding only",
    )
    args = parser.parse_args()
    token = os.environ.get("TV_REMOTE_WEB_TOKEN")
    try:
        loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = args.host == "localhost"
    if args.external_origin:
        origin = urlsplit(args.external_origin)
        if (
            not loopback
            or origin.scheme != "https"
            or not origin.hostname
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
            or origin.password
        ):
            parser.error(
                "External origin requires loopback binding and an exact HTTPS origin with no path"
            )
    if not loopback and (not token or len(token) < 24 or not args.allow_host):
        parser.error(
            "LAN access requires TV_REMOTE_WEB_TOKEN (24+ characters) and --allow-host with the server's LAN hostname/IP"
        )
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    os.umask(0o077)
    allowed = {"localhost", "127.0.0.1", "::1", *args.allow_host}
    if args.host not in {"0.0.0.0", "::"}:
        allowed.add(args.host)
    if args.external_origin:
        allowed.add(urlsplit(args.external_origin).hostname)
    app = create_app(
        allowed_hosts=allowed, access_token=token, external_origin=args.external_origin
    )
    uvicorn.run(app, host=args.host, port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()
