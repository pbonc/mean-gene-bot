"""World of Tanks Modern Armor API client used by the WoTWoM overlay."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import aiohttp


API_ROOT = "https://api-console.worldoftanks.com/wotx"
AUTH_FILE = Path(__file__).resolve().parents[1] / "data" / "wot_auth.json"


class WotApiError(RuntimeError):
    """A safe-to-display error returned by the Wargaming API."""


@dataclass(frozen=True)
class WotConfig:
    application_id: str
    account_id: str = ""
    player_name: str = ""
    api_root: str = API_ROOT

    @classmethod
    def from_env(cls) -> "WotConfig":
        return cls(
            application_id=os.getenv("WOT_APPLICATION_ID", "").strip(),
            account_id=os.getenv("WOT_ACCOUNT_ID", "").strip(),
            player_name=os.getenv("WOT_PLAYER_NAME", "").strip(),
            api_root=os.getenv("WOT_API_ROOT", API_ROOT).strip().rstrip("/"),
        )


def _mode_for_vehicle(vehicle: dict[str, Any]) -> str:
    """Normalize the several mode fields seen in WoTMA Tankopedia responses."""
    if vehicle.get("era"):
        return "cold_war"
    raw = str(
        vehicle.get("mode")
        or vehicle.get("game_mode")
        or vehicle.get("era_name")
        or ""
    ).lower()
    if "cold" in raw or raw in {"1", "2", "3"}:
        return "cold_war"
    return "wwii"


def _vehicle_type(raw: str) -> str:
    return {
        "lightTank": "Light Tank",
        "mediumTank": "Medium Tank",
        "heavyTank": "Heavy Tank",
        "AT-SPG": "Tank Destroyer",
        "SPG": "Artillery",
    }.get(raw, raw or "Unknown")


def _nation_for_vehicle(raw: str) -> str:
    return {
        "usa": "USA",
        "ussr": "USSR",
        "uk": "UK",
        "czech": "Czechoslovakia",
        "merc": "Mercenary",
        "xn": "Independent",
    }.get(raw, raw.replace("_", " ").title() or "Unknown")


def _faction_for_vehicle(vehicle: dict[str, Any]) -> str | None:
    if _mode_for_vehicle(vehicle) != "cold_war":
        return None
    nation = str(vehicle.get("nation") or "").lower()
    if nation in {"usa", "uk", "france", "germany", "italy"}:
        return "Western Alliance"
    if nation in {"ussr", "china", "czech", "poland"}:
        return "Eastern Alliance"
    return "Independent"


def _era_for_vehicle(vehicle: dict[str, Any]) -> int | None:
    raw = vehicle.get("era") or vehicle.get("era_id") or vehicle.get("era_number")
    if isinstance(raw, int) and 1 <= raw <= 3:
        return raw
    text = str(raw or vehicle.get("era_name") or "").lower()
    named_eras = {"post war": 1, "escalation": 2, "détente": 3, "detente": 3}
    if text in named_eras:
        return named_eras[text]
    for era in (1, 2, 3):
        if str(era) in text:
            return era
    return None


class WotApiClient:
    def __init__(self, config: WotConfig, session: aiohttp.ClientSession):
        self.config = config
        self.session = session

    async def _get(self, path: str, **params: str) -> Any:
        query = {"application_id": self.config.application_id, "language": "en"}
        query.update({key: value for key, value in params.items() if value})
        try:
            async with self.session.get(
                f"{self.config.api_root}/{path.lstrip('/')}",
                params=query,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise WotApiError("World of Tanks data service is unavailable.") from exc
        if payload.get("status") != "ok":
            error = payload.get("error") or {}
            raise WotApiError(error.get("message") or "World of Tanks API request failed.")
        return payload.get("data")

    async def resolve_account(self) -> tuple[str, str]:
        if self.config.account_id:
            return self.config.account_id, self.config.player_name
        if not self.config.player_name:
            raise WotApiError("Set WOT_ACCOUNT_ID or WOT_PLAYER_NAME.")
        matches = await self._get("account/list/", search=self.config.player_name)
        requested = self.config.player_name.casefold()
        exact = [
            player
            for player in (matches or [])
            if str(player.get("nickname", "")).casefold() == requested
            or str(player.get("nickname", "")).casefold().removesuffix("-x")
            == requested
            or str(player.get("nickname", "")).casefold().removesuffix("-p")
            == requested
        ]
        if len(exact) != 1:
            raise WotApiError(f'Player "{self.config.player_name}" was not found.')
        player = exact[0]
        return str(player["account_id"]), str(player.get("nickname", ""))

    async def inventory(self) -> dict[str, Any]:
        if not self.config.application_id:
            raise WotApiError("Set WOT_APPLICATION_ID before using WoTWoM.")
        account_id, nickname = await self.resolve_account()
        stats = await self._get("tanks/stats/", account_id=account_id)
        if isinstance(stats, dict):
            stats = stats.get(str(account_id)) or stats.get(int(account_id)) or []
        stats_by_id = {str(row["tank_id"]): row for row in stats or []}
        tank_ids = sorted({str(row["tank_id"]) for row in stats or []})
        if not tank_ids:
            raise WotApiError("No played vehicles were returned for this account.")

        vehicles: dict[str, Any] = {}
        # The API accepts at most 100 comma-separated IDs per request.
        for start in range(0, len(tank_ids), 100):
            result = await self._get(
                "encyclopedia/vehicles/",
                tank_id=",".join(tank_ids[start : start + 100]),
            )
            vehicles.update(result or {})

        normalized = []
        for tank_id in tank_ids:
            vehicle = vehicles.get(tank_id) or {}
            if not vehicle:
                continue
            normalized.append(
                {
                    "tank_id": int(tank_id),
                    "name": vehicle.get("short_name") or vehicle.get("name") or tank_id,
                    "nation": _nation_for_vehicle(
                        str(vehicle.get("nation") or "unknown").lower()
                    ),
                    "faction": _faction_for_vehicle(vehicle),
                    "type": _vehicle_type(str(vehicle.get("type") or "")),
                    "tier": vehicle.get("tier"),
                    "era": _era_for_vehicle(vehicle),
                    "mode": _mode_for_vehicle(vehicle),
                    "last_battle_time": stats_by_id.get(tank_id, {}).get(
                        "last_battle_time"
                    ),
                }
            )
        return {
            "account_id": account_id,
            "nickname": nickname or self.config.player_name,
            "source": "played_vehicle_statistics",
            "vehicles": normalized,
        }

    async def login_url(self, redirect_uri: str) -> str:
        data = await self._get(
            "auth/login/",
            redirect_uri=redirect_uri,
            nofollow="1",
        )
        location = (data or {}).get("location")
        if not location:
            raise WotApiError("World of Tanks did not return a console login URL.")
        return str(location)

    async def authenticated_profile(self, token: str, account_id: str) -> dict[str, Any]:
        data = await self._get(
            "account/info/",
            access_token=token,
            account_id=account_id,
            extra="private.garage",
        )
        if isinstance(data, dict):
            return data.get(str(account_id)) or data.get(int(account_id)) or {}
        return {}


async def fetch_wot_inventory() -> dict[str, Any]:
    config = WotConfig.from_env()
    async with aiohttp.ClientSession() as session:
        return await WotApiClient(config, session).inventory()


def save_wot_auth(payload: dict[str, Any]) -> None:
    allowed = {
        key: payload[key]
        for key in ("access_token", "account_id", "nickname", "expires_at")
        if payload.get(key) not in (None, "")
    }
    if not allowed.get("access_token") or not allowed.get("account_id"):
        raise WotApiError("Authorization callback did not include a token and account ID.")
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = AUTH_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(allowed, indent=2), encoding="utf-8")
    os.replace(temporary, AUTH_FILE)


def load_wot_auth() -> dict[str, Any]:
    if not AUTH_FILE.is_file():
        return {}
    try:
        return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
