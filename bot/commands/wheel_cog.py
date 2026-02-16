import json
import os
import random
import asyncio
import logging
import re
from twitchio.ext import commands
from bot.overlay_server import broadcast_overlay_message
from bot.commands.base_command import mod_only

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
WHEEL_STATE_FILE = os.path.join(DATA_DIR, "wheel_state.json")

MAX_SLOTS_PER_ADD = 500
COLOR_PALETTE = [
    "#2dd4bf", "#38bdf8", "#6366f1", "#f472b6", "#fb7185", "#f59e0b",
    "#a3e635", "#34d399", "#22d3ee", "#818cf8", "#f97316", "#c084fc"
]

def normalize_hex_color(value: str):
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.startswith("#"):
        value = f"#{value}"
    if not re.match(r"^#[0-9a-fA-F]{6}$", value):
        return None
    return value.lower()

class WheelState:
    def __init__(self, state_file=WHEEL_STATE_FILE):
        self.state_file = state_file
        self.slots = {}
        self.scores = {}
        self.last_winner = None
        self.remove_on_win = False
        self.wheel_locked = False
        self.last_man_standing = False
        self.order = []
        self.colors = {}
        self.multiplier = 1
        self.manual_users = set()
        self.load()

    def load(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.slots = {k: int(v) for k, v in data.get("slots", {}).items() if int(v) > 0}
            self.scores = {k: int(v) for k, v in data.get("scores", {}).items() if int(v) >= 0}
            self.last_winner = data.get("last_winner", None)
            self.remove_on_win = bool(data.get("remove_on_win", False))
            self.wheel_locked = bool(data.get("wheel_locked", False))
            self.last_man_standing = bool(data.get("last_man_standing", False))
            self.order = [u for u in data.get("order", []) if u in self.slots]
            for u in sorted(self.slots.keys()):
                if u not in self.order:
                    self.order.append(u)
            self.colors = {k: v for k, v in data.get("colors", {}).items() if isinstance(v, str)}
            self.multiplier = max(1, int(data.get("multiplier", 1)))
            self.manual_users = {
                u for u in data.get("manual_users", []) if isinstance(u, str) and u in self.slots
            }
        else:
            self.save()

    def save(self):
        data = {
            "slots": self.slots,
            "scores": self.scores,
            "last_winner": self.last_winner,
            "remove_on_win": self.remove_on_win,
            "wheel_locked": self.wheel_locked,
            "last_man_standing": self.last_man_standing,
            "order": self.order,
            "colors": self.colors,
            "multiplier": self.multiplier,
            "manual_users": sorted(self.manual_users),
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_slots(self, user, count=1, allow_multi=False, color=None, manual=False):
        user = user.lower()
        count = max(1, int(count))
        if user in self.slots and not allow_multi:
            return False
        if not allow_multi:
            count = 1
        self.slots[user] = self.slots.get(user, 0) + count
        if user not in self.order:
            self.order.append(user)
        if color:
            self.colors[user] = color
        if manual:
            self.manual_users.add(user)
        self.save()
        return True

    def remove_user(self, user):
        user = user.lower()
        if user in self.slots:
            del self.slots[user]
            if user in self.order:
                self.order = [u for u in self.order if u != user]
            if user in self.manual_users:
                self.manual_users.discard(user)
            self.save()
            return True
        return False

    def set_multiplier(self, multiplier):
        multiplier = max(1, int(multiplier))
        self.multiplier = multiplier
        if not self.slots:
            self.save()
            return False
        updated = False
        for user in list(self.slots.keys()):
            if user in self.manual_users:
                continue
            if self.slots.get(user) != multiplier:
                self.slots[user] = multiplier
                updated = True
        self.save()
        return updated

    def set_remove_on_win(self, enabled: bool):
        self.remove_on_win = bool(enabled)
        self.save()

    def set_wheel_locked(self, enabled: bool):
        self.wheel_locked = bool(enabled)
        self.save()

    def set_last_man_standing(self, enabled: bool):
        self.last_man_standing = bool(enabled)
        self.save()

    def reset(self):
        self.slots = {}
        self.scores = {}
        self.last_winner = None
        self.wheel_locked = False
        self.last_man_standing = False
        self.order = []
        self.colors = {}
        self.multiplier = 1
        self.manual_users = set()
        self.save()

    def build_slots_list(self):
        ordered_users = [u for u in self.order if u in self.slots]
        for u in sorted(self.slots.keys()):
            if u not in ordered_users:
                ordered_users.append(u)
        if not ordered_users:
            return []
        max_count = max(max(1, int(self.slots[u])) for u in ordered_users)
        slots_list = []
        for i in range(max_count):
            for u in ordered_users:
                if i < int(self.slots[u]):
                    slots_list.append(u)
        return slots_list

    def spin(self):
        slots_list = self.build_slots_list()
        if not slots_list:
            return None, None, None
        winner_index = random.randrange(len(slots_list))
        winner = slots_list[winner_index]
        self.last_winner = winner
        self.scores[winner] = self.scores.get(winner, 0) + 1
        if winner in self.slots:
            if self.last_man_standing:
                remaining = int(self.slots.get(winner, 0)) - 1
                if remaining > 0:
                    self.slots[winner] = remaining
                else:
                    del self.slots[winner]
                    if winner in self.order:
                        self.order = [u for u in self.order if u != winner]
                    if winner in self.manual_users:
                        self.manual_users.discard(winner)
            elif self.remove_on_win:
                remaining = int(self.slots.get(winner, 0)) - 1
                if remaining > 0:
                    self.slots[winner] = remaining
                else:
                    del self.slots[winner]
                    if winner in self.order:
                        self.order = [u for u in self.order if u != winner]
                    if winner in self.manual_users:
                        self.manual_users.discard(winner)
        self.save()
        return winner, winner_index, slots_list

    def get_state_payload(self):
        slots_payload = [
            {"name": name, "count": int(count), "color": self.colors.get(name)}
            for name, count in [(u, self.slots[u]) for u in self.order if u in self.slots]
        ]
        scores_payload = [
            {"name": name, "score": int(score)}
            for name, score in sorted(self.scores.items(), key=lambda x: (-x[1], x[0]))
        ]
        total_slots = sum(int(c) for c in self.slots.values())
        return {
            "type": "wheel_state",
            "slots": slots_payload,
            "scores": scores_payload,
            "total_slots": total_slots,
            "last_winner": self.last_winner,
            "remove_on_win": self.remove_on_win,
            "wheel_locked": self.wheel_locked,
            "last_man_standing": self.last_man_standing,
        }

class WheelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("wheel")
        self.state = WheelState()
        try:
            self.bot.loop.create_task(self._broadcast_state_on_start())
        except Exception:
            pass

    async def _broadcast_state_on_start(self):
        await asyncio.sleep(1)
        await broadcast_overlay_message(self.state.get_state_payload())

    @commands.command(name="wheeljoin")
    async def wheel_join(self, ctx):
        self.state.load()
        if self.state.wheel_locked:
            await ctx.send("🔒 The wheel is locked. No new entries right now.")
            return
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

        if user in self.state.slots:
            await ctx.send("⚠️ You're already on the wheel.")
            return
        if count != 1:
            await ctx.send("⚠️ Use the multiplier to add repeats. One entry per person.")
            return

        if not color:
            color = self.state.colors.get(user)
        if not color:
            color = COLOR_PALETTE[len(self.state.colors) % len(COLOR_PALETTE)]
        count = max(1, int(self.state.multiplier))
        self.state.add_slots(user, count, allow_multi=False, color=color, manual=False)
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send(f"🎡 @{user} joined the wheel ({count} slot{'s' if count != 1 else ''}).")

    @commands.command(name="wheeladd")
    @mod_only
    async def wheel_add(self, ctx):
        self.state.load()
        if self.state.wheel_locked:
            await ctx.send("🔒 The wheel is locked. No new entries right now.")
            return
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
        if user in self.state.slots:
            await ctx.send("⚠️ That user is already on the wheel.")
            return
        if not color:
            color = self.state.colors.get(user)
        if not color:
            color = COLOR_PALETTE[len(self.state.colors) % len(COLOR_PALETTE)]
        self.state.add_slots(user, count, allow_multi=True, color=color, manual=True)
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send(f"✅ Added {count} slot{'s' if count != 1 else ''} for @{user}.")

    @commands.command(name="wheelremove")
    @mod_only
    async def wheel_remove(self, ctx):
        self.state.load()
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
    async def wheel_spin(self, ctx):
        self.state.load()
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
    async def wheel_scores(self, ctx):
        self.state.load()
        if not self.state.scores:
            await ctx.send("No wheel scores yet.")
            return
        top_scores = sorted(self.state.scores.items(), key=lambda x: (-x[1], x[0]))[:5]
        score_text = ", ".join([f"@{name}: {score}" for name, score in top_scores])
        await ctx.send(f"🏆 Wheel scores: {score_text}")

    @commands.command(name="wheelcolor")
    async def wheel_color(self, ctx):
        self.state.load()
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send("⚠️ Usage: !wheelcolor #hex")
            return
        color = normalize_hex_color(parts[1])
        if color is None:
            await ctx.send("⚠️ Invalid color. Use a hex code like #ff33aa.")
            return
        user = ctx.author.name.lower()
        if user not in self.state.slots:
            await ctx.send("⚠️ You must be on the wheel to set a color.")
            return
        self.state.colors[user] = color
        self.state.save()
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send(f"✅ Color updated for @{user}.")

    @commands.command(name="wheelmultiplier")
    @mod_only
    async def wheel_multiplier(self, ctx):
        self.state.load()
        parts = ctx.message.content.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await ctx.send("⚠️ Usage: !wheelmultiplier <count>")
            return
        multiplier = int(parts[1])
        if multiplier < 1 or multiplier > MAX_SLOTS_PER_ADD:
            await ctx.send(f"⚠️ Multiplier must be between 1 and {MAX_SLOTS_PER_ADD}.")
            return
        updated = self.state.set_multiplier(multiplier)
        await broadcast_overlay_message(self.state.get_state_payload())
        if updated:
            await ctx.send(f"✅ Set all non-manual entries to {multiplier} slots each.")
        else:
            await ctx.send(f"✅ Multiplier set to {multiplier} for future joins.")

    @commands.command(name="wheelremoveonwin")
    @mod_only
    async def wheel_remove_on_win(self, ctx):
        self.state.load()
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
    async def wheel_lock(self, ctx):
        self.state.load()
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
    async def wheel_last_man(self, ctx):
        self.state.load()
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
    async def wheel_reset(self, ctx):
        self.state.load()
        self.state.reset()
        await broadcast_overlay_message(self.state.get_state_payload())
        await ctx.send("✅ Wheel entries and scores reset.")


def prepare(bot):
    if not bot.get_cog("WheelCog"):
        bot.add_cog(WheelCog(bot))
