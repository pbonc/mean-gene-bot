"""Sanitized connectivity diagnostic for the WoTWoM API integration."""

import argparse
import asyncio
import json

import aiohttp
from dotenv import load_dotenv

from bot.wot_api import WotApiClient, WotApiError, WotConfig, load_wot_auth


async def main(
    partial: bool,
    metadata: bool,
    auth_url: bool,
    private_profile: bool,
    stats_schema: bool,
) -> None:
    load_dotenv()
    config = WotConfig.from_env()
    async with aiohttp.ClientSession() as session:
        client = WotApiClient(config, session)
        if stats_schema:
            auth = load_wot_auth()
            profile = await client.authenticated_profile(
                str(auth.get("access_token", "")),
                str(auth.get("account_id", "")),
            )
            vehicle_stats = await client._get(
                "tanks/stats/",
                account_id=str(auth.get("account_id", "")),
            )
            if isinstance(vehicle_stats, dict):
                vehicle_stats = (
                    vehicle_stats.get(str(auth.get("account_id"))) or []
                )
            sections = profile.get("statistics") or {}
            print(
                json.dumps(
                    {
                        "account_stat_sections": {
                            section: sorted(values)
                            for section, values in sections.items()
                            if isinstance(values, dict)
                        },
                        "account_top_level_fields": sorted(
                            key
                            for key, value in sections.items()
                            if not isinstance(value, dict)
                        ),
                        "vehicle_stat_fields": sorted(
                            {key for row in (vehicle_stats or []) for key in row}
                        ),
                        "vehicle_all_fields": sorted(
                            {
                                key
                                for row in (vehicle_stats or [])
                                for key in (row.get("all") or {})
                            }
                        ),
                    },
                    indent=2,
                )
            )
            return
        if private_profile:
            auth = load_wot_auth()
            profile = await client.authenticated_profile(
                str(auth.get("access_token", "")),
                str(auth.get("account_id", "")),
            )
            stats = await client._get(
                "tanks/stats/",
                access_token=str(auth.get("access_token", "")),
                account_id=str(auth.get("account_id", "")),
            )
            if isinstance(stats, dict):
                stats = stats.get(str(auth.get("account_id"))) or []
            public_stats = await client._get(
                "tanks/stats/",
                account_id=str(auth.get("account_id", "")),
            )
            if isinstance(public_stats, dict):
                public_stats = public_stats.get(str(auth.get("account_id"))) or []
            try:
                account_tanks = await client._get(
                    "account/tanks/",
                    access_token=str(auth.get("access_token", "")),
                    account_id=str(auth.get("account_id", "")),
                )
                account_tanks_status = "available"
                if isinstance(account_tanks, dict):
                    account_tanks = (
                        account_tanks.get(str(auth.get("account_id"))) or []
                    )
            except WotApiError as exc:
                account_tanks_status = str(exc)
                account_tanks = []
            private = profile.get("private") or {}
            garage = private.get("garage")
            print(
                json.dumps(
                    {
                        "profile_keys": sorted(profile),
                        "private_keys": sorted(private),
                        "slot_count": private.get("slots"),
                        "empty_slot_count": private.get("empty_slots"),
                        "garage_type": type(garage).__name__,
                        "garage_count": len(garage) if garage is not None else None,
                        "garage_sample": list(garage)[:10]
                        if isinstance(garage, (list, dict))
                        else None,
                        "vehicle_stat_keys": sorted(
                            {key for row in (stats or []) for key in row}
                        ),
                        "has_in_garage_field": any(
                            "in_garage" in row for row in (stats or [])
                        ),
                        "in_garage_counts": {
                            str(value): sum(
                                row.get("in_garage") is value for row in (stats or [])
                            )
                            for value in (True, False, None)
                        },
                        "authenticated_vehicle_count": len(stats or []),
                        "public_vehicle_count": len(public_stats or []),
                        "account_tanks_status": account_tanks_status,
                        "account_tanks_count": len(account_tanks or []),
                        "public_in_garage_counts": {
                            str(value): sum(
                                row.get("in_garage") is value
                                for row in (public_stats or [])
                            )
                            for value in (True, False, None)
                        },
                    },
                    indent=2,
                )
            )
            return
        if auth_url:
            async with session.get(
                f"{config.api_root}/auth/login/",
                params={
                    "application_id": config.application_id,
                    "redirect_uri": "http://localhost:8080/api/wotwom/auth/callback",
                    "nofollow": "1",
                },
                allow_redirects=False,
            ) as response:
                payload = await response.json(content_type=None)
                print(
                    json.dumps(
                        {
                            "http_status": response.status,
                            "api_status": payload.get("status"),
                            "location_present": bool(
                                (payload.get("data") or {}).get("location")
                                or response.headers.get("Location")
                            ),
                            "error": payload.get("error"),
                        },
                        indent=2,
                    )
                )
            return
        if partial:
            data = await client._get(
                "account/list/", search=config.player_name, limit="20"
            )
            print(
                json.dumps(
                    [
                        {
                            "account_id": player.get("account_id"),
                            "nickname": player.get("nickname"),
                        }
                        for player in (data or [])
                    ],
                    indent=2,
                )
            )
            return

        if metadata:
            account_id, _ = await client.resolve_account()
            stats = await client._get("tanks/stats/", account_id=account_id)
            if isinstance(stats, dict):
                stats = stats.get(str(account_id)) or []
            tank_ids = sorted({str(row["tank_id"]) for row in stats or []})
            vehicles = {}
            for start in range(0, len(tank_ids), 100):
                vehicles.update(
                    await client._get(
                        "encyclopedia/vehicles/",
                        tank_id=",".join(tank_ids[start : start + 100]),
                    )
                    or {}
                )
            rows = list(vehicles.values())
            keys = sorted({key for row in rows for key in row})
            print(
                json.dumps(
                    {
                        "keys": keys,
                        "tiers": sorted(
                            {row.get("tier") for row in rows},
                            key=lambda value: (value is None, str(value)),
                        ),
                        "nations": sorted(
                            {str(row.get("nation")) for row in rows}
                        ),
                        "types": sorted({str(row.get("type")) for row in rows}),
                        "era_values": {
                            str(value): sum(row.get("era") == value for row in rows)
                            for value in sorted(
                                {row.get("era") for row in rows},
                                key=lambda item: (item is None, str(item)),
                            )
                        },
                        "era_samples": [
                            {
                                "tank_id": row.get("tank_id"),
                                "name": row.get("short_name") or row.get("name"),
                                "tier": row.get("tier"),
                                "era": row.get("era"),
                                "tag": row.get("tag"),
                            }
                            for row in rows
                            if row.get("era")
                        ][:12],
                        "without_tier": [
                            {
                                key: row.get(key)
                                for key in (
                                    "tank_id",
                                    "name",
                                    "short_name",
                                    "nation",
                                    "type",
                                    "tier",
                                    "tag",
                                    "era",
                                )
                                if key in row
                            }
                            for row in rows
                            if row.get("tier") is None
                        ][:20],
                    },
                    indent=2,
                )
            )
            return

        data = await client.inventory()
        vehicles = data["vehicles"]
        print(
            json.dumps(
                {
                    "account_id": data["account_id"],
                    "nickname": data["nickname"],
                    "vehicle_count": len(vehicles),
                    "mode_counts": {
                        mode: sum(v["mode"] == mode for v in vehicles)
                        for mode in ("wwii", "cold_war")
                    },
                    "sample": vehicles[:5],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Show sanitized partial player-name matches instead of inventory.",
    )
    parser.add_argument(
        "--metadata",
        action="store_true",
        help="Show sanitized Tankopedia field and category metadata.",
    )
    parser.add_argument(
        "--auth-url",
        action="store_true",
        help="Validate that the console sign-in endpoint returns a login URL.",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Show sanitized private-profile and garage metadata.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show account-wide and per-vehicle statistics field names.",
    )
    arguments = parser.parse_args()
    asyncio.run(
        main(
            arguments.partial,
            arguments.metadata,
            arguments.auth_url,
            arguments.private,
            arguments.stats,
        )
    )
