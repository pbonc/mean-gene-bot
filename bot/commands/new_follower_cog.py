"""Welcome new Twitch followers and give them starter raffle entries."""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import aiohttp
from twitchio.ext import commands


LOGGER = logging.getLogger("new_followers")
API_BASE = "https://api.twitch.tv/helix"
POLL_SECONDS = 15
WARNING_INTERVAL_SECONDS = 300
FOLLOW_BONUS_ENTRIES = 10
STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "new_follower_state.json"


def _normalize_token(token):
    token = str(token or "").strip()
    return token.split(":", 1)[1] if token.casefold().startswith("oauth:") else token


def _prize_text(amount):
    try:
        value = float(amount)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return "the current raffle prize"
    formatted = f"${value:,.2f}".rstrip("0").rstrip(".")
    return f"a {formatted} gift card"


def follower_message(username, prize_amount, raffle_open, variant):
    """Build one of four conversational welcome messages."""
    mention = f"@{str(username).strip().lstrip('@')}"
    prize = _prize_text(prize_amount)
    action = "Try" if raffle_open else "When the raffle opens, try"
    messages = (
        f"Welcome in, {mention}! Thanks for the follow. You're officially today's FNG: Friendly New Guy. "
        f"You received 10 free raffle entries, and the prize is {prize}. {action} !raffle random all "
        f"to pick automatically or !raffle pick 123 456 to choose your own. Where are you joining us from?",

        f"Hey {mention}, thanks for the follow! You're our newest FNG with 10 free entries toward {prize}. "
        f"{action} !raffle random all for automatic picks or !raffle pick 123 456 to choose your own. "
        f"Use !raffle picks to see your numbers. What games have you been playing lately?",

        f"{mention} has entered the chat! Welcome to the crew. We started you with 10 free entries, and the "
        f"prize is {prize}. {action} !raffle random all or choose numbers with !raffle pick 123 456. "
        f"Use !raffle entries to check unused entries. What game could you replay forever?",

        f"Welcome, {mention}! Your FNG package includes 10 free entries for {prize}. {action} !raffle random all "
        f"or !raffle pick 123 456, then use !raffle picks to see your numbers. Important question: which video "
        f"game has the best soundtrack?",
    )
    return messages[int(variant) % len(messages)]


class NewFollowerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = self._load_state()
        self.broadcaster_id = None
        self.moderator_id = None
        self.last_api_warning_at = 0.0
        self.task = bot.loop.create_task(self._monitor())

    def _warn_api(self, message, *args):
        now = time.monotonic()
        if now - self.last_api_warning_at >= WARNING_INTERVAL_SECONDS:
            LOGGER.warning(message, *args)
            self.last_api_warning_at = now

    def _load_state(self):
        try:
            with STATE_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {
                    "initialized": bool(data.get("initialized")),
                    "handled_events": list(data.get("handled_events") or [])[-1000:],
                    "next_variant": int(data.get("next_variant") or 0) % 4,
                }
        except (OSError, ValueError, TypeError):
            pass
        return {"initialized": False, "handled_events": [], "next_variant": 0}

    def _save_state(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE_FILE.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2)
        os.replace(temporary, STATE_FILE)

    async def _resolve_ids(self, session, headers):
        if self.broadcaster_id and self.moderator_id:
            return True
        channel = (os.getenv("TWITCH_CHANNELS") or "").split(",")[0].strip().lstrip("@").lower()
        if not channel:
            return False
        async with session.get(f"{API_BASE}/users", params={"login": channel}, headers=headers) as response:
            if response.status != 200:
                return False
            users = (await response.json()).get("data") or []
        async with session.get("https://id.twitch.tv/oauth2/validate", headers=headers) as response:
            if response.status != 200:
                return False
            validation = await response.json()
        self.broadcaster_id = str((users[0] if users else {}).get("id") or "")
        self.moderator_id = str(validation.get("user_id") or "")
        return bool(self.broadcaster_id and self.moderator_id)

    async def _fetch_recent(self):
        client_id = (os.getenv("TWITCH_CLIENT_ID") or "").strip()
        token = _normalize_token(os.getenv("TWITCH_OAUTH_TOKEN"))
        if not client_id or not token:
            return []
        headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
        timeout = aiohttp.ClientTimeout(total=12, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if not await self._resolve_ids(session, headers):
                return []
            params = {
                "broadcaster_id": self.broadcaster_id,
                "moderator_id": self.moderator_id,
                "first": 20,
            }
            async with session.get(f"{API_BASE}/channels/followers", params=params, headers=headers) as response:
                if response.status != 200:
                    self._warn_api("New follower polling failed with Twitch HTTP %s", response.status)
                    return []
                return (await response.json()).get("data") or []

    def _remember_event(self, event_key):
        self.state["handled_events"].append(event_key)
        self.state["handled_events"] = self.state["handled_events"][-1000:]
        self._save_state()

    async def _handle_follow(self, follower, channel, event_key):
        username = str(follower.get("user_name") or follower.get("user_login") or "").strip()
        if not username:
            return False
        raffle_cog = self.bot.get_cog("RaffleCog")
        if not raffle_cog or not hasattr(raffle_cog, "state"):
            return False
        if not raffle_cog.state.add_entries(username, FOLLOW_BONUS_ENTRIES):
            LOGGER.info("Follower @%s is not eligible for raffle entries", username)
            self._remember_event(event_key)
            return True
        message = follower_message(
            username,
            raffle_cog.state.get_giveaway_amount(),
            raffle_cog.state.is_open,
            self.state["next_variant"],
        )
        # Persist the award before chat I/O so a send failure cannot duplicate it.
        self._remember_event(event_key)
        await channel.send(message[:500])
        self.state["next_variant"] = (self.state["next_variant"] + 1) % 4
        return True

    async def _poll_once(self):
        channels = list(getattr(self.bot, "connected_channels", None) or [])
        if not channels:
            return
        followers = await self._fetch_recent()
        if not followers:
            return
        event_keys = [
            f"{row.get('user_id')}:{row.get('followed_at')}"
            for row in followers
            if row.get("user_id") and row.get("followed_at")
        ]
        if not self.state["initialized"]:
            self.state["initialized"] = True
            self.state["handled_events"] = event_keys[-1000:]
            self._save_state()
            return
        handled = set(self.state["handled_events"])
        for follower in reversed(followers):
            event_key = f"{follower.get('user_id')}:{follower.get('followed_at')}"
            if event_key in handled or event_key == "None:None":
                continue
            if await self._handle_follow(follower, channels[0], event_key):
                handled.add(event_key)
                self._save_state()

    async def _monitor(self):
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                return
            except Exception:
                LOGGER.exception("New follower processing failed")
            await asyncio.sleep(POLL_SECONDS)

    def cog_unload(self):
        if self.task and not self.task.done():
            self.task.cancel()


def prepare(bot):
    if not bot.get_cog("NewFollowerCog"):
        bot.add_cog(NewFollowerCog(bot))
