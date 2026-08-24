import asyncio
import logging
import time

from twitchio.ext import commands

from bot.fishing.config import BAITS, BOATS, SPECIES
from bot.fishing.service import get_fishing_service
from bot.overlay_server import broadcast_overlay_message


class FishingCog(commands.Cog):
    """Twitch command adapter; gameplay remains in FishingService."""

    def __init__(self, bot):
        self.bot = bot
        self.service = get_fishing_service()
        self.service.set_broadcaster(self._publish)
        self._started = False
        asyncio.get_running_loop().create_task(self._ensure_started())

    async def _ensure_started(self):
        await self.service.start()
        self._started = True

    async def event_ready(self):
        if not self._started:
            await self._ensure_started()

    async def _publish(self, message):
        await broadcast_overlay_message(message)
        if message.get("type") != "fishing_event":
            return
        text = self._chat_alert(message)
        if not text:
            return
        try:
            channels = getattr(self.bot, "connected_channels", [])
            if channels:
                await channels[0].send(text)
        except Exception:
            logging.warning("[FISHING] Could not send autonomous chat alert", exc_info=True)

    @staticmethod
    def _chat_alert(event):
        p, kind = event["payload"], event["kind"]
        if kind == "catch" and p.get("special") == "mk1220":
            return None
        if kind == "bait_unlocked":
            return f"🎣 {p['display_name']} unlocked {p['bait_label']}! {p['species_name']} can now be targeted with !fish bait {p['species']}"
        if kind == "boat_unlocked":
            if p["boat_tier"] == 4:
                return f"🛳️ {p['display_name'].upper()} HAS ACQUIRED A YACHT."
            icon = "🛥️" if p["boat_tier"] == 3 else "🚤"
            return f"{icon} {p['display_name']} unlocked the {p['boat_name']}!"
        if kind == "catch" and (p.get("tier") == "diamond" or p.get("personal_best") or p.get("lake_record")):
            tags = " • ".join(x for x in ("New PB" if p["personal_best"] else "", "NEW LAKE RECORD" if p["lake_record"] else "") if x)
            return f"🎣 {p['display_name']} caught a {p['weight']:.1f} lb {p['tier'].title()} {p['species_name']} • +{p['points']} Fishing Points" + (f" • {tags}" if tags else "")
        if kind == "mk1220_launched":
            noteworthy = [fish for fish in p.get("catches", []) if fish.get("tier") == "diamond" or fish.get("personal_best") or fish.get("lake_record")]
            if not noteworthy:
                return f"💥 {p['display_name']} fired a Mk. 1220 and caught 5 fish."
            details = " | ".join(
                f"{fish['weight']:.1f} lb {fish['species']}"
                + (" ♦ Diamond" if fish.get("tier") == "diamond" else "")
                + (" • PB" if fish.get("personal_best") else "")
                + (" • LR" if fish.get("lake_record") else "")
                for fish in noteworthy
            )
            return f"💥 {p['display_name']}'s Mk. 1220 caught 5 fish • {details}"
        return None

    @staticmethod
    def _identity(ctx):
        author = ctx.author
        user_id = str(getattr(author, "id", None) or getattr(author, "name", "unknown")).casefold()
        name = getattr(author, "display_name", None) or getattr(author, "name", user_id)
        return user_id, name

    @staticmethod
    def _is_mod_or_broadcaster(author):
        return bool(getattr(author, "is_mod", False) or getattr(author, "is_broadcaster", False))

    @staticmethod
    def _personal_records_text(target):
        stats_by_species = {stat["species"]: stat for stat in target["species"]}
        records = [
            f"{config['name']}: {stats_by_species[species]['personal_best']:.1f} lb"
            for species, config in SPECIES.items()
            if species in stats_by_species and stats_by_species[species]["personal_best"] is not None
        ]
        if not records:
            return None
        return f"🎣 {target['display_name']}'s biggest catches • " + " | ".join(records)

    @commands.Cog.event()
    async def event_message(self, message):
        if getattr(message, "echo", False):
            return
        author = getattr(message, "author", None)
        if not author:
            return
        user_id = str(getattr(author, "id", None) or getattr(author, "name", "unknown")).casefold()
        name = getattr(author, "display_name", None) or getattr(author, "name", user_id)
        try:
            await self.service.note_chat_activity(user_id, name)
        except Exception:
            logging.warning("[FISHING] Could not update angler chat presence", exc_info=True)

    @commands.Cog.event()
    async def event_join(self, channel, user):
        try:
            await self.service.note_viewer_join(getattr(user, "name", ""))
        except Exception:
            logging.warning("[FISHING] Could not process viewer JOIN", exc_info=True)

    @commands.Cog.event()
    async def event_part(self, user):
        try:
            await self.service.note_viewer_part(getattr(user, "name", ""))
        except Exception:
            logging.warning("[FISHING] Could not process viewer PART", exc_info=True)

    @commands.command(name="fish")
    async def fish_command(self, ctx, *args):
        user_id, name = self._identity(ctx)
        sub = (args[0] if args else "").casefold()
        rest = list(args[1:])
        try:
            if sub.startswith("@") and rest and rest[0].casefold() == "records":
                target = await self.service.angler_by_name(sub)
                if not target:
                    return await ctx.send("No fishing stats found for that player.")
                text = self._personal_records_text(target)
                return await ctx.send(text[:450] if text else f"🎣 {target['display_name']} has not caught any fish yet.")
            if sub in ("on", "off"):
                if not self._is_mod_or_broadcaster(ctx.author):
                    return await ctx.send("Only moderators or the broadcaster can power fishing on or off.")
                enabled = sub == "on"
                await self.service.set_power(enabled)
                return await ctx.send(f"🎣 MeanGene Lake is now {'ON' if enabled else 'OFF'}." + (" Viewers may deploy with !fish join." if enabled else " The lake is empty; everyone must join again after it reopens."))
            if sub == "join":
                event = await self.service.set_enabled(user_id, name, True)
                if event["kind"] == "join_waiting":
                    remaining = max(0, int(event["payload"]["cooldown_until"] - time.time()))
                    minutes, seconds = divmod(remaining, 60)
                    reason = "Steve sank your boat" if event["payload"].get("cooldown_reason") == "steve" else "Your hull is still being repaired"
                    return await ctx.send(f"🛠️ @{name}: {reason}. Automatic redeployment in {minutes}m {seconds:02d}s.")
                if event["kind"] == "already_fishing":
                    return await ctx.send(f"🎣 @{name} is already fishing.")
                return await ctx.send(f"🎣 @{name} launched onto MeanGene Lake. Fishing is autonomous.")
            if sub == "stop":
                await self.service.set_enabled(user_id, name, False)
                return await ctx.send(f"🎣 @{name} headed back to shore. Your progress is saved.")
            if sub == "move":
                await self.service.move(user_id)
                return await ctx.send(f"🚤 @{name} reeled in and moved to a new spot.")
            if sub == "gps":
                await self.service.gps(user_id)
                return await ctx.send(f"📍 @{name}'s GPS beacon is flashing on the lake.")
            if sub == "status":
                status = await self.service.status()
                next_action = "none" if status["next_action_in"] is None else f"{status['next_action_in']:.0f}s"
                return await ctx.send(f"🎣 Lake {'ON' if status['enabled'] else 'OFF'} • loop {'running' if status['task_running'] else 'STOPPED'} • {status['weather']} • {status['active']}/{status['opted_in']} active • next action {next_action}")
            if sub == "bait":
                if rest:
                    bait = await self.service.set_bait(user_id, name, " ".join(rest))
                    bait_number = BAITS.index(bait) + 1
                    return await ctx.send(f"🪱 @{name} equipped bait {bait_number}: {bait['label']} to target {SPECIES[bait['target']]['name']}.")
                row = await self.service.angler(user_id)
                if not row:
                    return await ctx.send("Use !fish on first.")
                unlocked = [f"{index}: {bait['label']}" for index, bait in enumerate(BAITS, 1) if row["fishing_points"] >= bait["unlock"]]
                equipped = next((bait for bait in BAITS if bait["id"] == row["active_bait"]), BAITS[0])
                equipped_number = BAITS.index(equipped) + 1
                next_bait = next((bait for bait in BAITS if row["fishing_points"] < bait["unlock"]), None)
                progress = (f" Next unlock: {BAITS.index(next_bait) + 1}: {next_bait['label']} in {next_bait['unlock'] - row['fishing_points']:,} Fishing Points ({row['fishing_points']:,}/{next_bait['unlock']:,})." if next_bait else " All bait tiers unlocked.")
                return await ctx.send(f"🪱 @{name}: bait {equipped_number}: {equipped['label']} equipped. Unlocked: {', '.join(unlocked)}.{progress} Change with !fish bait <number>.")
            if sub in ("boatcolor", "shirt"):
                if not rest:
                    raise ValueError("Use a full hex color like #6f42c1.")
                field = "boat_color" if sub == "boatcolor" else "shirt_color"
                await self.service.set_color(user_id, name, field, rest[0])
                return await ctx.send(f"🎨 @{name} updated {sub} to {rest[0].lower()}.")
            if sub == "sink":
                if not rest:
                    raise ValueError("Usage: !fish sink @user")
                # The service event is formatted once by _publish for chat and both renderers.
                await self.service.sink(user_id, rest[0])
                return
            if sub == "1220":
                await self.service.launch_mk1220(user_id)
                return
            if sub in ("records", "record"):
                if sub == "records" and rest and rest[0].startswith("@"):
                    target = await self.service.angler_by_name(rest[0])
                    if not target:
                        return await ctx.send("No fishing stats found for that player.")
                    text = self._personal_records_text(target)
                    return await ctx.send(text[:450] if text else f"🎣 {target['display_name']} has not caught any fish yet.")
                records = await self.service.records()
                if sub == "record" and rest:
                    species = self.service.species_id(" ".join(rest))
                    records = [r for r in records if r["species"] == species]
                if not records:
                    return await ctx.send("No matching lake record yet.")
                text = " | ".join(f"{SPECIES[r['species']]['name']}: {r['weight']:.1f} lb ({r['display_name']})" for r in records)
                return await ctx.send("🏆 " + text[:450])
            if sub == "diamonds":
                leaders = await self.service.diamond_leaders()
                if not leaders:
                    return await ctx.send("💎 No Diamond fish have been caught yet.")
                ranking = " | ".join(
                    f"{index}. {row['display_name']} — {row['diamond_count']:,}"
                    for index, row in enumerate(leaders, 1)
                )
                return await ctx.send("💎 Diamond leaders: " + ranking)
            if sub == "stats":
                target = await (self.service.angler_by_name(rest[0]) if rest and rest[0].startswith("@") else self.service.angler(user_id))
                species_arg = " ".join(rest[1:] if rest and rest[0].startswith("@") else rest)
                if not target:
                    return await ctx.send("No fishing stats found.")
                if species_arg:
                    sid = self.service.species_id(species_arg)
                    stat = next((s for s in target["species"] if s["species"] == sid), None)
                    if not stat:
                        return await ctx.send("No catches recorded for that species.")
                    return await ctx.send(f"🎣 {target['display_name']} — {SPECIES[sid]['name']}: {stat['catches']} catches, biggest {stat['personal_best']:.1f} lb; medals: Bronze {stat['bronze']}, Silver {stat['silver']}, Gold {stat['gold']}, Diamond {stat['diamond']}.")
                return await ctx.send(f"🎣 {target['display_name']}: {target['total_catches']} fish, {target['fishing_points']:,} Fishing Points, {target['gold']} lifetime gold, tier {target['boat_tier']} {BOATS[target['boat_tier']-1]['name']}, {target['steve_catches']} Steve catch(es), {target['steve_strikes']} Steve strike(s), {target['mk1220']} Mk. 1220 rocket(s), {target['sink_tokens']} sink token(s).")
            if sub == "boat":
                row = await self.service.angler(user_id)
                if not row:
                    return await ctx.send("Use !fish on first.")
                next_boat = next((b for b in BOATS if b["tier"] > row["boat_tier"]), None)
                suffix = f" Next: {next_boat['name']} at {next_boat['unlock']} gold." if next_boat else " Max boat unlocked."
                return await ctx.send(f"🚤 @{name}: {BOATS[row['boat_tier']-1]['name']}, {row['gold']} gold.{suffix}")
            return await ctx.send("🎣 !fish join|stop|move|GPS|status|bait [species]|boat|boatcolor #RRGGBB|shirt #RRGGBB|sink @user|1220|stats [@user] [species]|records [@user]|record <species>|diamonds • Mods: !fish on|off")
        except ValueError as exc:
            await ctx.send(f"🎣 {exc}")


def prepare(bot):
    if not bot.get_cog("FishingCog"):
        bot.add_cog(FishingCog(bot))
