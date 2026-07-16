"""Non-invasive integration smoke tests for MGB's external connections.

This script never prints credentials and never sends chat/channel messages.
It validates Twitch OAuth plus an IRC join, opens and closes a Discord gateway
session, and starts the real overlay server long enough to test HTTP/WebSocket.
"""

import argparse
import asyncio
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_IRC_URL = "wss://irc-ws.chat.twitch.tv:443"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def _normalized_token(value: str) -> str:
    return value.removeprefix("oauth:")


async def check_twitch(timeout_seconds: float) -> CheckResult:
    token = _normalized_token(_required_env("TWITCH_OAUTH_TOKEN"))
    channels = [
        item.strip().lstrip("#").lower()
        for item in _required_env("TWITCH_CHANNELS").split(",")
        if item.strip()
    ]
    if not channels:
        raise RuntimeError("TWITCH_CHANNELS does not contain a channel")

    timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            TWITCH_VALIDATE_URL,
            headers={"Authorization": f"OAuth {token}"},
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"OAuth validation returned HTTP {response.status}")
            validation = await response.json()

        login = str(validation.get("login") or "").lower()
        if not login:
            raise RuntimeError("OAuth validation did not return a login")

        async with session.ws_connect(TWITCH_IRC_URL, heartbeat=20) as websocket:
            await websocket.send_str("CAP REQ :twitch.tv/membership twitch.tv/commands")
            await websocket.send_str(f"PASS oauth:{token}")
            await websocket.send_str(f"NICK {login}")
            await websocket.send_str(f"JOIN #{channels[0]}")

            authenticated = False
            joined = False
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_seconds

            while loop.time() < deadline and not (authenticated and joined):
                remaining = max(0.1, deadline - loop.time())
                message = await asyncio.wait_for(websocket.receive(), timeout=remaining)
                if message.type != aiohttp.WSMsgType.TEXT:
                    if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        raise RuntimeError("Twitch IRC websocket closed before channel join")
                    continue

                for line in message.data.split("\r\n"):
                    if line.startswith("PING"):
                        await websocket.send_str(line.replace("PING", "PONG", 1))
                    if " 001 " in line:
                        authenticated = True
                    if f" {login}!{login}@{login}.tmi.twitch.tv JOIN #{channels[0]}" in line:
                        joined = True
                    if " ROOMSTATE #" + channels[0] in line:
                        joined = True
                    if "Login authentication failed" in line:
                        raise RuntimeError("Twitch IRC rejected OAuth authentication")

            if not authenticated or not joined:
                raise RuntimeError("Timed out waiting for Twitch authentication/channel join")

    return CheckResult("twitch", True, "OAuth valid; IRC authenticated and channel joined")


async def check_discord(timeout_seconds: float) -> CheckResult:
    try:
        import discord
    except ImportError as exc:
        raise RuntimeError("discord.py is not installed") from exc

    token = _required_env("DISCORD_TOKEN")
    client = discord.Client(intents=discord.Intents.none())
    await asyncio.wait_for(client.login(token), timeout=timeout_seconds)
    connect_task = asyncio.create_task(client.connect(reconnect=False))
    try:
        await asyncio.wait_for(client.wait_until_ready(), timeout=timeout_seconds)
        if not client.user:
            raise RuntimeError("Discord gateway became ready without a bot identity")
        return CheckResult("discord", True, "Gateway authenticated and reached READY")
    finally:
        await client.close()
        try:
            await asyncio.wait_for(connect_task, timeout=5)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            connect_task.cancel()
            await asyncio.gather(connect_task, return_exceptions=True)


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def check_overlay(timeout_seconds: float) -> CheckResult:
    from bot.overlay_server import start_overlay_server

    port = _available_loopback_port()
    server_task = asyncio.create_task(start_overlay_server(host="127.0.0.1", port=port))
    base_url = f"http://127.0.0.1:{port}"
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            last_error = None
            for _ in range(20):
                try:
                    async with session.get(base_url + "/") as response:
                        if response.status != 200:
                            raise RuntimeError(f"overlay root returned HTTP {response.status}")
                    async with session.get(base_url + "/gifs/test.txt") as response:
                        if response.status != 200:
                            raise RuntimeError(f"canonical overlay media returned HTTP {response.status}")
                    async with session.get(base_url + "/api/cards") as response:
                        if response.status != 200:
                            raise RuntimeError(f"card API returned HTTP {response.status}")
                        card_payload = await response.json()
                        if not card_payload:
                            raise RuntimeError("card API did not discover assets/cards")
                    async with session.ws_connect(base_url + "/ws") as websocket:
                        if websocket.closed:
                            raise RuntimeError("overlay websocket closed immediately")
                    return CheckResult(
                        "overlay",
                        True,
                        "HTTP, canonical media/card paths, and WebSocket accepted connections",
                    )
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_error = exc
                    await asyncio.sleep(0.1)
            raise RuntimeError(f"overlay server did not become ready: {last_error}")
    finally:
        server_task.cancel()
        await asyncio.gather(server_task, return_exceptions=True)


async def _run(args: argparse.Namespace) -> int:
    checks = []
    if not args.skip_twitch:
        checks.append(("twitch", check_twitch))
    if not args.skip_discord:
        checks.append(("discord", check_discord))
    if not args.skip_overlay:
        checks.append(("overlay", check_overlay))

    failures = 0
    for name, check in checks:
        try:
            result = await check(args.timeout)
            print(f"PASS {result.name}: {result.detail}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")

    print(f"RESULT: {len(checks) - failures}/{len(checks)} checks passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=20.0, help="seconds allowed per check")
    parser.add_argument("--skip-twitch", action="store_true")
    parser.add_argument("--skip-discord", action="store_true")
    parser.add_argument("--skip-overlay", action="store_true")
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    load_dotenv()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
