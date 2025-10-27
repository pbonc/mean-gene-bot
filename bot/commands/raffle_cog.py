import json
import os
import random
import asyncio
from twitchio.ext import commands

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
RAFFLE_STATE_FILE = os.path.join(DATA_DIR, "raffle_state.json")

def chunk_message(text, limit=480):
    lines = text.strip().splitlines()
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > limit:
            if chunk.strip():
                yield chunk.strip()
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        yield chunk.strip()

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
        # Ensure jackpot default exists before loading (load may call save)
        self.bad_beat_jackpot = 25
        self.load()
        if not hasattr(self, 'bad_beat_jackpot'):
            self.bad_beat_jackpot = 25

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
            self.bad_beat_jackpot = data.get("bad_beat_jackpot", 25)
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
            "bad_beat_jackpot": self.bad_beat_jackpot,
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
        # Do NOT reset bad_beat_jackpot here (leave as-is)
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
            return user, number
        else:
            self.winner = None
            self.save()
            return None, number

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
    @commands.command(name="badbeat")
    async def badbeat_command(self, ctx):
        """Show the current bad beat jackpot in chat."""
        jackpot = self.state.bad_beat_jackpot if hasattr(self.state, 'bad_beat_jackpot') else 25
        await ctx.send(f"The current bad beat jackpot is {jackpot} entries!")
        
    def __init__(self, bot):
        self.bot = bot
        self.state = SimpleRaffleState()
        self._raffle_closing_task = None

    async def send_to_discord(self, message):
        """Send message to Discord if Discord client is available."""
        if hasattr(self.bot, 'discord_client') and self.bot.discord_client:
            try:
                await self.bot.discord_client.send_to_channel(message)
            except Exception as e:
                print(f'[DISCORD ERROR] Failed to send message: {e}')

    async def send_long_message(self, ctx, text):
        for chunk in chunk_message(text):
            await ctx.send(chunk)

    @commands.command(name="testdrawmessage")
    async def test_draw_message(self, ctx):
        """Test Discord integration by sending a fake draw message."""
        if not ctx.author.is_mod:
            await ctx.send("Only mods can use this command.")
            return
        
        # Send a fake winner message to Discord
        test_message = "🎉 TEST: The winning number is 007! Congratulations @testuser! (123 out of 1000 numbers were picked)"
        await self.send_to_discord(test_message)
        await ctx.send("Test draw message sent to Discord!")

    @commands.command(name="raffle")
    async def raffle_command(self, ctx, *args):
        user = ctx.author.name.lower()
        args = list(args)
        if not args or (args[0].lower() == "help"):
            await ctx.send("https://docs.google.com/document/d/1hEguHGkhTYTDIcfFOSrbT34_xKUqw0t5nP3-cXWICKk")
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
            message = f"Raffle is now open! Anyone who chats gets {entries_per_chat} free entr{'y' if entries_per_chat == 1 else 'ies'}! First chatter gets a special bonus."
            await ctx.send(message)
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
            message = "Raffle is now closed."
            await ctx.send(message)
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
            winner, num = self.state.draw_winner()
            # Dramatic reveal
            await ctx.send(f"The first number is: {num[0]}")
            await asyncio.sleep(1.5)
            await ctx.send(f"The second number is: {num[1]}")
            await asyncio.sleep(1.5)
            await ctx.send(f"The third number is: {num[2]}")
            await asyncio.sleep(1.5)
            picks = self.state.picks
            winning_int = int(num)
            closest_distance = 1000
            closest_picks = []
            closest_users = []
            bad_beat_users = []
            bad_beat_numbers = []

            # Check all picked numbers
            for pick, pick_user in picks.items():
                pick_int = int(pick)
                dist = abs(pick_int - winning_int)
                if dist == 1:
                    if pick_user != winner:
                        bad_beat_users.append(pick_user)
                        bad_beat_numbers.append(pick)
                if winner is None:
                    # Closest pick logic for no winner
                    if dist < closest_distance:
                        closest_distance = dist
                        closest_picks = [pick]
                        closest_users = [pick_user]
                    elif dist == closest_distance:
                        closest_picks.append(pick)
                        closest_users.append(pick_user)
            if winner:
                total_picks = len(self.state.picks)
                winner_message = f"The winning number is {num}! Congratulations @{winner}!"
                discord_winner_message = f"🎉 {winner_message} ({total_picks} out of 1000 numbers were picked)"
                await ctx.send(winner_message)
                await self.send_to_discord(discord_winner_message)
                if bad_beat_users:
                    user_number_pairs = [f"@{u} ({n})" for u, n in zip(bad_beat_users, bad_beat_numbers)]
                    jackpot = self.state.bad_beat_jackpot if hasattr(self.state, 'bad_beat_jackpot') else 25
                    split = (jackpot + len(set(bad_beat_users)) - 1) // len(set(bad_beat_users))
                    bad_beat_message = f"Bad beat! {' and '.join(user_number_pairs)} {'was' if len(bad_beat_users) == 1 else 'were'} off by one and receive {split} bonus entr{'y' if split == 1 else 'ies'} each from the jackpot!"
                    await ctx.send(bad_beat_message)
                    await self.send_to_discord(f"💔 {bad_beat_message}")
                    for bbuser in set(bad_beat_users):
                        self.state.add_entries(bbuser, split)
                    self.state.bad_beat_jackpot = 25
                    self.state.save()
                else:
                    no_bad_beat_message = "There were no bad beats this draw."
                    await ctx.send(no_bad_beat_message)
                    await self.send_to_discord(f"ℹ️ {no_bad_beat_message}")
                    self.state.bad_beat_jackpot = 25
                    self.state.save()
            else:
                total_picks = len(self.state.picks)
                no_winner_message = f"The winning number is {num}! No winner! The prize rolls over!"
                discord_no_winner_message = f"😔 {no_winner_message} ({total_picks} out of 1000 numbers were picked)"
                await ctx.send(no_winner_message)
                await self.send_to_discord(discord_no_winner_message)
                # Closest picks
                if closest_picks:
                    # Find all unique (user, pick) pairs for the closest picks
                    pairs = list(set((u, p) for u, p in zip(closest_users, closest_picks)))
                    pair_strs = [f"@{u} ({p})" for (u, p) in pairs]
                    closest_message = f"Closest pick(s): {' , '.join(pair_strs)} (distance {closest_distance})"
                    await ctx.send(closest_message)
                    await self.send_to_discord(f"🎯 {closest_message}")
                # No winner: increment jackpot by 5
                self.state.bad_beat_jackpot += 5
                jackpot_message = f"Bad beat jackpot increased to {self.state.bad_beat_jackpot} entries!"
                await self.send_to_discord(f"💰 {jackpot_message}")
                self.state.save()
            return

        if cmd == "simdraw":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can use !raffle simdraw.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !raffle simdraw <count>")
                return
            try:
                simcount = int(args[1])
                if simcount < 1 or simcount > 10000:
                    raise ValueError
            except Exception:
                await ctx.send("Please enter a positive integer between 1 and 10000.")
                return
            winner_count = 0
            loser_count = 0
            current_picks = dict(self.state.picks)
            for _ in range(simcount):
                number = f"{random.randint(0, 999):03}"
                if number in current_picks:
                    winner_count += 1
                else:
                    loser_count += 1
            await ctx.send(f"Simulated {simcount} draws: {winner_count} winner(s), {loser_count} loser(s) (would roll over).")
            return

        if cmd == "create":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can create entries for users.")
                return
            if len(args) < 3:
                await ctx.send("Usage: !raffle create <user> <count>")
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

        if cmd == "pick":
            if not self.state.is_open:
                await ctx.send("Raffle is not open.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !raffle pick <numbers>")
                return
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

        if cmd == "odds":
            odds = len(self.state.picks)
            await ctx.send(f"Current odds: {odds}/1000 numbers have been picked.")
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

        await ctx.send("placeholder link")

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
        if self.state.is_open and user not in self.state.chat_awarded and not self.state.is_ignored(user):
            if not self.state.first_chatter_awarded:
                bonus = self.state.award_first_chatter(user)
                if bonus > 0:
                    await message.channel.send(
                        f"🎉 Congratulations @{user} for being FIRST in chat after the raffle opened! You receive {bonus} raffle entr{'y' if bonus == 1 else 'ies'}! 🎟️"
                    )
                    return
            count = self.state.award_chat_entry(user)
            if count > 0:
                await message.channel.send(
                    f"@{user} – Here {'is' if count == 1 else 'are'} {count} complimentary entr{'y' if count == 1 else 'ies'}."
                )

def prepare(bot):
    if not bot.get_cog("RaffleCog"):
        bot.add_cog(RaffleCog(bot))