import os
import json
import random
import logging
import asyncio
from twitchio.ext import commands

logger = logging.getLogger("raffle")

BOT_USERNAME = "iamdar"  # Set to your bot's username (case-insensitive)

# ---- RaffleState definition ----

class RaffleState:
    STATE_FILE = "raffle_state.json"

    def __init__(self):
        self.state = {
            "is_open": False,
            "entries": {},
            "picks": {},
            "entries_per_chat": 1,
            "chat_awarded": [],
            "nuclear": {},
        }
        self.load()

    def load(self):
        if os.path.exists(self.STATE_FILE):
            with open(self.STATE_FILE, "r", encoding="utf-8") as f:
                try:
                    self.state = json.load(f)
                    # chat_awarded and nuclear need proper types
                    self.state["chat_awarded"] = set(self.state.get("chat_awarded", []))
                    self.state["nuclear"] = dict(self.state.get("nuclear", {}))
                except Exception as e:
                    logger.error(f"Failed to load raffle state: {e}")

    def save(self):
        try:
            save_state = dict(self.state)
            save_state["chat_awarded"] = list(save_state.get("chat_awarded", set()))
            with open(self.STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(save_state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save raffle state: {e}")

    def is_open(self):
        return self.state.get("is_open", False)

    def open_raffle(self, entries_per_chat):
        self.state["is_open"] = True
        self.state["entries_per_chat"] = entries_per_chat
        # DO NOT reset picks, chat_awarded, or entries here!
        self.save()

    def close_raffle(self):
        self.state["is_open"] = False
        self.save()

    def add_entries(self, user, count):
        entries = self.state["entries"].setdefault(user, 0)
        self.state["entries"][user] = entries + count
        self.save()

    def remove_entries(self, user, count):
        entries = self.state["entries"].get(user, 0)
        self.state["entries"][user] = max(0, entries - count)
        self.save()

    def get_entries(self, user):
        return self.state["entries"].get(user, 0)

    def pick_numbers(self, user, numbers):
        if not self.is_open():
            return False, "Raffle is not open."
        entries = self.get_entries(user)
        picks = self.state["picks"].setdefault(user, set())
        if len(picks) + len(numbers) > entries:
            return False, "Not enough entries left."
        taken = set()
        for n in numbers:
            for p_user, p_picks in self.state["picks"].items():
                if n in p_picks:
                    taken.add(n)
        if taken:
            return False, f"Numbers already taken: {', '.join(taken)}"
        picks.update(numbers)
        self.save()
        return True, numbers

    def pick_series(self, user, start, count, direction):
        if not self.is_open():
            return False, []
        series = []
        if direction == "+":
            series = [str(start + i).zfill(3) for i in range(count)]
        else:
            series = [str(start - i).zfill(3) for i in range(count)]
        ok, msg = self.pick_numbers(user, series)
        return ok, series if ok else []

    def pick_random_numbers(self, user, count):
        if not self.is_open():
            return False, []
        available = [str(i).zfill(3) for i in range(0, 1000)]
        for picks in self.state["picks"].values():
            for n in picks:
                if n in available:
                    available.remove(n)
        entries = self.get_entries(user)
        to_pick = min(count, entries - len(self.state["picks"].get(user, set())))
        if to_pick <= 0 or len(available) < to_pick:
            return False, []
        result = random.sample(available, to_pick)
        ok, msg = self.pick_numbers(user, result)
        return ok, result if ok else []

    def get_user_picks(self, user):
        return list(self.state["picks"].get(user, set()))

    def clear_picks(self):
        self.state["picks"] = {}
        self.save()

    def has_chat_award(self, user):
        return user in self.state["chat_awarded"]

    def award_chat(self, user):
        self.state["chat_awarded"].add(user)
        self.save()

    def draw(self):
        all_picks = {}
        for user, picks in self.state["picks"].items():
            for n in picks:
                all_picks[n] = user
        if not all_picks:
            return ("000", "000", None)
        number = random.choice(list(all_picks.keys()))
        digits = [number[0], number[1], number[2]]
        winner = all_picks[number]
        return digits, number, winner

    def test_draw(self):
        # Returns a random number and winner, or "no user"
        digits, number, winner = self.draw()
        return number, winner

    def nuclear_attempt(self, op, user):
        nuke = self.state["nuclear"].setdefault(op, set())
        nuke.add(user)
        if len(nuke) >= 2:
            return True
        self.save()
        return False

    def clear_nuclear(self, op):
        if op in self.state["nuclear"]:
            self.state["nuclear"].pop(op)
            self.save()

# ---- RaffleCog definition ----

class RaffleCog(commands.Cog):
    def __init__(self, bot, raffle_state, sfx_registry=None):
        self.bot = bot
        self.raffle_state = raffle_state
        self.sfx_registry = sfx_registry
        print(f"[RaffleCog __init__] sfx_registry: {self.sfx_registry}")
        if self.sfx_registry:
            file_count = len(getattr(self.sfx_registry, "file_commands", {}))
            folder_count = len(getattr(self.sfx_registry, "folder_commands", {}))
            print(f"[RaffleCog __init__] Loaded {file_count} file commands, {folder_count} folder commands")
        else:
            print("[RaffleCog __init__] No sfx_registry provided!")

    @commands.Cog.event()
    async def event_ready(self):
        logger.info(f"Logged in as | {self.bot.nick}")
        for channel in getattr(self.bot, 'initial_channels', []):
            logger.info(f"Joined channel | {channel}")

    @commands.Cog.event()
    async def event_message(self, message):
        # Only skip complimentary numbers for the bot user
        if message.echo:
            return
        if not hasattr(message.author, "name"):
            return
        # Award complimentary numbers to everyone except the bot user
        if (
            self.raffle_state.is_open() and
            not self.raffle_state.has_chat_award(message.author.name) and
            message.author.name.lower() != BOT_USERNAME.lower()
        ):
            self.raffle_state.add_entries(message.author.name, self.raffle_state.state["entries_per_chat"])
            self.raffle_state.award_chat(message.author.name)
            count = self.raffle_state.state["entries_per_chat"]
            await message.channel.send(f"@{message.author.name} – Here are {count} complimentary number{'s' if count > 1 else ''}.")

    @commands.command(name="openraffle")
    async def openraffle(self, ctx):
        parts = ctx.message.content.split()
        is_mod = getattr(ctx.author, "is_mod", False) or getattr(ctx.author, "is_broadcaster", False)
        if not is_mod:
            await ctx.send("Only mods can open the raffle.")
            return
        if len(parts) < 2 or not parts[1].isdigit():
            await ctx.send("Usage: !openraffle X (X = 1-10)")
            return
        x = int(parts[1])
        if not (1 <= x <= 10):
            await ctx.send("Entries per chat must be between 1 and 10.")
            return
        self.raffle_state.open_raffle(x)
        await ctx.send(f"Raffle is now open! Anyone who chats gets {x} free number{'s' if x > 1 else ''}!")

    @commands.command(name="giveentries")
    async def giveentries(self, ctx):
        parts = ctx.message.content.split()
        is_mod = getattr(ctx.author, "is_mod", False) or getattr(ctx.author, "is_broadcaster", False)
        if not is_mod:
            await ctx.send("Only mods can give entries.")
            return
        if len(parts) < 3 or not parts[2].isdigit():
            await ctx.send("Usage: !giveentries @user X")
            return
        user = parts[1].lstrip('@')
        amount = int(parts[2])
        if not (1 <= amount <= 10):
            await ctx.send("Can only give 1-10 entries at a time.")
            return
        before = self.raffle_state.get_entries(user)
        self.raffle_state.add_entries(user, amount)
        after = self.raffle_state.get_entries(user)
        await ctx.send(f"@{user} now has {after} number{'s' if after != 1 else ''}.")

    @commands.command(name="tradeentries")
    async def tradeentries(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 3 or not parts[2].isdigit():
            await ctx.send("Usage: !tradeentries @user X")
            return
        from_user = ctx.author.name
        to_user = parts[1].lstrip('@')
        amount = int(parts[2])
        if not (1 <= amount <= 10):
            await ctx.send("Can only trade 1-10 numbers at a time.")
            return
        if self.raffle_state.get_entries(from_user) < amount:
            await ctx.send(f"@{from_user} – You do not have enough numbers to trade.")
            return
        self.raffle_state.remove_entries(from_user, amount)
        self.raffle_state.add_entries(to_user, amount)
        await ctx.send(f"@{to_user} received {amount} number{'s' if amount != 1 else ''} from @{from_user}.")

    @commands.command(name="raffle")
    async def raffle(self, ctx):
        parts = ctx.message.content.split()
        user = ctx.author.name
        entries = self.raffle_state.get_entries(user)
        if len(parts) == 1:
            await ctx.send("Usage: !raffle XXX or !raffle XXX,YYY or !raffle XXX+ N or !raffle random N")
            return
        if parts[1] == "random":
            count = 1
            if len(parts) > 2 and parts[2].isdigit():
                count = int(parts[2])
            ok, numbers = self.raffle_state.pick_random_numbers(user, count)
            if not ok or not numbers:
                await ctx.send(f"@{user} – Unable to register random numbers. You may not have enough numbers or enough picks left.")
            else:
                left = self.raffle_state.get_entries(user) - len(self.raffle_state.get_user_picks(user))
                await ctx.send(f"@{user} – Registered random numbers: {', '.join(numbers)}. You have {left} number{'s' if left != 1 else ''} left.")
            return

        # Handle batch +/-
        if "+" in parts[1] or "-" in parts[1]:
            base = parts[1].rstrip("+-")
            direction = "+" if "+" in parts[1] else "-"
            try:
                start = int(base)
            except ValueError:
                await ctx.send("Invalid number format.")
                return
            count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else entries
            ok, nums = self.raffle_state.pick_series(user, start, count, direction)
            if not ok or not nums:
                await ctx.send(f"@{user} – Unable to register sequence. Numbers may be taken or you lack enough numbers.")
            else:
                left = self.raffle_state.get_entries(user) - len(self.raffle_state.get_user_picks(user))
                await ctx.send(f"@{user} – Registered numbers: {', '.join(nums)}. You have {left} number{'s' if left != 1 else ''} left.")
            return

        # Handle comma separated batch
        picks = [n.strip().zfill(3) for n in parts[1].split(",") if n.strip().isdigit() and 0 <= int(n.strip()) <= 999]
        if not picks:
            await ctx.send("No valid numbers found.")
            return
        ok, result = self.raffle_state.pick_numbers(user, picks)
        if not ok or not result:
            await ctx.send(f"@{user} – {result}")
        else:
            left = self.raffle_state.get_entries(user) - len(self.raffle_state.get_user_picks(user))
            await ctx.send(f"@{user} – Registered numbers: {', '.join(result)}. You have {left} number{'s' if left != 1 else ''} left.")

    @commands.command(name="myentries")
    async def myentries(self, ctx):
        count = self.raffle_state.get_entries(ctx.author.name)
        await ctx.send(f"@{ctx.author.name} – You have {count} number{'s' if count != 1 else ''}.")

    @commands.command(name="mypicks")
    async def mypicks(self, ctx):
        picks = self.raffle_state.get_user_picks(ctx.author.name)
        if not picks:
            await ctx.send(f"@{ctx.author.name} – You have no picks in the current raffle.")
        else:
            await ctx.send(f"@{ctx.author.name} – Your picks: {', '.join(sorted(picks))}")

    @commands.command(name="closeraffle")
    async def closeraffle(self, ctx):
        user = ctx.author.name
        is_mod = getattr(ctx.author, "is_mod", False) or getattr(ctx.author, "is_broadcaster", False)
        if not is_mod:
            await ctx.send("Only mods can close the raffle.")
            return
        if self.raffle_state.nuclear_attempt("closeraffle", user):
            self.raffle_state.close_raffle()
            self.raffle_state.clear_nuclear("closeraffle")
            await ctx.send("Raffle is now closed!")
        else:
            await ctx.send(f"{user} has requested to close the raffle. Waiting for second mod confirmation...")

    @commands.command(name="drawraffle")
    async def drawraffle(self, ctx):
        user = ctx.author.name
        is_mod = getattr(ctx.author, "is_mod", False) or getattr(ctx.author, "is_broadcaster", False)
        if not is_mod:
            await ctx.send("Only mods can draw the raffle.")
            return
        if self.raffle_state.is_open():
            await ctx.send("Raffle must be closed before drawing.")
            return
        if self.raffle_state.nuclear_attempt("drawraffle", user):
            self.raffle_state.clear_nuclear("drawraffle")
            digits, number, winner = self.raffle_state.draw()
            await ctx.send(f"Tonight's first number is... {digits[0]}")
            await asyncio.sleep(1)
            await ctx.send(f"Tonight's second number is... {digits[1]}")
            await asyncio.sleep(1)
            await ctx.send(f"Tonight's third number is... {digits[2]}")
            await asyncio.sleep(1)
            if winner:
                await ctx.send(f"@{winner} is the winner!")
            else:
                await ctx.send("No winner selected, the prize rolls over!")
        else:
            await ctx.send(f"{user} has requested to draw the raffle. Waiting for second mod confirmation...")

    @commands.command(name="clearraffle")
    async def clearraffle(self, ctx):
        user = ctx.author.name
        is_mod = getattr(ctx.author, "is_mod", False) or getattr(ctx.author, "is_broadcaster", False)
        if not is_mod:
            await ctx.send("Only mods can clear the raffle.")
            return
        if self.raffle_state.nuclear_attempt("clearraffle", user):
            self.raffle_state.clear_picks()
            self.raffle_state.clear_nuclear("clearraffle")
            await ctx.send("Raffle cleared. All picks reset; entries remain.")
        else:
            await ctx.send(f"{user} has requested to clear the raffle. Waiting for second mod confirmation...")

    @commands.command(name="testdraw")
    async def testdraw(self, ctx):
        user = ctx.author.name
        is_mod = getattr(ctx.author, "is_mod", False) or getattr(ctx.author, "is_broadcaster", False)
        if not is_mod:
            await ctx.send("Only mods can use testdraw.")
            return
        number, winner = self.raffle_state.test_draw()
        if winner:
            await ctx.send(f"{number} - @{winner}")
        else:
            await ctx.send(f"{number} - no user")

def prepare(bot: commands.Bot):
    # Only create one RaffleState per bot/session
    if not hasattr(bot, "_raffle_state"):
        bot._raffle_state = RaffleState()
    sfx_registry = getattr(bot, "sfx_registry", None)
    print(f"[RaffleCog.prepare] sfx_registry: {sfx_registry}")
    bot.add_cog(RaffleCog(bot, bot._raffle_state, sfx_registry))