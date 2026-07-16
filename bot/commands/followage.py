import os
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import aiohttp
from twitchio.ext import commands

API_BASE = "https://api.twitch.tv/helix"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=3)
DECAP_API_BASE = "https://decapi.me/twitch/followage"


def _normalize_token(token: str | None) -> str:
    token = (token or "").strip()
    if token.lower().startswith("oauth:"):
        token = token.split(":", 1)[1]
    return token


def _parse_login(raw: str | None) -> str:
    return (raw or "").strip().lstrip("@").lower()


def _format_followed_since(followed_at_raw: str) -> tuple[str, str] | None:
    try:
        followed_at = datetime.fromisoformat(followed_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    date_text = followed_at.strftime("%B %d, %Y")

    delta_days = max(0, (datetime.now(timezone.utc) - followed_at).days)
    years = delta_days // 365
    remaining_days = delta_days % 365
    months = remaining_days // 30
    days = remaining_days % 30

    if years > 0:
        duration = f"{years}y {months}mo"
    elif months > 0:
        duration = f"{months}mo {days}d"
    else:
        duration = f"{days}d"

    return date_text, duration


class FollowageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger("followage")

    async def _fetch_user_by_login(
        self,
        session: aiohttp.ClientSession,
        headers: dict[str, str],
        login: str,
    ) -> dict | None:
        async with session.get(f"{API_BASE}/users", params={"login": login}, headers=headers) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json()
            data = payload.get("data") or []
            return data[0] if data else None

    async def _fetch_token_user_id(
        self,
        session: aiohttp.ClientSession,
        headers: dict[str, str],
    ) -> str | None:
        async with session.get("https://id.twitch.tv/oauth2/validate", headers=headers) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json()
            user_id = str(payload.get("user_id") or "").strip()
            return user_id or None

    async def _fetch_followage_from_decap(
        self,
        session: aiohttp.ClientSession,
        channel_login: str,
        target_login: str,
    ) -> str | None:
        # decapi supports followage with a decapi-managed OAuth token.
        decapi_token = (os.getenv("DECAP_FOLLOWAGE_TOKEN") or "").strip()
        if not decapi_token:
            return None

        params = urlencode({"token": decapi_token})
        url = f"{DECAP_API_BASE}/{channel_login}/{target_login}?{params}"
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            text = (await resp.text()).strip()
            if not text:
                return None

            lowered = text.lower()
            if "cannot follow themself" in lowered:
                return f"@{target_login}, you are the broadcaster here. Try !followage <username>."
            if "not following" in lowered:
                return f"@{target_login} is not currently following @{channel_login}."
            if "missing `token`" in lowered:
                return None
            if "error" in lowered:
                return None

            return f"@{target_login} followage: {text}"

    @commands.command(name="followage")
    async def followage(self, ctx: commands.Context, username=None):
        channel_login = _parse_login((os.getenv("TWITCH_CHANNELS") or "").split(",")[0])
        if not channel_login:
            await ctx.send("Followage is unavailable: TWITCH_CHANNELS is not configured.")
            return

        client_id = (os.getenv("TWITCH_CLIENT_ID") or "").strip()
        token = _normalize_token(os.getenv("TWITCH_OAUTH_TOKEN"))
        if not client_id or not token:
            await ctx.send("Followage is unavailable: Twitch API credentials are missing.")
            return

        target_login = _parse_login(username) if username else _parse_login(getattr(ctx.author, "name", ""))
        if not target_login:
            await ctx.send("Usage: !followage [username]")
            return

        if target_login == channel_login:
            await ctx.send(f"@{target_login}, you are the broadcaster here. Try !followage <username>.")
            return

        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
        }

        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                moderator_id = await self._fetch_token_user_id(session, headers)
                if not moderator_id:
                    fallback = await self._fetch_followage_from_decap(session, channel_login, target_login)
                    if fallback:
                        await ctx.send(fallback)
                        return
                    return

                broadcaster = await self._fetch_user_by_login(session, headers, channel_login)
                if not broadcaster:
                    await ctx.send("Could not verify the channel on Twitch.")
                    return

                target_user = await self._fetch_user_by_login(session, headers, target_login)
                if not target_user:
                    await ctx.send(f"Could not find Twitch user @{target_login}.")
                    return

                params = {
                    "broadcaster_id": broadcaster.get("id"),
                    "moderator_id": moderator_id,
                    "user_id": target_user.get("id"),
                    "first": 1,
                }
                async with session.get(f"{API_BASE}/channels/followers", params=params, headers=headers) as resp:
                    if resp.status == 200:
                        payload = await resp.json()
                        follows = payload.get("data") or []
                        if not follows:
                            await ctx.send(f"@{target_login} is not currently following @{channel_login}.")
                            return

                        followed_at_raw = follows[0].get("followed_at")
                        if not followed_at_raw:
                            await ctx.send(f"@{target_login} follows @{channel_login}, but the follow date was unavailable.")
                            return

                        formatted = _format_followed_since(followed_at_raw)
                        if not formatted:
                            await ctx.send(f"@{target_login} follows @{channel_login}, but I could not parse the follow date.")
                            return

                        date_text, duration_text = formatted
                        await ctx.send(
                            f"@{target_login} has been following @{channel_login} since {date_text} ({duration_text} ago)."
                        )
                        return

                    if resp.status in (401, 403):
                        fallback = await self._fetch_followage_from_decap(session, channel_login, target_login)
                        if fallback:
                            await ctx.send(fallback)
                            return
                        return

                    self.logger.warning("Followage request failed with Twitch HTTP %s", resp.status)
                    await ctx.send("Followage is temporarily unavailable due to a Twitch API error.")
        except aiohttp.ClientError:
            await ctx.send("Followage is temporarily unavailable due to a network error.")
        except Exception as exc:
            self.logger.exception("Unexpected followage error: %s", exc)
            await ctx.send("Followage is temporarily unavailable.")


def prepare(bot: commands.Bot):
    if not bot.get_cog("FollowageCog"):
        bot.add_cog(FollowageCog(bot))
