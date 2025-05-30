import json
import os
import random
from twitchio.ext import commands

# Always use raffle_state.json in the /data directory at project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
RAFFLE_STATE_FILE = os.path.join(DATA_DIR, "raffle_state.json")

class RaffleState:
    def __init__(self, state_file=RAFFLE_STATE_FILE):
        self.state_file = state_file
        self.state = {
            "is_open": False,
            "entries_per_chat": 1,
            "entries": {},
            "picks": {},
            "chat_awarded": set(),
            "winning_number": None,
            "winner": None,
        }
        self.load()

    def load(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.state.update(data)
            def intify(nums):
                return set(int(n) for n in nums)
            self.state["picks"] = {user: intify(nums) for user, nums in self.state.get("picks", {}).items()}
            self.state["chat_awarded"] = set(self.state.get("chat_awarded", []))
        else:
            self.save()

    def save(self):
        data = dict(self.state)
        data["picks"] = {user: [int(n) for n in nums] for user, nums in self.state["picks"].items()}
        data["chat_awarded"] = list(self.state["chat_awarded"])
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def open_raffle(self, entries_per_chat):
        if not isinstance(entries_per_chat, int) or entries_per_chat < 1:
            raise ValueError("Entries per chat must be a positive integer.")
        self.state["is_open"] = True
        self.state["entries_per_chat"] = entries_per_chat
        # DO NOT CLEAR picks or chat_awarded here!
        self.state["winning_number"] = None
        self.state["winner"] = None
        self.save()

    def close_raffle(self):
        self.state["is_open"] = False
        self.save()

    def reset_for_new_round(self):
        # Only clear everything when explicitly called
        self.state["picks"] = {}
        self.state["chat_awarded"] = set()
        self.state["winning_number"] = None
        self.state["winner"] = None
        self.state["entries"] = {}
        self.save()

    def clear_picks(self):
        self.state["picks"] = {}
        self.save()

    def clear_chat_awarded(self):
        self.state["chat_awarded"] = set()
        self.save()

    def award_chat_entry(self, user):
        if user not in self.state["chat_awarded"]:
            self.state["entries"].setdefault(user, 0)
            self.state["entries"][user] += self.state["entries_per_chat"]
            self.state["chat_awarded"].add(user)
            self.save()
            return self.state["entries_per_chat"]
        return 0

    def add_entries(self, user, count):
        try:
            count = int(count)
        except Exception:
            return False, "Entry count must be a number."
        if count < 1:
            return False, "You must add at least 1 entry."
        self.state["entries"].setdefault(user, 0)
        self.state["entries"][user] += count
        self.save()
        return True, f"Added {count} entr{'y' if count == 1 else 'ies'} to @{user}."

    def remove_entries(self, user, count):
        try:
            count = int(count)
        except Exception:
            return False
        if count < 1:
            return False
        self.state["entries"].setdefault(user, 0)
        if self.state["entries"][user] < count:
            return False
        self.state["entries"][user] -= count
        self.save()
        return True

    def pick_numbers(self, user, numbers):
        already_picked = set()
        for nums in self.state["picks"].values():
            already_picked.update(nums)
        to_pick = []
        for number in numbers:
            try:
                n = int(number)
            except Exception:
                return False, f"Invalid number: {number}"
            if n < 0 or n > 999:
                return False, f"Pick a number between 0 and 999."
            if n in already_picked or n in to_pick:
                return False, f"Number {n:03} has already been picked."
            to_pick.append(n)
        entries_user = self.state["entries"].get(user, 0)
        if entries_user < len(to_pick):
            return False, f"Not enough entries left (need {len(to_pick)}, have {entries_user})."
        self.state["entries"][user] -= len(to_pick)
        self.state["picks"].setdefault(user, set())
        self.state["picks"][user].update(to_pick)
        self.save()
        pick_str = ", ".join(f"{n:03}" for n in to_pick)
        return True, f"Your picks: {pick_str}"

    def pick_random_numbers(self, user, count):
        try:
            count = int(count)
        except Exception:
            return False, "Amount must be a number."
        if count < 1:
            return False, "You must pick at least 1 number."
        if self.state["entries"].get(user, 0) < count:
            return False, f"Not enough entries left (need {count}, have {self.state['entries'].get(user,0)})."
        already_picked = set()
        for nums in self.state["picks"].values():
            already_picked.update(nums)
        available = [n for n in range(1000) if n not in already_picked]
        if len(available) < count:
            return False, f"Not enough available numbers left to pick {count}."
        picks = random.sample(available, count)
        self.state["entries"][user] -= count
        self.state["picks"].setdefault(user, set())
        self.state["picks"][user].update(picks)
        self.save()
        pick_str = ", ".join(f"{n:03}" for n in sorted(picks))
        return True, f"Random picks: {pick_str}"

    def pick_number(self, user, number):
        return self.pick_numbers(user, [number])

    def pick_random_number(self, user):
        return self.pick_random_numbers(user, 1)

    def user_entries(self, user):
        return self.state["entries"].get(user, 0)

    def user_picks(self, user):
        return sorted(int(n) for n in self.state["picks"].get(user, set()))

    def all_picks(self):
        return {user: sorted(int(n) for n in nums) for user, nums in self.state["picks"].items()}

    def draw_winner(self):
        all_picked_numbers = []
        for user, picks in self.state["picks"].items():
            for num in picks:
                all_picked_numbers.append((user, num))
        if not all_picked_numbers:
            return None, "No numbers have been picked."
        winner_user, winning_number = random.choice(all_picked_numbers)
        self.state["winning_number"] = winning_number
        self.state["winner"] = winner_user
        self.save()
        # Only clear picks and chat_awarded after drawing a winner, NOT on open/close
        self.clear_picks()
        self.clear_chat_awarded()
        return winner_user, f"Winner: @{winner_user} with {int(winning_number):03}!"

    def my_entries_string(self, user):
        entries = self.user_entries(user)
        return f"You have {entries} entr{'y' if entries == 1 else 'ies'} left."

    def my_picks_string(self, user):
        picks = self.user_picks(user)
        if not picks:
            return "You have no picks in the current raffle."
        return "Your picks: " + ", ".join(f"{n:03}" for n in picks)

    def gift_entries(self, giver, recipient, count):
        try:
            count = int(count)
        except Exception:
            return False, "Entry count must be a number."
        if count < 1:
            return False, "You must gift at least 1 entry."
        if giver == recipient:
            return False, "Cannot gift entries to yourself."
        if self.user_entries(giver) < count:
            return False, "Not enough entries to gift."
        self.state["entries"][giver] -= count
        self.state["entries"].setdefault(recipient, 0)
        self.state["entries"][recipient] += count
        self.save()
        return True, f"Gifted {count} entr{'y' if count == 1 else 'ies'} to @{recipient}."

    def trade_entries(self, from_user, to_user, count):
        try:
            count = int(count)
        except Exception:
            return False, "Entry count must be a number."
        if count < 1:
            return False, "You must trade at least 1 entry."
        if from_user == to_user:
            return False, "Cannot trade with yourself."
        if self.user_entries(from_user) < count:
            return False, "Not enough entries to trade."
        self.state["entries"][from_user] -= count
        self.state["entries"].setdefault(to_user, 0)
        self.state["entries"][to_user] += count
        self.save()
        return True, f"Traded {count} entr{'y' if count == 1 else 'ies'} to @{to_user}."


class RaffleCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.state = RaffleState()

    @commands.command(name="openraffle")
    async def open_raffle_cmd(self, ctx, entries_per_chat: int = 1):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can open the raffle.")
            return
        if entries_per_chat < 1:
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
        # This is the NUCLEAR OPTION: clears everything, for emergencies only!
        self.state.reset_for_new_round()
        await ctx.send("All raffle data has been cleared. This action is irreversible!")

    @commands.command(name="raffle")
    async def raffle_cmd(self, ctx, *args):
        user = ctx.author.name.lower()
        if not self.state.state["is_open"]:
            await ctx.send("Raffle is not open.")
            return
        if not args:
            await ctx.send("Pick a number: !raffle <number>, !raffle random, !raffle random 3, or !raffle 123,456,789")
            return

        # !raffle random N
        if args[0].lower() == "random":
            if len(args) > 1:
                try:
                    n = int(args[1])
                except Exception:
                    await ctx.send("Usage: !raffle random [amount]")
                    return
                if n < 1:
                    await ctx.send("You must pick at least 1 number.")
                    return
                ok, msg = self.state.pick_random_numbers(user, n)
                await ctx.send(f"@{user} – {msg}")
                return
            ok, msg = self.state.pick_random_number(user)
            await ctx.send(f"@{user} – {msg}")
            return

        # !raffle 123,456,789 or !raffle 123 456 789
        numbers = []
        for arg in args:
            if ',' in arg:
                numbers.extend([x.strip() for x in arg.split(',') if x.strip()])
            else:
                numbers.append(arg)
        # Validate all numbers before trying to pick
        for number in numbers:
            try:
                n = int(number)
            except Exception:
                await ctx.send(f"@{user} – Invalid number: {number}")
                return
            if n < 0 or n > 999:
                await ctx.send(f"@{user} – Pick a number between 0 and 999.")
                return
        if len(numbers) == 1:
            ok, msg = self.state.pick_number(user, numbers[0])
        else:
            ok, msg = self.state.pick_numbers(user, numbers)
        await ctx.send(f"@{user} – {msg}")

    @commands.command(name="myentries")
    async def myentries_cmd(self, ctx):
        user = ctx.author.name.lower()
        await ctx.send(f"@{user} – {self.state.my_entries_string(user)}")

    @commands.command(name="mypicks")
    async def mypicks_cmd(self, ctx):
        user = ctx.author.name.lower()
        await ctx.send(f"@{user} – {self.state.my_picks_string(user)}")

    @commands.command(name="drawraffle")
    async def drawraffle_cmd(self, ctx):
        if not ctx.author.is_mod:
            await ctx.send("Only mods can draw a winner.")
            return
        winner, msg = self.state.draw_winner()
        await ctx.send(msg if winner else "No winner could be drawn.")

    @commands.command(name="giveraffle")
    async def giveraffle_cmd(self, ctx, count: int = None, recipient: str = None):
        user = ctx.author.name.lower()
        if count is None or recipient is None:
            await ctx.send("Usage: !giveraffle <count> @user")
            return
        recipient = recipient.lstrip("@").lower()
        try:
            count = int(count)
        except Exception:
            await ctx.send("Entry count must be a number.")
            return
        if count < 1:
            await ctx.send("You must gift at least 1 entry.")
            return
        ok, msg = self.state.gift_entries(user, recipient, count)
        await ctx.send(f"@{user} – {msg}")

    @commands.command(name="traderaffle")
    async def traderaffle_cmd(self, ctx, count: int = None, recipient: str = None):
        user = ctx.author.name.lower()
        if count is None or recipient is None:
            await ctx.send("Usage: !traderaffle <count> @user")
            return
        recipient = recipient.lstrip("@").lower()
        try:
            count = int(count)
        except Exception:
            await ctx.send("Entry count must be a number.")
            return
        if count < 1:
            await ctx.send("You must trade at least 1 entry.")
            return
        ok, msg = self.state.trade_entries(user, recipient, count)
        await ctx.send(f"@{user} – {msg}")

    @commands.Cog.event()
    async def event_message(self, message):
        # Only award entries for normal chat (not commands), and not from the bot itself
        if message.echo or message.content.startswith("!"):
            return
        user = message.author.name.lower()
        if self.state.state["is_open"] and user not in self.state.state["chat_awarded"]:
            count = self.state.award_chat_entry(user)
            if count > 0:
                await message.channel.send(
                    f"@{user} – Here {'is' if count == 1 else 'are'} {count} complimentary entr{'y' if count == 1 else 'ies'}."
                )

def prepare(bot):
    if not bot.get_cog("RaffleCog"):
        bot.add_cog(RaffleCog(bot))