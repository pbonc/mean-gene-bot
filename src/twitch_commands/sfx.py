import os
import json
import random
import asyncio
from twitchio.ext import commands

RAFFLE_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "raffle_state.json")

def ensure_json():
    os.makedirs(os.path.dirname(RAFFLE_DATA_FILE), exist_ok=True)
    if not os.path.exists(RAFFLE_DATA_FILE):
        with open(RAFFLE_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "raffle_state": "closed",
                "entries_per_chat": 1,
                "awarded_entries": {},
                "entries": {},
                "picks": {},
                "pending_nuclear": {
                    "closeraffle": [],
                    "drawraffle": [],
                    "clearsheet": []
                },
                "last_draw": {
                    "number": None,
                    "winner": None
                }
            }, f, indent=2)

class RaffleManager:
    def __init__(self):
        ensure_json()
        self.load()

    def load(self):
        with open(RAFFLE_DATA_FILE, "r", encoding="utf-8") as f:
            self.state = json.load(f)

    def save(self):
        with open(RAFFLE_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    # State
    def open_raffle(self, entries_per_chat: int):
        self.state["raffle_state"] = "open"
        self.state["entries_per_chat"] = entries_per_chat
        self.state["awarded_entries"] = {}
        self.state["picks"] = {}
        self.state["pending_nuclear"] = {
            "closeraffle": [],
            "drawraffle": [],
            "clearsheet": []
        }
        self.save()

    def close_raffle(self):
        self.state["raffle_state"] = "closed"
        self.save()

    def is_open(self):
        return self.state.get("raffle_state") == "open"

    def is_closed(self):
        return self.state.get("raffle_state") == "closed"

    # Entries
    def award_entry_on_chat(self, username: str):
        u = username.lower()
        if not self.is_open():
            return 0
        if self.state["awarded_entries"].get(u):
            return 0
        n = int(self.state.get("entries_per_chat", 1))
        self.state["entries"][u] = self.state["entries"].get(u, 0) + n
        self.state["awarded_entries"][u] = True
        self.save()
        return n

    def create_entries(self, username: str, amount: int):
        u = username.lower()
        self.state["entries"][u] = self.state["entries"].get(u, 0) + int(amount)
        self.save()

    def trade_entries(self, from_user: str, to_user: str, amount: int):
        fromu = from_user.lower()
        tou = to_user.lower()
        if fromu == tou:
            return False, "⛔ Cannot trade entries to yourself."
        if self.state["entries"].get(fromu, 0) < amount or amount <= 0:
            return False, f"⛔ You only have {self.state['entries'].get(fromu, 0)} entries."
        self.state["entries"][fromu] -= amount
        self.state["entries"][tou] = self.state["entries"].get(tou, 0) + amount
        self.save()
        return True, f"✅ Transferred {amount} entries to {tou}."

    def get_entries(self, username: str) -> int:
        return int(self.state["entries"].get(username.lower(), 0))

    # Picks
    def pick_numbers(self, username: str, numbers):
        u = username.lower()
        available = self.get_entries(u)
        picks_to_add = []
        for number in numbers:
            num = number.zfill(3)
            if not num.isdigit() or len(num) != 3:
                return False, f"⛔ Invalid number: {num}. Must be 3 digits."
            if num in self.state["picks"]:
                return False, f"⛔ Number {num} is already picked."
            picks_to_add.append(num)
        if len(picks_to_add) > available:
            return False, f"⛔ You only have {available} entries to spend."
        for num in picks_to_add:
            self.state["picks"][num] = u
        self.state["entries"][u] -= len(picks_to_add)
        self.save()
        return True, f"✅ {u} picked: {', '.join(picks_to_add)}"

    def random_pick_numbers(self, username: str, count: int):
        u = username.lower()
        available = self.get_entries(u)
        if count > available:
            return False, f"⛔ You only have {available} entries to spend.", []
        all_numbers = {str(i).zfill(3) for i in range(1000)}
        already_picked = set(self.state["picks"].keys())
        possible = list(all_numbers - already_picked)
        if len(possible) < count:
            return False, "⛔ Not enough numbers left to pick.", []
        picks = random.sample(possible, count)
        for num in picks:
            self.state["picks"][num] = u
        self.state["entries"][u] -= count
        self.save()
        return True, f"✅ {u} picked: {', '.join(picks)}", picks

    def get_user_picks(self, username: str):
        u = username.lower()
        return sorted([num for num, owner in self.state["picks"].items() if owner == u])

    # Nuclear
    def add_nuclear_confirmation(self, command, mod):
        m = mod.lower()
        pending = self.state["pending_nuclear"].setdefault(command, [])
        if m not in pending:
            pending.append(m)
            self.save()
        return len(pending)

    def clear_nuclear_confirmations(self, command):
        self.state["pending_nuclear"][command] = []
        self.save()

    # Sheet/draw
    def clear_sheet(self):
        self.state["picks"] = {}
        self.save()

    def draw_winner(self):
        num = str(random.randint(0, 999)).zfill(3)
        winner = self.state["picks"].get(num)
        self.state["last_draw"]["number"] = num
        self.state["last_draw"]["winner"] = winner
        self.save()
        return num, winner, [num[0], num[1], num[2]]

# The actual Twitch command handler
raffle = RaffleManager()

class RaffleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Award entries on first chat after open
    async def event_message(self, message):
        if message.echo:
            return
        user = message.author.name.lower()
        awarded = raffle.award_entry_on_chat(user)
        if awarded > 0:
            await message.channel.send(f"🎟 {user}, you received {awarded} raffle entries!")

    @commands.command(name="openraffle")
    async def openraffle(self, ctx):
        if not ctx.author.is_mod:
            return
        parts = ctx.message.content.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await ctx.send("⚠️ Usage: !openraffle <entry_count>")
            return
        entry_count = int(parts[1])
        raffle.open_raffle(entry_count)
        await ctx.send(f"🎉 Raffle opened! Everyone who chats gets {entry_count} entries on first message.")

    @commands.command(name="entries")
    async def entries_cmd(self, ctx):
        parts = ctx.message.content.strip().split()
        user = ctx.author.name.lower()
        if len(parts) == 1:
            await ctx.send(f"🎟 @{user}, you have {raffle.get_entries(user)} entries.")
            return
        elif parts[1] == "create":
            if not ctx.author.is_mod:
                return
            if len(parts) != 4 or not parts[2].isdigit() or not parts[3].startswith("@"):
                await ctx.send("⚠️ Usage: !entries create <X> @user")
                return
            amount = int(parts[2])
            target = parts[3].lstrip("@").lower()
            raffle.create_entries(target, amount)
            await ctx.send(f"🎁 {target} was granted {amount} entries.")
        elif parts[1] == "trade":
            if len(parts) != 4 or not parts[2].isdigit() or not parts[3].startswith("@"):
                await ctx.send("⚠️ Usage: !entries trade <X> @user")
                return
            amount = int(parts[2])
            target = parts[3].lstrip("@").lower()
            ok, msg = raffle.trade_entries(user, target, amount)
            await ctx.send(msg)
        else:
            await ctx.send("⚠️ Usage: !entries, !entries create X @user, or !entries trade X @user")

    @commands.command(name="myentries")
    async def myentries(self, ctx):
        user = ctx.author.name.lower()
        await ctx.send(f"🎟 @{user}, you have {raffle.get_entries(user)} entries.")

    @commands.command(name="mypicks")
    async def mypicks(self, ctx):
        user = ctx.author.name.lower()
        picks = raffle.get_user_picks(user)
        if picks:
            await ctx.send(f"🔢 @{user}, your picked numbers: {', '.join(picks)}")
        else:
            await ctx.send(f"🧐 @{user}, you haven't picked any numbers yet.")

    @commands.command(name="enterraffle")
    async def enterraffle(self, ctx):
        if not raffle.is_open():
            await ctx.send("🔒 The raffle is closed. No new picked numbers allowed.")
            return
        args = ctx.message.content.strip().split(maxsplit=1)
        user = ctx.author.name.lower()
        if len(args) < 2:
            await ctx.send("⚠️ Usage: !enterraffle <number(s)|random [N]>")
            return
        subcommand = args[1].lower()
        # random
        if subcommand.startswith("random"):
            parts = subcommand.split()
            count = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
            ok, msg, picks = raffle.random_pick_numbers(user, count)
            await ctx.send(msg)
            return
        # specific numbers
        requested_raw = [n.strip() for n in subcommand.split(",")]
        ok, msg = raffle.pick_numbers(user, requested_raw)
        await ctx.send(msg)

    @commands.command(name="closeraffle")
    async def closeraffle(self, ctx):
        if not ctx.author.is_mod:
            return
        parts = ctx.message.content.strip().split()
        user = ctx.author.name.lower()
        # Timer: default 2 min, allow 1-5 min
        minutes = 2
        if len(parts) > 1 and parts[1].isdigit():
            minutes = min(max(int(parts[1]), 1), 5)
        # nuclear confirmation
        conf = raffle.add_nuclear_confirmation("closeraffle", user)
        if conf < 2:
            await ctx.send(f"🟠 {user} confirmed close. One more mod confirmation needed...")
            return
        raffle.clear_nuclear_confirmations("closeraffle")
        await ctx.send(f"⏳ Raffle will close in {minutes} minute(s)! Submit your picked numbers soon!")

        total_seconds = minutes * 60
        warn_schedule = [
            (120, "⏰ 2 minutes left to enter the raffle!"),
            (60, "⏰ 1 minute left to enter the raffle!"),
            (30, "⏰ 30 seconds left to enter the raffle!"),
        ]
        now = 0
        # Only send warnings that are within the chosen time window
        for warn_sec, warn_msg in warn_schedule:
            if total_seconds > warn_sec:
                await asyncio.sleep(total_seconds - warn_sec - now)
                await ctx.send(warn_msg)
                now += total_seconds - warn_sec - now
        await asyncio.sleep(total_seconds - now)
        raffle.close_raffle()
        await ctx.send("🔒 Raffle is now closed! No new picks will be accepted.")

    @commands.command(name="drawraffle")
    async def drawraffle(self, ctx):
        if not ctx.author.is_mod:
            return
        if raffle.is_open():
            await ctx.send("⚠️ You must close the raffle before drawing a winner! Use !closeraffle")
            return
        user = ctx.author.name.lower()
        conf = raffle.add_nuclear_confirmation("drawraffle", user)
        if conf < 2:
            await ctx.send(f"🟡 {user} confirmed draw. One more mod confirmation needed...")
            return
        raffle.clear_nuclear_confirmations("drawraffle")
        num, winner, digits = raffle.draw_winner()
        await ctx.send(f"🎰 The first number is... {digits[0]}")
        await asyncio.sleep(5)
        await ctx.send(f"🎰 The second number is... {digits[1]}")
        await asyncio.sleep(5)
        await ctx.send(f"🎰 The last number is... {digits[2]}")
        await asyncio.sleep(5)
        await ctx.send(f"🌙 Tonight's winning number is {num}.")
        if winner:
            await ctx.send(f"🎉 The winner is @{winner} with picked number {num}!")
        else:
            await ctx.send(f"😢 No one picked {num}. The prize rolls over!")

    @commands.command(name="testdraw")
    async def testdraw(self, ctx):
        if not ctx.author.is_mod:
            return
        # Simulate a draw without altering state
        num = str(random.randint(0, 999)).zfill(3)
        winner = raffle.state["picks"].get(num)
        result = f"Test Draw : {num} - "
        if winner:
            result += f"WINNER: @{winner} picked {num}!"
        else:
            result += "No winner."
        await ctx.send(result)

    @commands.command(name="clearsheet")
    async def clearsheet(self, ctx):
        if not ctx.author.is_mod:
            return
        user = ctx.author.name.lower()
        conf = raffle.add_nuclear_confirmation("clearsheet", user)
        if conf < 2:
            await ctx.send(f"🟠 {user} confirmed clear. One more mod confirmation needed...")
            return
        raffle.clear_nuclear_confirmations("clearsheet")
        raffle.clear_sheet()
        await ctx.send("🧹 All picked numbers cleared. Entries remain safe.")

def prepare(bot):
    if not bot.get_cog("RaffleCog"):
        bot.add_cog(RaffleCog(bot))