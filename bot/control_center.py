"""Local authenticated operator surface; no runtime service construction."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import time
from typing import Callable, Literal

from aiohttp import web


@dataclass(frozen=True)
class ControlCenterSettings:
    host: str = "127.0.0.1"
    port: int = 8090
    password: str = field(default="", repr=False)

    @classmethod
    def from_env(cls):
        try:
            port = int(os.getenv("CONTROL_CENTER_PORT", "8090"))
        except ValueError:
            port = -1
        return cls(os.getenv("CONTROL_CENTER_HOST", "127.0.0.1"), port,
                   os.getenv("CONTROL_CENTER_PASSWORD", ""))

    def validate(self):
        if self.host != "127.0.0.1":
            raise ValueError("Control Center requires the 127.0.0.1 loopback literal")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Invalid Control Center port")
        if not isinstance(self.password, str) or not 16 <= len(self.password) <= 1024 or self.password.isspace():
            raise ValueError("Control Center authentication is not configured")

    def validate_overlay_port(self, configured_port: str):
        try:
            base = int(configured_port.strip() or "8080")
        except ValueError:
            base = 8080
        if self.port in (base, base + 1, base + 2):
            raise ValueError("Control Center port overlaps the overlay listener range")

    @property
    def origin(self):
        return f"http://{self.host}:{self.port}"


State = Literal["unknown", "unavailable", "channels_joined"]


@dataclass(frozen=True)
class ReconnectStatus:
    supported: bool = False
    reason: str = "No safe isolated manual reconnect is established."


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    state: State
    detail: str
    reconnect: ReconnectStatus | None = None


@dataclass(frozen=True)
class DashboardStatus:
    meangene: Literal["unknown"]
    channels: tuple[str, ...]
    services: tuple[ServiceStatus, ...]
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)


class OwnedStatus:
    """Read only verified channel evidence; existence never means healthy."""
    def __init__(self, twitch, discord, hermes, lore):
        self.twitch, self.discord, self.hermes, self.lore = twitch, discord, hermes, lore

    def __call__(self) -> DashboardStatus:
        channels = ()
        try:
            channels = tuple(sorted({c.name for c in self.twitch.connected_channels
                                     if isinstance(c.name, str) and re.fullmatch(r"[A-Za-z0-9_]{1,25}", c.name)}))
        except Exception:
            pass
        return DashboardStatus("unknown", channels, (
            ServiceStatus("Twitch", "channels_joined" if channels else "unknown" if self.twitch is not None else "unavailable",
                          "Joined channels observed; this is not a health check." if channels else "No current joined-channel evidence.", ReconnectStatus()),
            ServiceStatus("Discord", "unknown" if self.discord is not None else "unavailable", "No verified live health signal is exposed by this adapter.", ReconnectStatus()),
            ServiceStatus("Hermes", "unknown" if self.hermes is not None else "unavailable", "Request/response health is not probed.", ReconnectStatus(reason="Hermes has no persistent connection to reconnect.")),
            ServiceStatus("Lore", "unknown" if self.lore is not None else "unavailable", "No store health probe is performed."),
        ))


@dataclass
class Session:
    csrf: str
    expires: float
    authenticated: bool = False


class ControlCenterServer:
    COOKIE = "meangene_control"
    PREFIX = "/control/"

    def __init__(self, settings: ControlCenterSettings, status: Callable[[], DashboardStatus], *, clock=time.monotonic):
        settings.validate()
        self.settings = settings
        self._password_digest = hashlib.sha256(settings.password.encode()).digest()
        self.status = status
        self.clock = clock
        self.sessions: dict[str, Session] = {}
        self.runner = None
        self._lock = asyncio.Lock()
        self.app = web.Application(middlewares=[self._security], client_max_size=4096)
        self.app.router.add_get("/control/login", self.login_page)
        self.app.router.add_post("/control/login", self.login)
        self.app.router.add_post("/control/logout", self.logout)
        self.app.router.add_get("/control/", self.dashboard)
        self.app.router.add_get("/control/api/status", self.get_status)
        self.app.router.add_post("/control/api/reconnect/{service}", self.reconnect)
        self.app.router.add_get("/control/assets/{asset}", self.asset)

    def _session(self, request):
        now = self.clock()
        for key in tuple(self.sessions):
            if self.sessions[key].expires <= now:
                del self.sessions[key]
        return self.sessions.get(request.cookies.get(self.COOKIE, ""))

    @web.middleware
    async def _security(self, request, handler):
        try:
            if request.host != f"{self.settings.host}:{self.settings.port}":
                raise web.HTTPForbidden()
            session = self._session(request)
            public = request.path == "/control/login" or request.path in {"/control/assets/login.js", "/control/assets/style.css"}
            if not public and (session is None or not session.authenticated):
                raise web.HTTPUnauthorized()
            if request.method not in {"GET", "HEAD"}:
                if request.method != "POST" or request.headers.getall("Origin", []) != [self.settings.origin]:
                    raise web.HTTPForbidden()
                csrf = request.headers.get("X-CSRF-Token", "")
                if session is None or not csrf.isascii() or not hmac.compare_digest(csrf, session.csrf):
                    raise web.HTTPForbidden()
                if request.content_type != "application/json":
                    raise web.HTTPBadRequest()
                try:
                    body = await request.json()
                except Exception:
                    raise web.HTTPBadRequest() from None
                if not isinstance(body, dict):
                    raise web.HTTPBadRequest()
                request["body"] = body
            response = await handler(request)
        except web.HTTPException as error:
            response = web.json_response({"error": "Request rejected"}, status=error.status)
        except Exception:
            response = web.json_response({"error": "Control Center unavailable"}, status=500)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    def _new_session(self, response, *, authenticated=False):
        if len(self.sessions) >= 512:
            raise web.HTTPServiceUnavailable()
        key = secrets.token_urlsafe(32)
        session = Session(secrets.token_urlsafe(32), self.clock() + (3600 if authenticated else 300), authenticated)
        self.sessions[key] = session
        response.set_cookie(self.COOKIE, key, httponly=True, samesite="Strict", secure=False,
                            path=self.PREFIX, max_age=3600 if authenticated else 300)
        return session

    async def login_page(self, request):
        existing = self._session(request)
        if existing is not None and existing.authenticated:
            return web.Response(text='<a href="/control/">Open Control Center</a>', content_type="text/html")
        response = web.Response(content_type="text/html")
        session = existing or self._new_session(response)
        response.text = (Path(__file__).with_name("control_static") / "login.html").read_text(encoding="utf-8").replace("CSRF_VALUE", session.csrf)
        return response

    async def login(self, request):
        body = request["body"]
        password = body.get("password")
        if set(body) != {"password"} or not isinstance(password, str) or len(password) > 1024:
            raise web.HTTPBadRequest()
        if not hmac.compare_digest(hashlib.sha256(password.encode()).digest(), self._password_digest):
            self.sessions.pop(request.cookies.get(self.COOKIE, ""), None)
            raise web.HTTPUnauthorized()
        self.sessions.pop(request.cookies.get(self.COOKIE, ""), None)
        response = web.json_response({"ok": True})
        self._new_session(response, authenticated=True)
        return response

    async def logout(self, request):
        if request["body"]:
            raise web.HTTPBadRequest()
        self.sessions.pop(request.cookies.get(self.COOKIE, ""), None)
        response = web.json_response({"ok": True})
        response.del_cookie(self.COOKIE, path=self.PREFIX)
        return response

    async def dashboard(self, request):
        return web.Response(text=(Path(__file__).with_name("control_static") / "index.html").read_text(encoding="utf-8"), content_type="text/html")

    async def get_status(self, request):
        return web.json_response({"status": self.status().to_dict(), "csrf": self._session(request).csrf})

    async def reconnect(self, request):
        if request["body"]:
            raise web.HTTPBadRequest()
        if request.match_info["service"] not in {"twitch", "discord", "hermes"}:
            raise web.HTTPNotFound()
        return web.json_response({"error": "Reconnect unsupported", "supported": False}, status=409)

    async def asset(self, request):
        name = request.match_info["asset"]
        if name not in {"style.css", "login.js", "dashboard.js"}:
            raise web.HTTPNotFound()
        return web.Response(text=(Path(__file__).with_name("control_static") / name).read_text(encoding="utf-8"),
                            content_type="text/css" if name.endswith("css") else "text/javascript")

    async def start(self):
        async with self._lock:
            if self.runner is not None:
                raise RuntimeError("Control Center already started")
            runner = web.AppRunner(self.app, access_log=None)
            try:
                await runner.setup()
                await web.TCPSite(runner, self.settings.host, self.settings.port).start()
            except BaseException:
                try:
                    await runner.cleanup()
                except BaseException:
                    pass  # Preserve the original setup/bind/cancellation failure.
                raise
            self.runner = runner

    async def close(self):
        async with self._lock:
            self.sessions.clear()
            if self.runner is not None:
                runner, self.runner = self.runner, None
                await runner.cleanup()
