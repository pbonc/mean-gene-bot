import os
from datetime import datetime, timedelta, timezone

import aiohttp


API_BASE = "https://api.twitch.tv/helix"


def _get_bearer_token() -> str:
    token = (os.getenv("TWITCH_OAUTH_TOKEN") or "").strip()
    if token.lower().startswith("oauth:"):
        token = token.split(":", 1)[1]
    return token


def _headers() -> dict[str, str]:
    client_id = (os.getenv("TWITCH_CLIENT_ID") or "").strip()
    token = _get_bearer_token()
    return {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }


async def _fetch_user_by_login(session: aiohttp.ClientSession, login: str) -> dict | None:
    login = login.strip().lower()
    async with session.get(f"{API_BASE}/users", params={"login": login}, headers=_headers()) as resp:
        if resp.status != 200:
            return None
        payload = await resp.json()
        data = payload.get("data") or []
        return data[0] if data else None


async def check_join_eligibility(
    username: str,
    min_account_age_days: int = 30,
    require_follow: bool = True,
) -> tuple[bool, str]:
    username = username.lstrip("@").strip().lower()
    channel_login = (os.getenv("TWITCH_CHANNELS") or "").split(",")[0].strip().lower()
    if not channel_login:
        return False, "Join check unavailable: TWITCH_CHANNELS is not configured."

    if not (os.getenv("TWITCH_CLIENT_ID") and _get_bearer_token()):
        return False, "Join check unavailable: Twitch API credentials are missing."

    # When strict mode is disabled, join flow remains usable even if follower API checks
    # are temporarily unavailable because of missing scopes or transient Twitch issues.
    strict_follow_check = os.getenv("FACTION_FOLLOW_REQUIRE_STRICT", "false").strip().lower() == "true"

    async with aiohttp.ClientSession() as session:
        user = await _fetch_user_by_login(session, username)
        if not user:
            return False, f"Could not verify Twitch account for @{username}."

        created_at_raw = user.get("created_at")
        if not created_at_raw:
            return False, f"Could not verify account age for @{username}."

        try:
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except ValueError:
            return False, f"Could not parse account age for @{username}."

        account_age = datetime.now(timezone.utc) - created_at
        if account_age < timedelta(days=min_account_age_days):
            return False, f"@{username} must have a Twitch account older than {min_account_age_days} days to join."

        if not require_follow:
            return True, "Eligible"

        broadcaster = await _fetch_user_by_login(session, channel_login)
        if not broadcaster:
            return False, "Could not verify follower status (broadcaster lookup failed)."

        follower_params = {
            "broadcaster_id": broadcaster.get("id"),
            "user_id": user.get("id"),
            "first": 1,
        }
        async with session.get(f"{API_BASE}/channels/followers", params=follower_params, headers=_headers()) as resp:
            if resp.status == 200:
                payload = await resp.json()
                total = payload.get("total", 0)
                if int(total) > 0:
                    return True, "Eligible"
                return False, f"@{username} must follow the channel before joining a faction."

            if resp.status in (401, 403):
                if strict_follow_check:
                    return False, "Follower verification is unavailable (missing Twitch scope/permissions)."
                print(
                    f"[FACTIONS] Follower verification unavailable for @{username} (HTTP {resp.status}); "
                    "allowing join because FACTION_FOLLOW_REQUIRE_STRICT is false."
                )
                return True, "Eligible"

            if strict_follow_check:
                return False, f"Follower verification failed (HTTP {resp.status})."

            print(
                f"[FACTIONS] Follower verification failed for @{username} (HTTP {resp.status}); "
                "allowing join because FACTION_FOLLOW_REQUIRE_STRICT is false."
            )
            return True, "Eligible"
