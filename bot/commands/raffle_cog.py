import json
import os
import random
from twitchio.ext import commands

# Data files for this bot are stored in the project root's 'data' folder.
# This keeps persistent files together and avoids confusion between bot/data and top-level data.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
RAFFLE_STATE_FILE = os.path.join(DATA_DIR, "raffle_state.json")

class SimpleRaffleState:
    def __init__(self, state_file=RAFFLE_STATE_FILE):
        self.state_file = state_file
        self.is_open = False
        self.entries_per_chat = 1
        self.entries = {}  # user -> int
        self.picks = {}    # 'NNN' -> user
        self.winner = None
        self.winning_number = None
        self.chat_awarded = set()
        self.load()

    def load(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.is_open = data.get("is_open", False)
            self.entries_per_chat = data.get("entries_per_chat", 1)
            self.entries = data.get("entries", {})
            self.picks = data.get("picks", {})
            self.winner = data.get("winner", None)
            self.winning_number = data.get("winning_number", None)
            self.chat_awarded = set(data.get("chat_awarded", []))
        else:
            self.save()

    def save(self):
        sorted_picks = {k: self.picks[k] for k in sorted(self.picks, key=lambda x: int(x))}
        data = {
            "is_open": self.is_open,
            "entries_per_chat": self.entries_per_chat,
            "entries": self.entries,
            "picks": sorted_picks,
            "winner": self.winner,
            "winning_number": self.winning_number,
            "chat_awarded": list(self.chat_awarded),
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def open_raffle(self, entries_per_chat):
        self.is_open = True
        self.entries_per_chat = entries_per_chat
        self.chat_awarded = set()
        self.save()

    def close_raffle(self):
        self.is_open = False
        self.save()

    def reset(self):
        self.entries = {}
        self.picks = {}
        self.winner = None
        self.winning_number = None
        self.chat_awarded = set()
        self.save()

    def add_entries(self, user, count):
        self.entries[user] = self.entries.get(user, 0) + count
        self.save()

    def trade_entries(self, from_user, to_user, count):
        if from_user == to_user:
            return False, "Cannot trade entries to yourself."
        if not (isinstance(count, int) and count > 0):
            if isinstance(count, int) and count < 0:
                return False, "Error Code: Caerdwyn -1"
            return False, "Please enter a positive whole number."
        if self.entries.get(from_user, 0) < count:
            return False, "You do not have enough entries to trade."
        self.entries[from_user] -= count
        self.entries[to_user] = self.entries.get(to_user, 0) + count
        self.save()
        return True, f"Traded {count} entr{'y' if count == 1 else 'ies'} to @{to_user}."

    def pick_numbers(self, user, numbers):
        # All-or-nothing: every pick must be valid and available
        errors = []
        picks_to_make = []
        for num in numbers:
            if not (isinstance(num, str) and num.isdigit() and len(num) == 3 and 0 <= int(num) <= 999):
                errors.append(f"{num} is not a valid three-digit number.")
            elif num in self.picks:
                errors.append(f"{num} is already picked.")
            elif num in picks_to_make:
                errors.append(f"{num} is a duplicate in your picks.")
            else:
                picks_to_make.append(num)
        if errors:
            return False, f"None of your picks were accepted: {errors[0]}"
        if self.entries.get(user, 0) < len(picks_to_make):
            return False, f"Not enough entries left (need {len(picks_to_make)}, have {self.entries.get(user,0)})."
        self.entries[user] -= len(picks_to_make)
        for num in picks_to_make:
            self.picks[num] = user
        self.save()
        pick_str = ", ".join(picks_to_make)
        return True, f"Your picks: {pick_str}"

    def pick_random_numbers(self, user, count):
        if not (isinstance(count, int) and count > 0):
            return False, "You must pick at least 1 number."
        if self.entries.get(user, 0) < count:
            return False, f"Not enough entries left (need {count}, have {self.entries.get(user,0)})."
        available = [f"{n:03}" for n in range(1000) if f"{n:03}" not in self.picks]
        if len(available) < count:
            return False, f"Not enough available numbers left to pick {count}."
        picks = random.sample(available, count)
        self.entries[user] -= count
        for num in picks:
            self.picks[num] = user
        self.save()
        pick_str = ", ".join(sorted(picks))
        return True, f"Random picks: {pick_str}"

    def user_entries(self, user):
        return self.entries.get(user, 0)

    def user_picks(self, user):
        picks = [num for num, u in self.picks.items() if u == user]
        return sorted(picks, key=lambda x: int(x))

    def draw_winner(self):
        # Always pick a number from 000 to 999 (inclusive), not just numbers that were picked
        number = f"{random.randint(0, 999):03}"
        user = self.picks.get(number)
        self.winning_number = number
        if user:
            self.winner = user
            self.save()
            return user, f"Winner: @{user} with {number}!"
        else:
            self.winner = None
            self.save()
            return None, f"No winner! The drawn number was {number}. Prize rolls over!"

    def award_chat_entry(self, user):
        if user not in self.chat_awarded:
            self.entries[user] = self.entries.get(user, 0) + self.entries_per_chat
            self.chat_awarded.add(user)
            self.save()
            return self.entries_per_chat
        return 0

class RaffleCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.state = SimpleRaffleState()

    @commands.command(name="openraffle")
    async def open_raffle_cmd(self, ctx, entries_per_chat: int = 1):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can open the raffle.")
            return
        if not isinstance(entries_per_chat, int) or entries_per_chat < 1:
            await ctx.send("Entries per chat must be at least 1.")
            return
        self.state.open_raffle(entries_per_chat)
        await ctx.send(f"Raffle is now open! Anyone who chats gets {entries_per_chat} free entr{'y' if entries_per_chat == 1 else 'ies'}!")

    @commands.command(name="closeraffle")
    async def close_raffle_cmd(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can close the raffle.")
            return
        self.state.close_raffle()
        await ctx.send("Raffle is now closed.")

    @commands.command(name="clearraffle")
    async def clearraffle_cmd(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can clear the raffle.")
            return
        self.state.reset()
        await ctx.send("All raffle data has been cleared. This action is irreversible!")

    @commands.command(name="raffle")
    async def raffle_cmd(self, ctx, *args):
        user = ctx.author.name.lower()
        if not self.state.is_open:
            await ctx.send("Raffle is not open.")
            return
        if not args:
            await ctx.send("Pick a number: !raffle <three-digit-number>, !raffle random, !raffle random 3, or !raffle 005,123,789")
            return

        # !raffle random N
        if args[0].lower() == "random":
            n = 1
            if len(args) > 1:
                try:
                    n = int(args[1])
                except Exception:
                    await ctx.send("Usage: !raffle random [amount]")
                    return
            ok, msg = self.state.pick_random_numbers(user, n)
            await ctx.send(f"@{user} – {msg}")
            return

        # !raffle 005,123,789 or !raffle 005 123 789
        numbers = []
        for arg in args:
            if ',' in arg:
                numbers.extend([x.strip() for x in arg.split(',') if x.strip()])
            else:
                numbers.append(arg.strip())
        # All picks must be 3 digits and valid together
        ok, msg = self.state.pick_numbers(user, numbers)
        await ctx.send(f"@{user} – {msg}")

    @commands.command(name="myentries")
    async def myentries_cmd(self, ctx):
        user = ctx.author.name.lower()
        count = self.state.user_entries(user)
        await ctx.send(f"@{user} – You have {count} entr{'y' if count == 1 else 'ies'} left.")

    @commands.command(name="mypicks")
    async def mypicks_cmd(self, ctx):
        user = ctx.author.name.lower()
        picks = self.state.user_picks(user)
        if not picks:
            await ctx.send(f"@{user} – You have no picks in the current raffle.")
        else:
            await ctx.send(f"@{user} – Your picks: {', '.join(picks)}")

    @commands.command(name="drawraffle")
    async def drawraffle_cmd(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can draw a winner.")
            return
        winner, msg = self.state.draw_winner()
        await ctx.send(msg)

    @commands.command(name="rafflecreate")
    async def rafflecreate_cmd(self, ctx, count: str = None, recipient: str = None):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can create entries for users.")
            return
        if count is None or recipient is None:
            await ctx.send("Usage: !rafflecreate <count> @user")
            return
        recipient = recipient.lstrip("@").lower()
        try:
            n = int(count)
        except Exception:
            await ctx.send("Please enter a positive whole number.")
            return
        if n < 1:
            await ctx.send("Please enter a positive whole number.")
            return
        self.state.add_entries(recipient, n)
        await ctx.send(f"Created {n} entr{'y' if n == 1 else 'ies'} for @{recipient}.")

    @commands.command(name="testdraw")
    async def testdraw_cmd(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use !testdraw.")
            return
        # Use same logic as draw_winner but do not update state or announce winners
        number = f"{random.randint(0, 999):03}"
        user = self.state.picks.get(number)
        if user:
            await ctx.send(f"Test draw: {number} - {user}")
        else:
            await ctx.send(f"Test draw: {number} - empty (prize would roll over)")

    @commands.command(name="raffletrade")
    async def raffletrade_cmd(self, ctx, count: str = None, recipient: str = None):
        user = ctx.author.name.lower()
        if count is None or recipient is None:
            await ctx.send("Usage: !raffletrade <count> @user")
            return
        recipient = recipient.lstrip("@").lower()
        try:
            n = int(count)
        except Exception:
            await ctx.send("Please enter a positive whole number.")
            return
        ok, msg = self.state.trade_entries(user, recipient, n)
        await ctx.send(f"@{user} – {msg}")

    @commands.command(name="raffletestdata")
    async def raffletestdata_cmd(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use !raffletestdata.")
            return
        # Create 30 fake users with random entries (1-20)
        users = [f"user{i}" for i in range(1, 31)]
        self.state.entries = {}
        self.state.picks = {}
        all_numbers = [f"{n:03}" for n in range(1000)]
        random.shuffle(all_numbers)
        assigned = 0
        for user in users:
            entry_count = random.randint(1, 20)
            self.state.entries[user] = entry_count
            pick_count = min(random.randint(1, max(1, entry_count // 2 + 1)), len(all_numbers) - assigned)
            picks = all_numbers[assigned:assigned+pick_count]
            assigned += pick_count
            for num in picks:
                self.state.picks[num] = user
            if assigned >= len(all_numbers):
                break
        self.state.save()
        await ctx.send(f"Populated test data: {len(users)} users, {len(self.state.picks)} picked numbers, entries assigned 1–20 each.")

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo or message.content.startswith("!"):
            return
        user = message.author.name.lower()
        if self.state.is_open and user not in self.state.chat_awarded:
            count = self.state.award_chat_entry(user)
            if count > 0:
                await message.channel.send(
                    f"@{user} – Here {'is' if count == 1 else 'are'} {count} complimentary entr{'y' if count == 1 else 'ies'}."
                )

def prepare(bot):
    if not bot.get_cog("RaffleCog"):
        bot.add_cog(RaffleCog(bot))