import asyncio
import logging
from datetime import datetime, timedelta, timezone

from twitchio.ext import commands

from bot.bittleships_state import (
    BittleshipsManager,
    MAX_SHIPS,
    normalize_username,
    parse_coordinate,
)
from bot.overlay_server import broadcast_overlay_message


LOGGER = logging.getLogger("bittleships")
ACTIVE_WINDOW = timedelta(minutes=10)
COORDINATE_COMMANDS = [
    f"{letter.lower()}{number}"
    for letter in "ABCDEFGHIJ"
    for number in range(1, 11)
]
USAGE = (
    "Bittleships: !ships status | !A5 to fire | !ships join | "
    "Admiral: !ships start <ships>, !ships give @user [shots] | "
    "Mod: !ships classic <minutes> [fighter], !ships skip, !ships stop, !ships resume"
)


class BittleshipsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = BittleshipsManager()
        self.recent_chatters = {}
        self.classic_join_task = None
        self.classic_turn_task = None
        self.classic_channel = None
        try:
            bot.loop.create_task(self._broadcast_startup_state())
        except Exception:
            LOGGER.exception("Failed to schedule Bittleships startup broadcast")

    async def _broadcast_startup_state(self):
        await asyncio.sleep(1)
        await self._broadcast()
        if self.manager.state.get("mode") == "classic" and self.manager.state.get("phase") == "joining":
            self._schedule_classic_close()
        elif self.manager.state.get("mode") == "classic" and self.manager.state.get("phase") == "playing":
            self._schedule_classic_turn_timeout()

    def _schedule_classic_close(self):
        if self.classic_join_task and not self.classic_join_task.done():
            self.classic_join_task.cancel()
        self.classic_join_task = self.bot.loop.create_task(self._close_classic_join())

    async def _close_classic_join(self):
        deadline_raw = self.manager.state.get("classic", {}).get("join_deadline")
        if deadline_raw:
            try:
                deadline = datetime.fromisoformat(deadline_raw)
                delay = max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds())
                await asyncio.sleep(delay)
            except (TypeError, ValueError):
                pass
        if self.manager.state.get("mode") != "classic" or self.manager.state.get("phase") != "joining":
            return
        order = self.manager.begin_classic()
        if not order:
            self.manager.restore_suspended_game(
                "Classic signup ended with no players. Giveaway board restored."
            )
        await self._broadcast()
        channel = self._get_classic_channel()
        if not channel:
            if order:
                self._schedule_classic_turn_timeout()
            return
        if not order:
            await channel.send("Classic Bittleships signup closed with no players. Game cancelled.")
            return
        self._schedule_classic_turn_timeout()
        await channel.send(
            f"⚓ Classic Bittleships begins! Turn order: "
            f"{', '.join('@' + player for player in order)}. "
            f"@{order[0]}, fire with !A5."
        )

    def _get_classic_channel(self):
        if self.classic_channel:
            return self.classic_channel
        channels = getattr(self.bot, "connected_channels", None) or []
        return channels[0] if channels else None

    def _schedule_classic_turn_timeout(self):
        if self.classic_turn_task and not self.classic_turn_task.done():
            self.classic_turn_task.cancel()
        if self.manager.state.get("mode") != "classic" or self.manager.state.get("phase") != "playing":
            self.classic_turn_task = None
            return
        classic = self.manager.state.get("classic", {})
        deadline = classic.get("turn_deadline")
        order = classic.get("turn_order", [])
        if not deadline or not order:
            self.classic_turn_task = None
            return
        current = order[classic.get("turn_index", 0)]
        self.classic_turn_task = self.bot.loop.create_task(
            self._timeout_classic_turn(current, deadline)
        )

    async def _timeout_classic_turn(self, expected_player, expected_deadline):
        try:
            deadline = datetime.fromisoformat(expected_deadline)
            delay = max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds())
            await asyncio.sleep(delay)
            self.classic_turn_task = None
            skipped = self.manager.skip_classic_turn(
                expected_player=expected_player,
                expected_deadline=expected_deadline,
            )
        except asyncio.CancelledError:
            return
        except (TypeError, ValueError):
            return
        await self._broadcast()
        current = self.manager.public_payload()["classic"]["current_player"]
        channel = self._get_classic_channel()
        if channel:
            await channel.send(
                f"⏱️ @{skipped}'s 60-second turn expired and was skipped. @{current} is up."
            )
        self._schedule_classic_turn_timeout()

    async def _broadcast(self, message=None):
        await broadcast_overlay_message(self.manager.public_payload(message=message))

    @staticmethod
    def _is_mod_or_broadcaster(author) -> bool:
        return bool(
            getattr(author, "is_mod", False)
            or getattr(author, "is_broadcaster", False)
        )

    def _is_admiral(self, author) -> bool:
        return normalize_username(getattr(author, "name", "")) == self.manager.admiral

    def _active_target(self, username):
        target = normalize_username(username)
        last_seen = self.recent_chatters.get(target)
        if not last_seen:
            return False
        return datetime.now(timezone.utc) - last_seen <= ACTIVE_WINDOW

    @commands.Cog.event()
    async def event_message(self, message):
        if getattr(message, "echo", False):
            return
        author = getattr(message, "author", None)
        if not author:
            return
        username = normalize_username(getattr(author, "name", ""))
        if username:
            self.recent_chatters[username] = datetime.now(timezone.utc)

    @commands.command(name="admiral")
    async def admiral_command(self, ctx):
        if not self._is_mod_or_broadcaster(ctx.author):
            await ctx.send("Only moderators or the broadcaster can assign the admiral.")
            return
        parts = ctx.message.content.split()
        if len(parts) < 2 or parts[1].lower() in ("status", "show"):
            admiral = self.manager.admiral
            await ctx.send(f"Current Bittleships admiral: @{admiral}" if admiral else "Bittleships has no admiral.")
            return
        if parts[1].lower() in ("clear", "remove", "none"):
            self.manager.clear_admiral()
            await self._broadcast()
            await ctx.send("Bittleships admiral cleared.")
            return
        target = normalize_username(parts[1])
        if not target:
            await ctx.send("Usage: !admiral @username | !admiral clear")
            return
        self.manager.set_admiral(target)
        await self._broadcast()
        await ctx.send(
            f"⚓ @{target} is now the Bittleships admiral. "
            "They command with !ships start <ships> and !ships give @user [shots]. "
            "They cannot receive shots in giveaway mode, but may join Classic."
        )

    @commands.command(name="ships")
    async def ships_command(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send(USAGE)
            return
        action = parts[1].lower()
        args = parts[2:]

        if action == "start":
            await self._handle_start(ctx, args)
        elif action == "classic":
            await self._handle_classic(ctx, args)
        elif action == "join":
            await self._handle_join(ctx)
        elif action in ("give", "grant", "shot", "shots"):
            await self._handle_give(ctx, args)
        elif action in ("status", "info", "board"):
            await self._handle_status(ctx)
        elif action in ("stop", "end"):
            await self._handle_stop(ctx)
        elif action == "skip":
            await self._handle_skip(ctx)
        elif action == "resume":
            await self._handle_resume(ctx)
        else:
            await ctx.send(USAGE)

    async def _handle_start(self, ctx, args):
        if not self._is_admiral(ctx.author):
            await ctx.send("Only the assigned admiral can start a Bittleships game.")
            return
        if len(args) != 1:
            await ctx.send(f"Usage: !ships start <1-{MAX_SHIPS}>")
            return
        try:
            ship_count = int(args[0])
            self.manager.start_game(ship_count)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await self._broadcast()
        await ctx.send(
            f"🚢 Bittleships started with {ship_count} hidden one-space "
            f"ship{'s' if ship_count != 1 else ''} on a 10×10 grid!"
        )

    async def _handle_give(self, ctx, args):
        if not self._is_admiral(ctx.author):
            await ctx.send("Only the assigned admiral can grant shots.")
            return
        if not args:
            await ctx.send("Usage: !ships give @username [shots]")
            return
        target = normalize_username(args[0])
        count = 1
        if len(args) > 1:
            try:
                count = int(args[1])
            except ValueError:
                await ctx.send("Shot count must be a whole number from 1 to 20.")
                return
        if target == self.manager.admiral:
            await ctx.send("The admiral cannot receive shots or play.")
            return
        if not self._active_target(target):
            await ctx.send(
                f"@{target} is not active. They must speak in chat within the last "
                "10 minutes before receiving a shot."
            )
            return
        try:
            total = self.manager.grant_shots(target, count)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await self._broadcast()
        await ctx.send(
            f"🎯 @{target} received {count} shot{'s' if count != 1 else ''} "
            f"({total} available). Fire with !A5."
        )

    async def _handle_classic(self, ctx, args):
        if not self._is_mod_or_broadcaster(ctx.author):
            await ctx.send("Only moderators or the broadcaster can open Classic mode.")
            return
        if not args:
            await ctx.send("Usage: !ships classic <1-10 minutes> [fighter]")
            return
        try:
            minutes = int(args[0])
        except ValueError:
            await ctx.send("Classic join time must be a whole number of minutes.")
            return
        fighter = any(arg.lower() in ("fighter", "jet", "on", "yes") for arg in args[1:])
        try:
            self.manager.start_classic_join(minutes, fighter_enabled=fighter)
        except (ValueError, RuntimeError) as exc:
            await ctx.send(str(exc))
            return
        self.classic_channel = ctx.channel
        self._schedule_classic_close()
        await self._broadcast()
        fighter_text = " A moving fighter is enabled." if fighter else ""
        await ctx.send(
            f"🚢 Classic Bittleships signup is open for {minutes} minute"
            f"{'s' if minutes != 1 else ''}! Join with !ships join.{fighter_text}"
        )

    async def _handle_join(self, ctx):
        phase = self.manager.state.get("phase")
        shots_fired = bool(self.manager.state.get("revealed"))
        try:
            player_count = self.manager.join_classic(ctx.author.name)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await self._broadcast()
        if phase == "playing" and shots_fired:
            await ctx.send(
                f"@{ctx.author.name} joined Classic Bittleships and will be added "
                f"to the end of the next round ({player_count} players)."
            )
            return
        if phase == "playing":
            await ctx.send(
                f"@{ctx.author.name} joined before the first shot and was added "
                f"to the end of the current round ({player_count} players)."
            )
            return
        await ctx.send(
            f"⚓ @{ctx.author.name} joined Classic Bittleships "
            f"({player_count} player{'s' if player_count != 1 else ''})."
        )

    @commands.command(
        name=COORDINATE_COMMANDS[0],
        aliases=COORDINATE_COMMANDS[1:],
    )
    async def coordinate_fire_command(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) != 1:
            await ctx.send("Usage: !A5")
            return
        command = parts[0].lstrip("!")
        coordinate = parse_coordinate(command)
        if coordinate:
            await self._handle_fire(ctx, [coordinate])

    async def _handle_fire(self, ctx, args):
        if len(args) != 1:
            await ctx.send("Usage: !A5")
            return
        if self.manager.state.get("mode") == "classic":
            await self._handle_classic_fire(ctx, args[0])
            return
        try:
            result, shots_left, won = self.manager.fire(ctx.author.name, args[0])
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        coordinate = args[0].upper()
        await self._broadcast()
        if won:
            await ctx.send(f"💥 @{ctx.author.name} fires at {coordinate}: HIT! All ships sunk—victory!")
        elif result == "hit":
            await ctx.send(f"💥 @{ctx.author.name} fires at {coordinate}: HIT! {shots_left} shot(s) left.")
        else:
            await ctx.send(f"🌊 @{ctx.author.name} fires at {coordinate}: MISS. {shots_left} shot(s) left.")

    async def _handle_classic_fire(self, ctx, coordinate):
        try:
            outcome = self.manager.classic_fire(ctx.author.name, coordinate)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await self._broadcast()
        result_text = "HIT" if outcome["result"] == "hit" else "MISS"
        sink_text = (
            f" {outcome['sunk']} destroyed—bonus point!"
            if outcome["sunk"] else ""
        )
        if outcome.get("sudden_death_started"):
            self._schedule_classic_turn_timeout()
            tied = self.manager.public_payload()["classic"]["sudden_death_players"]
            await ctx.send(
                f"💥 @{ctx.author.name} fires at {coordinate.upper()}: {result_text}!{sink_text} "
                f"Fleet destroyed, but the lead is tied between "
                f"{', '.join('@' + player for player in tied)}. SUDDEN DEATH! "
                f"A fighter is in play; first hit wins. Next: @{outcome['next_player']}."
            )
            return
        if outcome["won"]:
            self._schedule_classic_turn_timeout()
            winner = outcome.get("winner") or ctx.author.name
            winner_score = outcome.get("winner_score")
            if winner_score is None:
                winner_score = outcome["score"]["points"]
            await ctx.send(
                f"💥 @{ctx.author.name} fires at {coordinate.upper()}: {result_text}!{sink_text} "
                + (
                    f"Sudden-death fighter destroyed! Winner: @{winner}."
                    if outcome.get("sudden_death")
                    else f"Fleet destroyed! Winner: @{winner} with {winner_score} "
                    f"point{'s' if winner_score != 1 else ''}."
                )
            )
            winner_summary = (
                f"Classic complete. Winner: @{winner} ({winner_score} points). "
                "Giveaway board restored."
            )
            self.manager.restore_suspended_game(winner_summary)
            await self._broadcast()
            return
        self._schedule_classic_turn_timeout()
        await ctx.send(
            f"{'💥' if outcome['result'] == 'hit' else '🌊'} @{ctx.author.name} fires at "
            f"{coordinate.upper()}: {result_text}!{sink_text} "
            f"Next: @{outcome['next_player']} (Round {outcome['round']})."
        )

    async def _handle_status(self, ctx):
        payload = self.manager.public_payload()
        if not payload["ship_count"]:
            await ctx.send("No Bittleships game has been started. Assign an admiral with !admiral @user.")
            return
        if payload["mode"] == "classic":
            classic = payload["classic"]
            if payload["phase"] == "joining":
                await ctx.send(
                    f"🚢 Classic signup OPEN | Players: {len(classic['players'])} | "
                    f"Join with !ships join | Fighter: {'ON' if classic['fighter_enabled'] else 'OFF'}"
                )
                return
            leader = classic["scores"][0] if classic["scores"] else None
            leader_text = (
                f" | Leader: @{leader['name']} ({leader['points']} pts)"
                if leader else ""
            )
            sudden_death_text = " | SUDDEN DEATH: first fighter hit wins" if classic.get("sudden_death") else ""
            await ctx.send(
                f"🚢 Classic {payload['phase'].upper()} | Round: {classic['round']} | "
                f"Turn: @{classic['current_player'] or 'none'} | Ships left: "
                f"{payload['ships_remaining']}/5{leader_text}{sudden_death_text}"
            )
            return
        state = "ACTIVE" if payload["active"] else "ENDED"
        await ctx.send(
            f"🚢 Bittleships {state} | Admiral: @{payload['admiral'] or 'none'} | "
            f"Ships left: {payload['ships_remaining']}/{payload['ship_count']} | "
            f"Hits: {payload['hits']} | Misses: {payload['misses']}"
        )

    async def _handle_stop(self, ctx):
        if not (self._is_admiral(ctx.author) or self._is_mod_or_broadcaster(ctx.author)):
            await ctx.send("Only the admiral, a moderator, or the broadcaster can stop the game.")
            return
        was_classic = self.manager.state.get("mode") == "classic"
        self.manager.stop_game()
        restored = (
            self.manager.restore_suspended_game(
                "Classic stopped. Persistent giveaway board restored."
            )
            if was_classic else False
        )
        self._schedule_classic_turn_timeout()
        await self._broadcast()
        if restored:
            await ctx.send("Classic stopped. The persistent giveaway board is active again.")
        else:
            await ctx.send("Bittleships game stopped.")

    async def _handle_skip(self, ctx):
        if not self._is_mod_or_broadcaster(ctx.author):
            await ctx.send("Only moderators or the broadcaster can skip a Classic turn.")
            return
        try:
            skipped = self.manager.skip_classic_turn()
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await self._broadcast()
        current = self.manager.public_payload()["classic"]["current_player"]
        self._schedule_classic_turn_timeout()
        await ctx.send(f"⏭️ @{skipped}'s turn skipped. @{current} is up.")

    async def _handle_resume(self, ctx):
        if not self._is_mod_or_broadcaster(ctx.author):
            await ctx.send("Only moderators or the broadcaster can restore the giveaway board.")
            return
        if not self.manager.restore_suspended_game(
            "Persistent giveaway board restored by moderator."
        ):
            await ctx.send("There is no suspended giveaway board to restore.")
            return
        self._schedule_classic_turn_timeout()
        await self._broadcast()
        await ctx.send("Persistent giveaway board restored.")


def prepare(bot):
    if not bot.get_cog("BittleshipsCog"):
        bot.add_cog(BittleshipsCog(bot))
