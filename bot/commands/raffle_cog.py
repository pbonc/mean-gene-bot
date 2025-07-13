import json
import os
import random
import asyncio
from twitchio.ext import commands

# Data files for this bot are stored in the project root's 'data' folder.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
RAFFLE_STATE_FILE = os.path.join(DATA_DIR, "raffle_state.json")

HELP_TEXT = """
🎟️ Raffle Commands:
!raffle help                - Show this help message.
!raffle open [per_chat]     - (Mod) Open the raffle. Optionally set entries per chat.
!raffle close [minutes]     - (Mod) Close the raffle (immediately or in [minutes]).
!raffle clear               - (Mod) Clear all raffle data.
!raffle draw                - (Mod) Draw the winning number.
!raffle addentries <user> <count> - (Mod) Add entries for a user.
!raffle testdata            - (Mod) Populate with test data.
!raffle testdraw            - (Mod) Simulate a random draw.
!raffle ignore <user>       - (Mod) Ignore a user from the raffle.
!raffle unignore <user>     - (Mod) Remove a user from the ignore list.
!raffle ignored             - (Mod) List all ignored users.
!raffle pick <numbers>      - Pick one or more numbers (comma or space separated).
!raffle random [amount]     - Pick [amount] random numbers (default 1).
!raffle entries             - Show your current entry count.
!raffle picks               - Show your current picks.
!raffle trade <user> <count> - Trade entries to another user.
"""

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
        self.first_chatter_awarded = False
        self.first_chatter_user = None
        self.ignored_users = set()
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
            self.first_chatter_awarded = data.get("first_chatter_awarded", False)
            self.first_chatter_user = data.get("first_chatter_user", None)
            self.ignored_users = set([u.lower() for u in data.get("ignored_users", [])])
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
            "first_chatter_awarded": self.first_chatter_awarded,
            "first_chatter_user": self.first_chatter_user,
            "ignored_users": list(self.ignored_users),
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def open_raffle(self, entries_per_chat):
        self.is_open = True
        self.entries_per_chat = entries_per_chat
        self.chat_awarded = set()
        self.first_chatter_awarded = False
        self.first_chatter_user = None
        self.save()

    def close_raffle(self):
        self.is_open = False
        self.save()

    def reset(self):
        self.picks = {}
        self.winner = None
        self.winning_number = None
        self.chat_awarded = set()
        self.first_chatter_awarded = False
        self.first_chatter_user = None
        self.entries = {}
        self.ignored_users = set()
        self.save()

    def add_entries(self, user, count):
        user = user.lower()
        if user in self.ignored_users:
            return False
        self.entries[user] = self.entries.get(user, 0) + count
        self.save()
        return True

    def trade_entries(self, from_user, to_user, count):
        from_user = from_user.lower()
        to_user = to_user.lower()
        if from_user == to_user:
            return False, "Cannot trade entries to yourself."
        if to_user in self.ignored_users:
            return False, f"@{to_user} is not eligible for the raffle."
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
        user = user.lower()
        if user in self.ignored_users:
            return False, "You are not eligible for the raffle."
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
        user = user.lower()
        if user in self.ignored_users:
            return False, "You are not eligible for the raffle."
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
        return self.entries.get(user.lower(), 0)

    def user_picks(self, user):
        user = user.lower()
        picks = [num for num, u in self.picks.items() if u == user]
        return sorted(picks, key=lambda x: int(x))

    def draw_winner(self):
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
        user = user.lower()
        if user in self.ignored_users:
            return 0
        if user not in self.chat_awarded:
            self.entries[user] = self.entries.get(user, 0) + self.entries_per_chat
            self.chat_awarded.add(user)
            self.save()
            return self.entries_per_chat
        return 0

    def award_first_chatter(self, user):
        user = user.lower()
        if user in self.ignored_users:
            return 0
        if not self.first_chatter_awarded:
            bonus = max(5, 2 * self.entries_per_chat)
            self.entries[user] = self.entries.get(user, 0) + bonus
            self.first_chatter_awarded = True
            self.first_chatter_user = user
            self.chat_awarded.add(user)
            self.save()
            return bonus
        return 0

    def ignore_user(self, user):
        user = user.lower()
        self.ignored_users.add(user)
        self.save()

    def unignore_user(self, user):
        user = user.lower()
        self.ignored_users.discard(user)
        self.save()

    def is_ignored(self, user):
        return user.lower() in self.ignored_users

    def get_ignored_users(self):
        return sorted(list(self.ignored_users))

class RaffleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = SimpleRaffleState()
        self._raffle_closing_task = None

    @commands.command(name="raffle")
    async def raffle_command(self, ctx, *args):
        user = ctx.author.name.lower()
        args = list(args)
        if not args or (args[0].lower() == "help"):
            await ctx.send(HELP_TEXT)
            return

        cmd = args[0].lower()

        # Mods only commands
        if cmd == "open":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can open the raffle.")
                return
            entries_per_chat = 1
            if len(args) > 1:
                try:
                    entries_per_chat = int(args[1])
                    if entries_per_chat < 1:
                        raise ValueError
                except Exception:
                    await ctx.send("Usage: !raffle open [entries_per_chat]")
                    return
            self.state.open_raffle(entries_per_chat)
            await ctx.send(f"Raffle is now open! Anyone who chats gets {entries_per_chat} free entr{'y' if entries_per_chat == 1 else 'ies'}! First chatter gets a special bonus.")
            return

        if cmd == "close":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can close the raffle.")
                return
            if self._raffle_closing_task and not self._raffle_closing_task.done():
                await ctx.send("A raffle closing countdown is already in progress!")
                return
            if len(args) > 1:
                try:
                    mins = int(args[1])
                    if mins not in (1, 2, 3, 4, 5):
                        raise ValueError
                except Exception:
                    await ctx.send("Usage: !raffle close [minutes (1-5)]")
                    return
                await ctx.send(f"Raffle will close in {mins} minute{'s' if mins > 1 else ''}!")
                self._raffle_closing_task = asyncio.create_task(self._countdown_to_closure(ctx, mins))
                return
            self.state.close_raffle()
            await ctx.send("Raffle is now closed.")
            return

        if cmd == "clear":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can clear the raffle.")
                return
            self.state.reset()
            await ctx.send("All raffle data has been cleared. This action is irreversible!")
            return

        if cmd == "draw":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can draw a winner.")
                return
            winner, _ = self.state.draw_winner()
            num = self.state.winning_number or "???"
            # Dramatic reveal
            await ctx.send(f"The first number is: {num[0]}")
            await asyncio.sleep(1.5)
            await ctx.send(f"The second number is: {num[1]}")
            await asyncio.sleep(1.5)
            await ctx.send(f"The third number is: {num[2]}")
            await asyncio.sleep(1.5)
            if winner:
                await ctx.send(f"The winning number is {num}! Congratulations @{winner}!")
            else:
                await ctx.send(f"The winning number is {num}! No winner! The prize rolls over!")
            return

        if cmd == "addentries":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can add entries for users.")
                return
            if len(args) < 3:
                await ctx.send("Usage: !raffle addentries <user> <count>")
                return
            recipient = args[1].lstrip("@").lower()
            try:
                n = int(args[2])
            except Exception:
                await ctx.send("Please enter a positive whole number.")
                return
            if n < 1:
                await ctx.send("Please enter a positive whole number.")
                return
            ok = self.state.add_entries(recipient, n)
            if ok:
                await ctx.send(f"Created {n} entr{'y' if n == 1 else 'ies'} for @{recipient}.")
            else:
                await ctx.send(f"User @{recipient} is not eligible for the raffle.")
            return

        if cmd == "testdata":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can use !raffle testdata.")
                return
            # Create 30 fake users with random entries (1-20)
            users = [f"user{i}" for i in range(1, 31)]
            self.state.entries = {}
            self.state.picks = {}
            all_numbers = [f"{n:03}" for n in range(1000)]
            random.shuffle(all_numbers)
            assigned = 0
            for userx in users:
                entry_count = random.randint(1, 20)
                self.state.entries[userx] = entry_count
                pick_count = min(random.randint(1, max(1, entry_count // 2 + 1)), len(all_numbers) - assigned)
                picks = all_numbers[assigned:assigned+pick_count]
                assigned += pick_count
                for num in picks:
                    self.state.picks[num] = userx
                if assigned >= len(all_numbers):
                    break
            self.state.save()
            await ctx.send(f"Populated test data: {len(users)} users, {len(self.state.picks)} picked numbers, entries assigned 1–20 each.")
            return

        if cmd == "testdraw":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can use !raffle testdraw.")
                return
            number = f"{random.randint(0, 999):03}"
            userx = self.state.picks.get(number)
            if userx:
                await ctx.send(f"Test draw: {number} - {userx}")
            else:
                await ctx.send(f"Test draw: {number} - empty (prize would roll over)")
            return

        if cmd == "ignore":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can ignore users from the raffle.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !raffle ignore <user>")
                return
            to_ignore = args[1].lstrip("@").lower()
            self.state.ignore_user(to_ignore)
            await ctx.send(f"@{to_ignore} is now ignored from the raffle.")
            return

        if cmd == "unignore":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can unignore users from the raffle.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !raffle unignore <user>")
                return
            to_unignore = args[1].lstrip("@").lower()
            self.state.unignore_user(to_unignore)
            await ctx.send(f"@{to_unignore} is no longer ignored from the raffle.")
            return

        if cmd == "ignored":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can view the ignore list.")
                return
            ignored = self.state.get_ignored_users()
            await ctx.send(f"Ignored users: {', '.join('@'+u for u in ignored) if ignored else '(none)'}")
            return

        # User commands
        if cmd == "pick":
            if not self.state.is_open:
                await ctx.send("Raffle is not open.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !raffle pick <numbers>")
                return
            # Accept comma or space separated numbers
            numbers = []
            for arg in args[1:]:
                if ',' in arg:
                    numbers.extend([x.strip() for x in arg.split(',') if x.strip()])
                else:
                    numbers.append(arg.strip())
            ok, msg = self.state.pick_numbers(user, numbers)
            await ctx.send(f"@{user} – {msg}")
            return

        if cmd == "random":
            if not self.state.is_open:
                await ctx.send("Raffle is not open.")
                return
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

        if cmd == "entries":
            count = self.state.user_entries(user)
            await ctx.send(f"@{user} – You have {count} entr{'y' if count == 1 else 'ies'} left.")
            return

        if cmd == "picks":
            picks = self.state.user_picks(user)
            if not picks:
                await ctx.send(f"@{user} – You have no picks in the current raffle.")
            else:
                await ctx.send(f"@{user} – Your picks: {', '.join(picks)}")
            return

        if cmd == "trade":
            if len(args) < 3:
                await ctx.send("Usage: !raffle trade <user> <count>")
                return
            recipient = args[1].lstrip("@").lower()
            try:
                n = int(args[2])
            except Exception:
                await ctx.send("Please enter a positive whole number.")
                return
            ok, msg = self.state.trade_entries(user, recipient, n)
            await ctx.send(f"@{user} – {msg}")
            return

        # Unknown subcommand: fallback to help
        await ctx.send(HELP_TEXT)

    async def _countdown_to_closure(self, ctx, mins):
        total_seconds = mins * 60
        checkpoints = [
            (120, "2 minutes left to enter the raffle!"),
            (60, "1 minute left to enter the raffle!"),
            (30, "30 seconds left to enter the raffle!"),
        ]
        now = asyncio.get_event_loop().time()
        closes_at = now + total_seconds

        for sec, msg in checkpoints:
            if total_seconds > sec:
                sleep_amt = closes_at - asyncio.get_event_loop().time() - sec
                if sleep_amt > 0:
                    await asyncio.sleep(sleep_amt)
                await ctx.send(msg)
        # Wait until closure
        sleep_amt = closes_at - asyncio.get_event_loop().time()
        if sleep_amt > 0:
            await asyncio.sleep(sleep_amt)
        self.state.close_raffle()
        await ctx.send("Raffle is now closed.")

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return
        user = message.author.name.lower()
        # Only award if raffle is open and user hasn't received any chat entry this round
        if self.state.is_open and user not in self.state.chat_awarded and not self.state.is_ignored(user):
            # First chatter logic
            if not self.state.first_chatter_awarded:
                bonus = self.state.award_first_chatter(user)
                if bonus > 0:
                    await message.channel.send(
                        f"🎉 Congratulations @{user} for being FIRST in chat after the raffle opened! You receive {bonus} raffle entr{'y' if bonus == 1 else 'ies'}! 🎟️"
                    )
                    return
            # All other chatters
            count = self.state.award_chat_entry(user)
            if count > 0:
                await message.channel.send(
                    f"@{user} – Here {'is' if count == 1 else 'are'} {count} complimentary entr{'y' if count == 1 else 'ies'}."
                )

def prepare(bot):
    if not bot.get_cog("RaffleCog"):
        bot.add_cog(RaffleCog(bot))