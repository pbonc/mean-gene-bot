import os
import asyncio
import logging
from functools import wraps
from twitchio.ext import commands
from bot.overlay_server import broadcast_overlay_message
from bot.commands.base_command import mod_only
from bot.wheel_state import MAX_SLOTS_PER_ADD, WheelState, get_wheel_state, normalize_hex_color, WheelOperationError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
WHEEL_STATE_FILE = os.path.join(DATA_DIR, "wheel_state.json")

COLOR_PALETTE = [
    "#2dd4bf", "#38bdf8", "#6366f1", "#f472b6", "#fb7185", "#f59e0b",
    "#a3e635", "#34d399", "#22d3ee", "#818cf8", "#f97316", "#c084fc"
]

def wheel_errors(callback):
    @wraps(callback)
    async def handle(self, ctx):
        try:
            return await callback(self, ctx)
        except WheelOperationError as error:
            logging.getLogger("wheel").exception("Wheel operation failed")
            await ctx.send(f"Wheel operation failed; no change was committed. {error}")
    return handle

class WheelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("wheel")
        self.state = get_wheel_state(WHEEL_STATE_FILE)
        try:
            self.bot.loop.create_task(self._broadcast_state_on_start())
        except Exception:
            pass

    async def _broadcast_state_on_start(self):
        await asyncio.sleep(1)
        await broadcast_overlay_message(self.state.get_state_payload())

    @commands.command(name="wheeljoin")
    @wheel_errors
    async def wheel_join(self, ctx):
        parts = ctx.message.content.split()
        user = ctx.author.name.lower()
        count = 1
        color = None
        if len(parts) > 1:
            if parts[1].isdigit():
                count = int(parts[1])
                if len(parts) > 2:
                    color = normalize_hex_color(parts[2])
            else:
                color = normalize_hex_color(parts[1])
                if len(parts) > 2 and parts[2].isdigit():
                    count = int(parts[2])

        if color is None and len(parts) > 1 and not parts[1].isdigit():
            await ctx.send("⚠️ Invalid color. Use a hex code like #ff33aa.")
            return

        if count < 1:
            await ctx.send("⚠️ Count must be at least 1.")
            return

        if count > MAX_SLOTS_PER_ADD:
            await ctx.send(f"⚠️ Max per add is {MAX_SLOTS_PER_ADD} slots.")
            return

        if count != 1:
            await ctx.send("⚠️ Use the multiplier to add repeats. One entry per person.")
            return

        if not color:
            color = self.state.colors.get(user)
        if not color:
            color = COLOR_PALETTE[len(self.state.colors) % len(COLOR_PALETTE)]
        if not self.state.join(user, color=color):
            await ctx.send("Wheel entry rejected: the wheel is locked or the user already joined.")
            return
        count = self.state.slots[user]
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send(f"🎡 @{user} joined the wheel ({count} slot{'s' if count != 1 else ''}).")

    @commands.command(name="wheeladd")
    @mod_only
    @wheel_errors
    async def wheel_add(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 3:
            await ctx.send("⚠️ Usage: !wheeladd <user> <count> [#hex]")
            return
        user = parts[1].lstrip('@').lower()
        if not parts[2].isdigit():
            await ctx.send("⚠️ Count must be a number.")
            return
        count = int(parts[2])
        color = None
        if len(parts) > 3:
            color = normalize_hex_color(parts[3])
            if color is None:
                await ctx.send("⚠️ Invalid color. Use a hex code like #ff33aa.")
                return
        if count < 1:
            await ctx.send("⚠️ Count must be at least 1.")
            return
        if count > MAX_SLOTS_PER_ADD:
            await ctx.send(f"⚠️ Max per add is {MAX_SLOTS_PER_ADD} slots.")
            return
        if not color:
            color = self.state.colors.get(user)
        if not color:
            color = COLOR_PALETTE[len(self.state.colors) % len(COLOR_PALETTE)]
        if not self.state.add_slots(user, count, allow_multi=True, color=color, manual=True):
            await ctx.send("Wheel entry rejected: the wheel is locked or the user already joined.")
            return
        count = self.state.slots[user]
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send(f"✅ Added {count} slot{'s' if count != 1 else ''} for @{user}.")

    @commands.command(name="wheelremove")
    @mod_only
    @wheel_errors
    async def wheel_remove(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !wheelremove <user>")
            return
        user = parts[1].lstrip('@').lower()
        if self.state.remove_user(user):
            await broadcast_overlay_message(self.state.get_state_payload())
            await ctx.send(f"✅ Removed @{user} from the wheel.")
        else:
            await ctx.send("⚠️ That user is not on the wheel.")

    @commands.command(name="wheelspin")
    @mod_only
    @wheel_errors
    async def wheel_spin(self, ctx):
        parts = ctx.message.content.split()
        duration = 8
        if len(parts) > 1:
            if not parts[1].isdigit():
                await ctx.send("⚠️ Usage: !wheelspin [seconds]")
                return
            duration = int(parts[1])
        duration = max(5, min(200, duration))

        winner, winner_index, slots_list = self.state.spin()
        if not slots_list:
            await ctx.send("⚠️ The wheel is empty. Use !wheeljoin to enter.")
            return

        slots_payload = [
            {"name": name, "color": self.state.colors.get(name)} for name in slots_list
        ]

        await broadcast_overlay_message({
            "type": "wheel_spin",
            "slots": slots_payload,
            "winner": winner,
            "winner_index": winner_index,
            "duration_ms": duration * 1000,
        })
        await broadcast_overlay_message(self.state.get_state_payload())
        score = self.state.scores.get(winner, 0)
        removal_note = " Removed from wheel." if (self.state.remove_on_win or self.state.last_man_standing) else ""
        lms_winner = None
        if self.state.last_man_standing:
            if len(self.state.slots) == 1:
                lms_winner = next(iter(self.state.slots.keys()))
            elif len(self.state.slots) == 0 and winner:
                lms_winner = winner
        await asyncio.sleep(duration + 0.3)
        if self.state.last_man_standing:
            await ctx.send(f"🪓 Eliminated: @{winner} (+1). Total score: {score}.{removal_note}")
        else:
            await ctx.send(f"🎉 Winner: @{winner} (+1). Total score: {score}.{removal_note}")
        if lms_winner:
            await ctx.send(f"🏆 Last man standing: @{lms_winner}.")

    @commands.command(name="wheelscores")
    @wheel_errors
    async def wheel_scores(self, ctx):
        self.state.load()
        if not self.state.scores:
            await ctx.send("No wheel scores yet.")
            return
        top_scores = sorted(self.state.scores.items(), key=lambda x: (-x[1], x[0]))[:5]
        score_text = ", ".join([f"@{name}: {score}" for name, score in top_scores])
        await ctx.send(f"🏆 Wheel scores: {score_text}")

    @commands.command(name="wheelcolor")
    @wheel_errors
    async def wheel_color(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !wheelcolor #hex")
            return
        color = normalize_hex_color(parts[1])
        if color is None:
            await ctx.send("⚠️ Invalid color. Use a hex code like #ff33aa.")
            return
        user = ctx.author.name.lower()
        if not self.state.set_color(user, color):
            await ctx.send("You must be on the wheel to set a color.")
            return
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send(f"✅ Color updated for @{user}.")

    @commands.command(name="wheelmultiplier")
    @mod_only
    @wheel_errors
    async def wheel_multiplier(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send("Usage: !wheelmultiplier <count>")
            return
        updated = self.state.set_multiplier(parts[1])
        multiplier = self.state.multiplier
        await broadcast_overlay_message(self.state.get_state_payload())
        if updated:
            await ctx.send(f"✅ Set all entries to {multiplier} slots each.")
        else:
            await ctx.send(f"✅ Multiplier set to {multiplier} (slots per participant, including new joins).")

    @commands.command(name="wheelremoveonwin")
    @mod_only
    @wheel_errors
    async def wheel_remove_on_win(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !wheelremoveonwin <on|off>")
            return
        value = parts[1].lower()
        if value in ("on", "true", "yes", "1"):
            self.state.set_remove_on_win(True)
        elif value in ("off", "false", "no", "0"):
            self.state.set_remove_on_win(False)
        else:
            await ctx.send("⚠️ Usage: !wheelremoveonwin <on|off>")
            return
        await broadcast_overlay_message(self.state.get_state_payload())
        status = "on" if self.state.remove_on_win else "off"
        await ctx.send(f"✅ Remove-on-win is now {status}.")

    @commands.command(name="wheellock")
    @mod_only
    @wheel_errors
    async def wheel_lock(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !wheellock <on|off>")
            return
        value = parts[1].lower()
        if value in ("on", "true", "yes", "1"):
            self.state.set_wheel_locked(True)
        elif value in ("off", "false", "no", "0"):
            self.state.set_wheel_locked(False)
        else:
            await ctx.send("⚠️ Usage: !wheellock <on|off>")
            return
        await broadcast_overlay_message(self.state.get_state_payload())
        status = "on" if self.state.wheel_locked else "off"
        await ctx.send(f"✅ Wheel lock is now {status}.")

    @commands.command(name="wheellastman")
    @mod_only
    @wheel_errors
    async def wheel_last_man(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !wheellastman <on|off>")
            return
        value = parts[1].lower()
        if value in ("on", "true", "yes", "1"):
            self.state.set_last_man_standing(True)
        elif value in ("off", "false", "no", "0"):
            self.state.set_last_man_standing(False)
        else:
            await ctx.send("⚠️ Usage: !wheellastman <on|off>")
            return
        await broadcast_overlay_message(self.state.get_state_payload())
        status = "on" if self.state.last_man_standing else "off"
        await ctx.send(f"✅ Last man standing is now {status}.")

    @commands.command(name="wheelreset")
    @mod_only
    @wheel_errors
    async def wheel_reset(self, ctx):
        self.state.reset()
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send("✅ Wheel entries and scores reset.")


def prepare(bot):
    if not bot.get_cog("WheelCog"):
        bot.add_cog(WheelCog(bot))
