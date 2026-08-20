import shlex
import asyncio
from datetime import datetime, timedelta, timezone
import re
import random

from twitchio.ext import commands

from bot.faction_service import FactionService
from bot.twitch_eligibility import check_join_eligibility


class FactionCog(commands.Cog):
    DERPDAWG_RELIC_ID = "derp"
    GMB_RELIC_ID = "gmb"
    STREAM_ACTIVITY_REWARD_TYPES = {
        "meaningful_chat",
        "zap_trigger",
        "zap_faction_echo",
        "stream_activity",
    }
    RELIC_ALIASES = {
        "gmb": "gmb",
        "milkbone": "gmb",
        "goldenmilkbone": "gmb",
        "golden_milkbone": "gmb",
        "derpdawg": "derp",
        "derp": "derp",
    }
    RELIC_BATTLE_JOIN_SECONDS = 300
    RELIC_BATTLE_COOLDOWN_SECONDS = 300
    RELIC_DEFENDER_NERF_POINTS = 10

    def __init__(self, bot):
        self.bot = bot
        self.service = FactionService()
        self.chat_reward_cooldown_seconds = 120
        self.min_meaningful_length = 4
        self.duplicate_window_minutes = 15
        self._last_raffle_open_state = None
        self._stream_session_bootstrapped = False
        self._active_relic_battle = None
        self._active_relic_battle_task = None
        self._relic_battle_cooldowns = {}

    def award_entry_reward(self, username: str, entries: int, *, reward_type: str = "stream_activity") -> dict:
        username = str(username or "").strip().lower()
        requested = max(0, int(entries or 0))
        if not username or requested <= 0:
            return {
                "requested": requested,
                "applied": 0,
                "derpdawg_floor_applied": False,
                "gmb_applied": False,
                "capacity_reason": "invalid_reward_request",
            }

        raffle_cog = self.bot.get_cog("RaffleCog")
        if not raffle_cog or not hasattr(raffle_cog, "state"):
            return {
                "requested": requested,
                "applied": 0,
                "derpdawg_floor_applied": False,
                "gmb_applied": False,
                "capacity_reason": "raffle_unavailable",
            }

        effective_entries = requested
        derpdawg_floor_applied = False
        gmb_applied = False
        user_faction = self.service.get_user_faction(username)

        is_stream_activity_reward = str(reward_type or "").strip().lower() in self.STREAM_ACTIVITY_REWARD_TYPES
        if user_faction and is_stream_activity_reward and requested == 1:
            if self.service.faction_owns_relic(user_faction.id, self.DERPDAWG_RELIC_ID):
                effective_entries = 2
                derpdawg_floor_applied = True

        if user_faction and self.service.faction_owns_relic(user_faction.id, "gmb"):
            effective_entries *= 2
            gmb_applied = True

        if hasattr(raffle_cog.state, "add_entries_capped"):
            capped = raffle_cog.state.add_entries_capped(username, effective_entries)
            return {
                "requested": requested,
                "applied": int(capped.get("applied", 0)),
                "derpdawg_floor_applied": derpdawg_floor_applied,
                "gmb_applied": gmb_applied,
                "capacity_reason": capped.get("truncation_reason"),
            }

        ok = raffle_cog.state.add_entries(username, effective_entries)
        return {
            "requested": requested,
            "applied": effective_entries if ok else 0,
            "derpdawg_floor_applied": derpdawg_floor_applied,
            "gmb_applied": gmb_applied,
            "capacity_reason": None if ok else "entry_grant_failed",
        }

    @staticmethod
    def _format_cooldown(remaining: timedelta) -> str:
        total_seconds = int(remaining.total_seconds())
        if total_seconds <= 0:
            return "0m"
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    async def _send_faction_list(self, ctx):
        factions = self.service.list_factions()
        commissioner = self.service.get_commissioner()

        if not factions:
            await ctx.send("No factions have been created yet.")
            return

        lines = []
        for faction in factions:
            commissioner_marker = " | Commissioner" if commissioner and commissioner.get("faction_id") == faction.id else ""
            relic_marker = " | Golden Milkbone" if faction.owns_relic else ""
            lines.append(
                f"[{faction.id}] {faction.name} | Head: @{faction.head_username} | Influence: {faction.influence} | Active: {faction.active_member_count} | Members: {faction.member_count}{commissioner_marker}{relic_marker}"
            )

        await ctx.send("Factions: " + " || ".join(lines))

    def _resolve_faction_reference(self, raw_ref: str):
        raw_ref = raw_ref.strip()
        if raw_ref.isdigit():
            return self.service.get_faction_by_id(int(raw_ref))
        return self.service.get_faction_by_name(raw_ref)

    @staticmethod
    def _roll_relic_battle_score(faction, *, is_defending_owner: bool, defense_bonus: int) -> int:
        active_weight = int(faction.active_member_count or 0) * 25
        member_weight = int(faction.member_count or 0) * 5
        influence_weight = int(faction.influence or 0)
        owner_defense = int(defense_bonus or 0) if is_defending_owner else 0
        variance = random.randint(1, 100)
        return influence_weight + active_weight + member_weight + owner_defense + variance

    def _normalize_relic_id(self, raw_relic_id: str) -> str:
        key = str(raw_relic_id or "").strip().lower()
        return self.RELIC_ALIASES.get(key, key)

    def _relic_battle_status_text(self) -> str:
        battle = self._active_relic_battle
        if not battle:
            return "No active relic battle."

        now = datetime.now(timezone.utc)
        remaining = max(0, int((battle["ends_at"] - now).total_seconds()))
        participant_ids = sorted(list(battle["participants"]))
        factions = [self.service.get_faction_by_id(fid) for fid in participant_ids]
        names = [f.name for f in factions if f]
        names_text = ", ".join(names) if names else "(none yet)"
        return (
            f"Relic battle open for {battle['display_name']}. "
            f"Time left: {remaining}s. Joined factions: {names_text}."
        )

    def _relic_cooldown_remaining(self, relic_id: str) -> int:
        next_allowed = self._relic_battle_cooldowns.get(str(relic_id or "").strip().lower())
        if not next_allowed:
            return 0
        return max(0, int((next_allowed - datetime.now(timezone.utc)).total_seconds()))

    async def _resolve_active_relic_battle(self):
        battle = self._active_relic_battle
        if not battle:
            return

        now = datetime.now(timezone.utc)
        delay = max(0.0, (battle["ends_at"] - now).total_seconds())
        if delay > 0:
            await asyncio.sleep(delay)

        # If a newer battle replaced this one, do nothing.
        if battle is not self._active_relic_battle:
            return

        channel = battle["channel"]
        relic_id = battle["relic_id"]
        relic = self.service.get_relic(relic_id)
        if not relic or not relic.get("is_active"):
            self._active_relic_battle = None
            self._active_relic_battle_task = None
            await channel.send("Relic battle ended: relic became unavailable.")
            return

        faction_ids = sorted(list(battle["participants"]))
        participating_factions = [self.service.get_faction_by_id(fid) for fid in faction_ids]
        participating_factions = [f for f in participating_factions if f is not None]
        if len(participating_factions) < 2:
            self._active_relic_battle = None
            self._active_relic_battle_task = None
            await channel.send("Relic battle canceled: fewer than 2 factions joined during the join window.")
            return

        owner_id = relic.get("owner_faction_id")
        defense_bonus = int(relic.get("defense_bonus") or 0)
        scored = []
        for faction in participating_factions:
            is_owner = bool(owner_id) and int(owner_id) == faction.id
            base_score = self._roll_relic_battle_score(
                faction,
                is_defending_owner=is_owner,
                defense_bonus=defense_bonus,
            )
            nerf = self.RELIC_DEFENDER_NERF_POINTS if is_owner else 0
            final_score = max(0, base_score - nerf)
            scored.append((faction, base_score, nerf, final_score))

        max_score = max(final_score for _, _, _, final_score in scored)
        tied = [faction for faction, _, _, final_score in scored if final_score == max_score]
        winner = random.choice(tied)
        ok, message = self.service.set_relic_owner(relic_id, winner.id, acted_by=battle["started_by"])

        self._relic_battle_cooldowns[relic_id] = datetime.now(timezone.utc) + timedelta(
            seconds=self.RELIC_BATTLE_COOLDOWN_SECONDS
        )

        self._active_relic_battle = None
        self._active_relic_battle_task = None

        if not ok:
            await channel.send(f"Relic battle resolution failed: {message}")
            return

        scored_sorted = sorted(scored, key=lambda item: item[3], reverse=True)
        score_text = " | ".join(
            f"{faction.name}:{final_score}"
            + (f" ({base_score}-{nerf} defense nerf)" if nerf > 0 else "")
            for faction, base_score, nerf, final_score in scored_sorted
        )
        await channel.send(
            f"⚔️ Relic battle resolved for {relic['display_name']}! Winner: {winner.name}. {message} Scores: {score_text}"
        )

    def _auto_select_challenger(self, factions, defender_id: int):
        candidates = [f for f in factions if f.id != defender_id]
        if not candidates:
            return None
        candidates.sort(
            key=lambda f: (
                int(f.active_member_count or 0),
                int(f.influence or 0),
                int(f.member_count or 0),
            ),
            reverse=True,
        )
        return candidates[0]

    def _sync_stream_session_from_raffle_state(self) -> bool:
        raffle_cog = self.bot.get_cog("RaffleCog")
        if not raffle_cog or not hasattr(raffle_cog, "state"):
            return False

        raffle_is_open = bool(getattr(raffle_cog.state, "is_open", False))
        self._sync_stream_session(raffle_is_open)
        return True

    def _sync_stream_session(self, raffle_is_open: bool):
        if self._last_raffle_open_state is None:
            self._last_raffle_open_state = raffle_is_open
            if raffle_is_open and not self._stream_session_bootstrapped:
                # On startup while raffle is already open, start a fresh activity session
                # so stale activity from a previous stream is never reused.
                self.service.start_new_stream_session()
                self._stream_session_bootstrapped = True
            elif not raffle_is_open:
                self.service.end_current_stream_session()
            return

        if raffle_is_open and not self._last_raffle_open_state:
            self.service.start_new_stream_session()
        elif not raffle_is_open and self._last_raffle_open_state:
            self.service.end_current_stream_session()

        self._last_raffle_open_state = raffle_is_open

    @staticmethod
    def _normalize_message(content: str) -> str:
        compact = re.sub(r"\s+", " ", content.strip().lower())
        return compact

    def _is_meaningful_message(self, normalized: str) -> bool:
        if not normalized:
            return False
        no_space = normalized.replace(" ", "")
        if len(no_space) < self.min_meaningful_length:
            return False
        alpha_num_chars = sum(1 for c in no_space if c.isalnum())
        if alpha_num_chars < self.min_meaningful_length:
            return False
        return True

    @staticmethod
    def _roll_faction_echo_jackpot() -> int:
        roll = random.random() * 100.0
        if roll < 70.0:
            return 1
        if roll < 90.0:
            return 2
        if roll < 97.0:
            return 5
        if roll < 99.0:
            return 10
        if roll < 99.95:
            return 25
        return 50

    async def _award_faction_echo_jackpot(self, message, trigger_username: str, faction, reason: str):
        raffle_cog = self.bot.get_cog("RaffleCog")
        if not raffle_cog or not hasattr(raffle_cog, "state"):
            return

        # Avoid echo rewards in very low-activity sessions.
        stream_active_members = self.service.get_active_members_for_current_session()
        if len(stream_active_members) < 2:
            return

        active_members = self.service.get_active_members_for_faction_current_session(faction.id)
        if len(active_members) < 2:
            return

        # Prefer awarding someone other than the triggering chatter when possible.
        candidates = [u for u in active_members if u != trigger_username]
        if not candidates:
            candidates = [trigger_username] if trigger_username in active_members else active_members

        random.shuffle(candidates)
        jackpot_entries = self._roll_faction_echo_jackpot()

        recipient = None
        for candidate in candidates:
            try:
                if raffle_cog.state.add_entries(candidate, jackpot_entries):
                    recipient = candidate
                    break
            except Exception:
                continue

        if not recipient:
            return

        await message.channel.send(
            f"⚡ Faction Echo Jackpot: @{recipient} gains +{jackpot_entries} entries for {faction.name} "
            f"({reason}: @{trigger_username})."
        )

    @commands.command(name="factions")
    async def factions_command(self, ctx):
        self._sync_stream_session_from_raffle_state()
        await self._send_faction_list(ctx)

    @commands.command(name="commissioner")
    async def commissioner_command(self, ctx):
        parts = shlex.split(ctx.message.content)
        args = parts[1:]

        if not args:
            commissioner = self.service.get_commissioner()
            if not commissioner:
                await ctx.send("Commissioner seat is currently vacant.")
                return
            await ctx.send(f"Current Stream Commissioner: @{commissioner['username']}")
            return

        if not getattr(ctx.author, "is_mod", False):
            await ctx.send("Only mods can appoint the commissioner.")
            return

        target = args[0].strip().lower()
        if target in {"clear", "none", "vacant"}:
            ok, message = self.service.clear_commissioner(ctx.author.name)
            await ctx.send(message if ok else "Failed to clear commissioner.")
            return

        ok, message = self.service.set_commissioner(target, ctx.author.name)
        await ctx.send(message)

    @commands.command(name="faction")
    async def faction_command(self, ctx):
        self._sync_stream_session_from_raffle_state()
        parts = shlex.split(ctx.message.content)
        args = parts[1:]
        username = ctx.author.name.lower()

        if not args:
            current = self.service.get_user_faction(username)
            cooldown = self.service.get_cooldown_remaining(username)
            if current:
                await ctx.send(
                    f"@{username} | Faction: {current.name} | Head: @{current.head_username} | Influence: {current.influence} | Members: {current.member_count}"
                )
                return

            if cooldown > timedelta(0):
                await ctx.send(
                    f"@{username} is factionless. Join cooldown remaining: {self._format_cooldown(cooldown)}."
                )
            else:
                await ctx.send(f"@{username} is factionless. Use !factions then !faction join <number>.")
            return

        action = args[0].lower()

        if action == "create":
            if not getattr(ctx.author, "is_mod", False):
                await ctx.send("Only mods can create factions.")
                return
            if len(args) < 3:
                await ctx.send("Usage: !faction create \"Faction Name\" @FactionHead")
                return

            head = args[-1]
            faction_name = " ".join(args[1:-1]).strip()
            ok, message = self.service.create_faction(faction_name, head)
            await ctx.send(message)
            return

        if action == "disband":
            if not getattr(ctx.author, "is_mod", False):
                await ctx.send("Only mods can disband factions.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !faction disband \"Faction Name\"")
                return

            faction_name = " ".join(args[1:]).strip()
            ok, message = self.service.disband_faction(faction_name)
            await ctx.send(message)
            return

        if action == "join":
            if len(args) < 2:
                await ctx.send("Usage: !faction join <number|name>")
                return

            current = self.service.get_user_faction(username)
            if current:
                await ctx.send(f"@{username}, you are already in {current.name}. Use !faction leave first.")
                return

            cooldown = self.service.get_cooldown_remaining(username)
            if cooldown > timedelta(0):
                await ctx.send(
                    f"@{username}, faction switch cooldown active. Time remaining: {self._format_cooldown(cooldown)}."
                )
                return

            eligible, reason = await check_join_eligibility(username)
            if not eligible:
                await ctx.send(reason)
                return

            faction_ref = " ".join(args[1:]).strip()
            faction = self._resolve_faction_reference(faction_ref)
            if not faction:
                await ctx.send("Faction not found. Use !factions to view valid numbers.")
                return

            ok, message = self.service.join_faction(username, faction.id)
            if not ok:
                await ctx.send(message)
                return

            join_bonus_awarded = False
            raffle_cog = self.bot.get_cog("RaffleCog")
            if raffle_cog and hasattr(raffle_cog, "state"):
                try:
                    join_bonus_awarded = bool(raffle_cog.state.add_entries(username, 1))
                except Exception:
                    join_bonus_awarded = False

            if join_bonus_awarded:
                await ctx.send(f"{message} +1 raffle entry awarded. {faction.name} gains +10 influence.")
            else:
                await ctx.send(f"{message} {faction.name} gains +10 influence.")
            return

        if action == "leave":
            ok, message = self.service.leave_faction(username)
            if not ok:
                await ctx.send(message)
                return
            await ctx.send(
                f"{message} You now have a 7-day cooldown before joining another faction."
            )
            return

        if action == "battle":
            if len(args) < 2:
                await ctx.send("Usage: !faction battle <relic_id>|join|status|cancel")
                return

            battle_arg = args[1].strip().lower()

            if battle_arg == "status":
                await ctx.send(self._relic_battle_status_text())
                return

            if battle_arg == "join":
                battle = self._active_relic_battle
                if not battle:
                    await ctx.send("No active relic battle to join.")
                    return

                faction = self.service.get_user_faction(username)
                if not faction:
                    await ctx.send(f"@{username}, you must be in a faction to join this relic battle.")
                    return

                now = datetime.now(timezone.utc)
                if now >= battle["ends_at"]:
                    await ctx.send("Join window has closed for this relic battle.")
                    return

                if faction.id in battle["participants"]:
                    await ctx.send(f"{faction.name} is already entered in this relic battle.")
                    return

                battle["participants"].add(faction.id)
                await ctx.send(
                    f"⚑ {faction.name} joined the relic battle for {battle['display_name']}! "
                    f"Use !faction battle status for current entrants."
                )
                return

            if battle_arg == "cancel":
                if not getattr(ctx.author, "is_mod", False):
                    await ctx.send("Only mods can cancel relic battles.")
                    return
                if not self._active_relic_battle:
                    await ctx.send("No active relic battle to cancel.")
                    return
                self._active_relic_battle = None
                task = self._active_relic_battle_task
                self._active_relic_battle_task = None
                if task and not task.done():
                    task.cancel()
                await ctx.send("Active relic battle canceled.")
                return

            # Start battle mode: !faction battle <relic_id>
            if not getattr(ctx.author, "is_mod", False):
                await ctx.send("Only mods can start faction relic battles.")
                return

            if len(args) > 2:
                await ctx.send("Usage: !faction battle <relic_id>")
                return

            if self._active_relic_battle:
                await ctx.send("A relic battle is already active. Use !faction battle status.")
                return

            relic_id = self._normalize_relic_id(args[1])
            relic = self.service.get_relic(relic_id)
            if not relic or not relic.get("is_active"):
                await ctx.send(f"Unknown or inactive relic: {args[1]}.")
                return

            cooldown_remaining = self._relic_cooldown_remaining(relic_id)
            if cooldown_remaining > 0:
                await ctx.send(
                    f"{relic['display_name']} battle cooldown active: {cooldown_remaining}s remaining."
                )
                return

            factions = self.service.list_factions()
            if len(factions) < 2:
                await ctx.send("At least two active factions are required to run a relic battle.")
                return

            ends_at = datetime.now(timezone.utc) + timedelta(seconds=self.RELIC_BATTLE_JOIN_SECONDS)
            participant_ids = set()
            owner_id = relic.get("owner_faction_id")
            owner_faction = None
            if owner_id:
                owner_faction = self.service.get_faction_by_id(int(owner_id))
                if owner_faction:
                    participant_ids.add(owner_faction.id)

            self._active_relic_battle = {
                "relic_id": relic_id,
                "display_name": relic["display_name"],
                "started_by": ctx.author.name,
                "channel": ctx.channel,
                "ends_at": ends_at,
                "participants": participant_ids,
            }
            self._active_relic_battle_task = self.bot.loop.create_task(self._resolve_active_relic_battle())

            auto_owner_text = ""
            if owner_faction:
                auto_owner_text = f" Current holder {owner_faction.name} is auto-entered as defender."

            await ctx.send(
                f"⚔️ Relic battle started for {relic['display_name']}! "
                f"Join window: {self.RELIC_BATTLE_JOIN_SECONDS}s. "
                f"Any faction member can join their faction with !faction battle join. "
                f"Defender nerf: -{self.RELIC_DEFENDER_NERF_POINTS} to the relic holder in final scoring.{auto_owner_text}"
            )
            return

        await ctx.send("Usage: !faction [create|disband|join|leave|battle]")

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        if not message.author or not message.content:
            return

        username = message.author.name.lower()
        content = message.content.strip()

        raffle_cog = self.bot.get_cog("RaffleCog")
        if not raffle_cog or not hasattr(raffle_cog, "state"):
            return

        raffle_is_open = bool(getattr(raffle_cog.state, "is_open", False))
        self._sync_stream_session(raffle_is_open)

        # Skip command messages from activity rewards, but only after stream
        # session sync so commands like !factions show fresh active counts.
        if content.startswith("!"):
            return

        # Respect existing raffle session lifecycle.
        if not raffle_is_open:
            return

        normalized = self._normalize_message(content)
        if not self._is_meaningful_message(normalized):
            return

        now = datetime.now(timezone.utc)
        state = self.service.get_chat_state(username)

        last_message_norm = state.get("last_message_norm")
        last_message_at = state.get("last_message_at")
        if last_message_norm == normalized and last_message_at:
            if now - last_message_at <= timedelta(minutes=self.duplicate_window_minutes):
                return

        last_reward_at = state.get("last_reward_at")
        current_faction = self.service.get_user_faction(username)
        first_faction_reward_this_stream = bool(current_faction) and not self.service.has_stream_activity_for_current_session(username)

        if (
            last_reward_at
            and (now - last_reward_at).total_seconds() < self.chat_reward_cooldown_seconds
            and not first_faction_reward_this_stream
        ):
            self.service.update_chat_state(
                username,
                last_reward_at=last_reward_at,
                last_message_norm=normalized,
                last_message_at=now,
            )
            return

        reward_result = self.award_entry_reward(
            username,
            1,
            reward_type="meaningful_chat",
        )
        reward_ok = reward_result.get("applied", 0) > 0

        if not reward_ok:
            self.service.update_chat_state(
                username,
                last_reward_at=last_reward_at,
                last_message_norm=normalized,
                last_message_at=now,
            )
            return

        rewarded_faction_name = self.service.apply_meaningful_chat_reward(username, influence_amount=1)
        self.service.update_chat_state(
            username,
            last_reward_at=now,
            last_message_norm=normalized,
            last_message_at=now,
        )

        if current_faction and rewarded_faction_name:
            echo_trigger_allowed = self.service.try_mark_echo_triggered_for_current_session(username)
            if echo_trigger_allowed:
                await self._award_faction_echo_jackpot(
                    message,
                    username,
                    current_faction,
                    "first faction chat this stream",
                )

        # Provide lightweight visibility once per stream so members can confirm the
        # faction activity reward is being applied.
        if first_faction_reward_this_stream and rewarded_faction_name:
            await message.channel.send(
                f"⚑ @{username} faction activity recorded for {rewarded_faction_name} (+1 influence)."
            )


def prepare(bot):
    if not bot.get_cog("FactionCog"):
        bot.add_cog(FactionCog(bot))
