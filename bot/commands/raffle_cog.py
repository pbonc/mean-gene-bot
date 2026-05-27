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
        self.giveaway_amount = 0.0  # Track the prize amount for the current giveaway
        # Mystery/Zap feature state
        self.zap_active = False
        self.zap_start_time = None
        self.zap_target_seconds = 0
        self.zap_awarded_user = None
        self.zap_trigger_announced = False  # Has the trigger type been announced yet?
        self.zap_trigger_type = None  # 'chat', 'sfx', 'song', 'gif'
        self.zap_announcement_sent = False  # Has the bot announced what to do?
        self.zap_channel_ref = None  # Reference to send announcement
        self.load()
        if not hasattr(self, 'bad_beat_jackpot'):
            self.bad_beat_jackpot = 25
        if not hasattr(self, 'giveaway_amount'):
            self.giveaway_amount = 0.0

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
            self.giveaway_amount = data.get("giveaway_amount", 0.0)
            self.zap_active = data.get("zap_active", False)
            self.zap_start_time = data.get("zap_start_time", None)
            self.zap_target_seconds = data.get("zap_target_seconds", 0)
            self.zap_awarded_user = data.get("zap_awarded_user", None)
            self.zap_trigger_announced = data.get("zap_trigger_announced", False)
            self.zap_trigger_type = data.get("zap_trigger_type", None)
            self.zap_announcement_sent = data.get("zap_announcement_sent", False)
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
            "giveaway_amount": self.giveaway_amount,
            "zap_active": self.zap_active,
            "zap_start_time": self.zap_start_time,
            "zap_target_seconds": self.zap_target_seconds,
            "zap_awarded_user": self.zap_awarded_user,
            "zap_trigger_announced": self.zap_trigger_announced,
            "zap_trigger_type": self.zap_trigger_type,
            "zap_announcement_sent": self.zap_announcement_sent,
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
        self.giveaway_amount = 0.0  # Reset giveaway amount when clearing raffle
        # Do NOT reset bad_beat_jackpot here (leave as-is)
        self.save()

    def add_entries(self, user, count):
        user = user.lower()
        if user in self.ignored_users:
            return False
        self.entries[user] = self.entries.get(user, 0) + count
        self.save()
        return True

    def get_entry_capacity_remaining(self):
        occupied_numbers = len(self.picks)
        unspent_entries = sum(max(0, int(v)) for v in self.entries.values())
        return max(0, 1000 - occupied_numbers - unspent_entries)

    def add_entries_capped(self, user, count):
        user = user.lower()
        requested = max(0, int(count))
        if user in self.ignored_users:
            return {
                "requested": requested,
                "applied": 0,
                "capacity_before": self.get_entry_capacity_remaining(),
                "truncation_reason": "user_ignored",
            }

        # Intentionally do not cap by board occupancy. This raffle design allows
        # users to hold large entry balances and potentially blot out the board.
        capacity_before = self.get_entry_capacity_remaining()
        applied = requested
        truncation_reason = None

        if applied > 0:
            self.entries[user] = self.entries.get(user, 0) + applied
            self.save()

        return {
            "requested": requested,
            "applied": applied,
            "capacity_before": capacity_before,
            "truncation_reason": truncation_reason,
        }

    def remove_entries(self, user, count):
        user = user.lower()
        if not (isinstance(count, int) and count > 0):
            return False, "Please enter a positive whole number."
        current = self.entries.get(user, 0)
        if current <= 0:
            return False, f"@{user} has no entries to remove."
        removed = min(current, count)
        remaining = current - removed
        if remaining > 0:
            self.entries[user] = remaining
        else:
            self.entries.pop(user, None)
        self.save()
        return True, removed

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
        msg = f"Random picks: {pick_str}"
        # If message exceeds 500 chars, use summary format
        if len(msg) > 500:
            pick_count = len(picks)
            picks_sorted = sorted(picks, key=lambda x: int(x))
            # Show first 3 and last 3 picks
            sample = picks_sorted[:3] + (["..."] if pick_count > 6 else []) + picks_sorted[-3:]
            sample_str = ", ".join(sample)
            msg = f"Random picks: {pick_count} numbers. First/last: {sample_str}"
        return True, msg

    def user_entries(self, user):
        return self.entries.get(user.lower(), 0)

    def user_picks(self, user):
        user = user.lower()
        picks = [num for num, u in self.picks.items() if u == user]
        return sorted(picks, key=lambda x: int(x))

    def set_giveaway_amount(self, amount):
        """Set the giveaway amount for the current raffle"""
        try:
            self.giveaway_amount = float(amount)
            self.save()
            return True
        except (ValueError, TypeError):
            return False

    def get_giveaway_amount(self):
        """Get the current giveaway amount"""
        return self.giveaway_amount

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

    def start_zap(self, minutes):
        """Start a zap mystery instance. Returns (success, message)"""
        if self.zap_active:
            return False, "A ZAP is already active!"
        import time
        self.zap_active = True
        self.zap_start_time = time.time()
        self.zap_target_seconds = minutes * 60
        self.zap_awarded_user = None
        self.zap_trigger_announced = False
        self.zap_trigger_type = None
        self.zap_announcement_sent = False
        self.save()
        return True, f"⚡ ZAP activated! Timer ~{minutes} minute(s). I’ll announce a random trigger; winner gets a FREE raffle entry. This will repeat until !zapstop."

    def stop_zap(self):
        """Stop the active zap. Returns (was_active, message)"""
        if not self.zap_active:
            return False, "No ZAP is currently active."
        self.zap_active = False
        self.zap_start_time = None
        self.zap_target_seconds = 0
        self.zap_awarded_user = None
        self.zap_trigger_announced = False
        self.zap_trigger_type = None
        self.zap_announcement_sent = False
        self.save()
        return True, "⛔ ZAP stopped."

    def _reset_zap_cycle(self):
        """Re-arm the zap for the next cycle without stopping it."""
        if not self.zap_active:
            return
        # Increment start_time by target seconds to keep cycles evenly spaced
        self.zap_start_time = self.zap_start_time + self.zap_target_seconds
        self.zap_awarded_user = None
        self.zap_trigger_announced = False
        self.zap_trigger_type = None
        self.zap_announcement_sent = False
        self.save()

    async def check_and_announce_zap_trigger(self):
        """Check if it's time to announce the trigger. Call this periodically from the cog.
        Returns (should_announce, announcement_message)"""
        import time
        if not self.zap_active or self.zap_trigger_announced:
            return False, None
        
        elapsed = time.time() - self.zap_start_time
        target_time = self.zap_target_seconds
        variation = 180  # ±3 minutes
        min_time = max(0, target_time - variation)
        max_time = target_time + variation
        
        # Check if we're within the announcement window
        if elapsed >= min_time and elapsed <= max_time and not self.zap_announcement_sent:
            # Time to announce! Pick a random trigger
            trigger_types = ['chat', 'sfx', 'song', 'gif']
            self.zap_trigger_type = random.choice(trigger_types)
            self.zap_trigger_announced = True
            self.zap_announcement_sent = True
            self.save()
            
            announcements = {
                'chat': "💬 Next person to chat wins a FREE raffle entry!",
                'sfx': "🔊 Next SFX command wins a FREE raffle entry!",
                'song': "🎵 Next song request (!srx) wins a FREE raffle entry!",
                'gif': "🎬 Next GIF command wins a FREE raffle entry!"
            }
            message = announcements.get(self.zap_trigger_type, "Next action wins!")
            return True, message
        
        return False, None

    def check_zap_and_award(self, user, trigger_type='chat'):
        """Check if zap should award entry to this user. Returns (awarded, message)
        trigger_type: 'chat', 'sfx', 'song', 'gif'
        """
        import time
        if not self.zap_active or self.zap_awarded_user is not None or not self.zap_trigger_announced:
            return False, None
        
        user = user.lower()
        if user in self.ignored_users:
            return False, None
        
        # Check if this trigger type matches what we're waiting for
        if self.zap_trigger_type != trigger_type:
            return False, None
        
        # Mark winner and re-arm for the next cycle. Entry payout is handled by the cog
        # so faction/relic modifiers can be applied exactly once.
        self.zap_awarded_user = user
        self.save()
        self._reset_zap_cycle()
        return True, f"🔥 ZAPPED! @{user} just won a FREE raffle entry! (ZAP continues)"

class RaffleCog(commands.Cog):
    def _award_zap_trigger_entry(self, trigger_user: str):
        faction_cog = self.bot.get_cog("FactionCog")
        if faction_cog and hasattr(faction_cog, "award_entry_reward"):
            return faction_cog.award_entry_reward(
                trigger_user,
                1,
                reward_type="zap_trigger",
            )

        if hasattr(self.state, "add_entries_capped"):
            capped = self.state.add_entries_capped(trigger_user, 1)
            return {
                "applied": int(capped.get("applied", 0)),
                "gmb_applied": False,
                "capacity_reason": capped.get("truncation_reason"),
            }

        ok = self.state.add_entries(trigger_user, 1)
        return {
            "applied": 1 if ok else 0,
            "gmb_applied": False,
            "capacity_reason": None if ok else "entry_grant_failed",
        }

    async def _apply_zap_faction_bonus(self, trigger_user: str, channel):
        faction_cog = self.bot.get_cog("FactionCog")
        if not faction_cog or not hasattr(faction_cog, "service"):
            return

        service = faction_cog.service
        faction = service.add_influence_for_user_faction(trigger_user, influence_amount=1)
        if not faction:
            return

        stream_active_members = service.get_recent_active_members()
        if len(stream_active_members) < 2:
            return

        active_members = service.get_recent_active_members_for_faction(faction.id)
        if len(active_members) < 2:
            return

        candidates = [user for user in active_members if user != trigger_user]
        if not candidates:
            candidates = [trigger_user] if trigger_user in active_members else []
        if not candidates:
            return

        recipient = random.choice(candidates)
        reward_result = None
        if hasattr(faction_cog, "award_entry_reward"):
            reward_result = faction_cog.award_entry_reward(
                recipient,
                1,
                reward_type="zap_faction_echo",
            )

        if not reward_result:
            if hasattr(self.state, "add_entries_capped"):
                capped = self.state.add_entries_capped(recipient, 1)
                reward_result = {
                    "applied": int(capped.get("applied", 0)),
                    "gmb_applied": False,
                }
            else:
                ok = self.state.add_entries(recipient, 1)
                reward_result = {"applied": 1 if ok else 0, "gmb_applied": False}

        if reward_result.get("applied", 0) <= 0:
            return

        flavor = ""
        if reward_result.get("derpdawg_floor_applied"):
            flavor += " 🐾 The Derp relic raised this 1-entry reward to 2 before multipliers."
        if reward_result.get("gmb_applied"):
            flavor += " ⚡ Golden Milkbone resonance doubled the payout."

        await channel.send(
            f"⚡ {faction.name} faction echo: @{recipient} gains +{reward_result['applied']} bonus entries from @{trigger_user}'s zap!{flavor}"
        )

    @commands.command(name="badbeat")
    async def badbeat_command(self, ctx):
        """Show the current bad beat jackpot in chat."""
        jackpot = self.state.bad_beat_jackpot if hasattr(self.state, 'bad_beat_jackpot') else 25
        await ctx.send(f"The current bad beat jackpot is {jackpot} entries!")

    @commands.command(name="zap")
    async def zap_command(self, ctx, *args):
        """Start a zap mystery. Usage: !zap <minutes>"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can use this command.")
            return
        
        if not args:
            await ctx.send("Usage: !zap <minutes>")
            return
        
        try:
            minutes = int(args[0])
            if minutes < 1 or minutes > 60:
                raise ValueError
        except (ValueError, TypeError):
            await ctx.send("Please enter a valid number of minutes (1-60).")
            return
        
        success, message = self.state.start_zap(minutes)
        await ctx.send(message)

    @commands.command(name="zapstop")
    async def zapstop_command(self, ctx):
        """Stop the active zap."""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can use this command.")
            return
        
        was_active, message = self.state.stop_zap()
        await ctx.send(message)

    async def trigger_zap_sfx(self, username, ctx):
        """Called when an SFX command is used. Pass username and ctx for messaging."""
        awarded, message = self.state.check_zap_and_award(username, trigger_type='sfx')
        if awarded and message:
            self._award_zap_trigger_entry(username.lower())
            # Add a small delay to allow the SFX command to appear in chat first
            await asyncio.sleep(0.5)
            await ctx.send(message)
            await self._apply_zap_faction_bonus(username.lower(), ctx)

    async def trigger_zap_song(self, username, ctx):
        """Called when a song request (!srx) is used. Pass username and ctx for messaging."""
        awarded, message = self.state.check_zap_and_award(username, trigger_type='song')
        if awarded and message:
            self._award_zap_trigger_entry(username.lower())
            # Add a small delay to allow the song request to appear in chat first
            await asyncio.sleep(0.5)
            await ctx.send(message)
            await self._apply_zap_faction_bonus(username.lower(), ctx)

    async def trigger_zap_gif(self, username, ctx):
        """Called when a GIF command is used. Pass username and ctx for messaging."""
        awarded, message = self.state.check_zap_and_award(username, trigger_type='gif')
        if awarded and message:
            self._award_zap_trigger_entry(username.lower())
            # Add a small delay to allow the GIF command to appear in chat first
            await asyncio.sleep(0.5)
            await ctx.send(message)
            await self._apply_zap_faction_bonus(username.lower(), ctx)
        
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

        if cmd == "amount":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can set the giveaway amount.")
                return
            if len(args) < 2:
                current_amount = self.state.get_giveaway_amount()
                if current_amount > 0:
                    await ctx.send(f"Current giveaway amount: ${current_amount:.2f}")
                else:
                    await ctx.send("No giveaway amount set. Usage: !raffle amount <dollar_amount>")
                return
            try:
                amount = float(args[1])
                if amount < 0:
                    await ctx.send("Giveaway amount must be positive.")
                    return
                if self.state.set_giveaway_amount(amount):
                    await ctx.send(f"Giveaway amount set to ${amount:.2f}")
                else:
                    await ctx.send("Failed to set giveaway amount.")
            except (ValueError, TypeError):
                await ctx.send("Please enter a valid dollar amount (e.g., 25.00)")
            return

        if cmd == "+":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can increase the giveaway amount.")
                return
            current_amount = self.state.get_giveaway_amount()
            new_amount = current_amount + 1.0
            if self.state.set_giveaway_amount(new_amount):
                await ctx.send(f"Giveaway amount increased by $1! New total: ${new_amount:.2f}")
            else:
                await ctx.send("Failed to increase giveaway amount.")
            return

        if cmd == "set":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can set the giveaway amount.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !raffle set <dollar_amount>")
                return
            try:
                amount = float(args[1])
                if amount < 0:
                    await ctx.send("Giveaway amount must be positive.")
                    return
                if self.state.set_giveaway_amount(amount):
                    await ctx.send(f"Giveaway amount set to ${amount:.2f}")
                else:
                    await ctx.send("Failed to set giveaway amount.")
            except (ValueError, TypeError):
                await ctx.send("Please enter a valid dollar amount (e.g., 5.00)")
            return

        if cmd == "firstnumber":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can set the first dice number.")
                return
            if len(args) < 2:
                await ctx.send("Usage: !raffle firstnumber <0-9>")
                return
            try:
                first_digit = int(args[1])
                if first_digit < 0 or first_digit > 9:
                    raise ValueError
                
                # Broadcast dice roll to overlay
                from bot.overlay_server import broadcast_overlay_message
                await broadcast_overlay_message({
                    "type": "dice_roll",
                    "numbers": [first_digit]
                })
                
                await ctx.send(f"🎲 First number set to: {first_digit}")
                
            except (ValueError, TypeError):
                await ctx.send("Please enter a valid digit (0-9)")
            return

        if cmd == "secondnumber":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can set the second dice number.")
                return
            if len(args) < 3:
                await ctx.send("Usage: !raffle secondnumber <first_digit> <second_digit>")
                return
            try:
                first_digit = int(args[1])
                second_digit = int(args[2])
                if first_digit < 0 or first_digit > 9 or second_digit < 0 or second_digit > 9:
                    raise ValueError
                
                # Broadcast dice roll to overlay
                from bot.overlay_server import broadcast_overlay_message
                await broadcast_overlay_message({
                    "type": "dice_roll", 
                    "numbers": [first_digit, second_digit]
                })
                
                await ctx.send(f"🎲 Numbers set to: {first_digit}{second_digit}_")
                
            except (ValueError, TypeError):
                await ctx.send("Please enter valid digits (0-9)")
            return

        if cmd == "thirdnumber":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can set the third dice number.")
                return
            if len(args) < 4:
                await ctx.send("Usage: !raffle thirdnumber <first_digit> <second_digit> <third_digit>")
                return
            try:
                first_digit = int(args[1])
                second_digit = int(args[2])
                third_digit = int(args[3])
                if any(d < 0 or d > 9 for d in [first_digit, second_digit, third_digit]):
                    raise ValueError
                
                # Broadcast dice roll to overlay
                from bot.overlay_server import broadcast_overlay_message
                await broadcast_overlay_message({
                    "type": "dice_roll",
                    "numbers": [first_digit, second_digit, third_digit]
                })
                
                final_number = f"{first_digit}{second_digit}{third_digit}"
                await ctx.send(f"🎲 Final number: {final_number}")
                
                # Check if it's a winner
                if final_number in self.state.picks:
                    winner = self.state.picks[final_number]
                    await ctx.send(f"🎉 WINNER! {final_number} belongs to @{winner}!")
                else:
                    await ctx.send(f"No winner for {final_number}. The prize rolls over!")
                
            except (ValueError, TypeError):
                await ctx.send("Please enter valid digits (0-9)")
            return

        if cmd == "resetfilter":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can reset the number filter.")
                return
            
            # Broadcast reset to overlay
            from bot.overlay_server import broadcast_overlay_message
            await broadcast_overlay_message({
                "type": "reset_filter"
            })
            
            await ctx.send("🎲 Number filter reset - all numbers visible again")
            return

        if cmd == "testdraw":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can perform test draws.")
                return
            
            # Generate random test dice
            import random
            test_numbers = [random.randint(0, 9) for _ in range(3)]
            
            # Broadcast test draw to overlay
            from bot.overlay_server import broadcast_overlay_message
            await broadcast_overlay_message({
                "type": "dice_roll",
                "numbers": test_numbers,
                "test_mode": True
            })
            
            final_number = f"{test_numbers[0]}{test_numbers[1]}{test_numbers[2]}"
            await ctx.send(f"🎲 TEST DRAW: {final_number}")
            
            # Check if it would be a winner
            if final_number in self.state.picks:
                winner = self.state.picks[final_number]
                await ctx.send(f"🎉 TEST RESULT: {final_number} would be won by @{winner}!")
            else:
                await ctx.send(f"💔 TEST RESULT: {final_number} would have no winner")
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
                    # Reset jackpot only when there are bad beat winners
                    self.state.bad_beat_jackpot = 25
                    self.state.save()
                else:
                    # No bad beats, so increase the jackpot by 10
                    self.state.bad_beat_jackpot += 10
                    no_bad_beat_message = f"There were no bad beats this draw. Bad beat jackpot increased to {self.state.bad_beat_jackpot} entries!"
                    await ctx.send(no_bad_beat_message)
                    await self.send_to_discord(f"💰 {no_bad_beat_message}")
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

        if cmd == "remove":
            if not ctx.author.is_mod:
                await ctx.send("Only mods can remove entries from users.")
                return
            if len(args) < 3:
                await ctx.send("Usage: !raffle remove <user> <count>")
                return
            target = args[1].lstrip("@").lower()
            try:
                n = int(args[2])
            except Exception:
                await ctx.send("Please enter a positive whole number.")
                return
            ok, result = self.state.remove_entries(target, n)
            if not ok:
                await ctx.send(result)
                return
            removed = result
            remaining = self.state.user_entries(target)
            await ctx.send(
                f"Removed {removed} entr{'y' if removed == 1 else 'ies'} from @{target}. "
                f"@{target} now has {remaining} entr{'y' if remaining == 1 else 'ies'}."
            )
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
                if args[1].lower() == "all":
                    n = self.state.user_entries(user)
                    if n < 1:
                        await ctx.send(f"@{user} – You have no entries left.")
                        return
                else:
                    try:
                        n = int(args[1])
                    except Exception:
                        await ctx.send("Usage: !raffle random [amount] or !raffle random all")
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
                full_list = ", ".join(picks)
                msg = f"@{user} – Your picks: {full_list}"
                # If message exceeds 500 chars, use summary format
                if len(msg) > 500:
                    pick_count = len(picks)
                    # Show first 3 and last 3 picks
                    sample = picks[:3] + (["..."] if pick_count > 6 else []) + picks[-3:]
                    sample_str = ", ".join(sample)
                    msg = f"@{user} – You have {pick_count} picks, including: {sample_str}"
                await ctx.send(msg)
            return

        if cmd == "odds":
            odds = len(self.state.picks)
            giveaway_amount = self.state.get_giveaway_amount()
            if giveaway_amount > 0:
                await ctx.send(f"Current odds: {odds}/1000 numbers have been picked. Prize: ${giveaway_amount:.2f}")
            else:
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
        
        # Check for zap announcement timing and trigger awards
        should_announce, announcement = await self.state.check_and_announce_zap_trigger()
        if should_announce and announcement:
            await message.channel.send(announcement)
        
        # Check if this chat message triggers the zap
        awarded, zap_message = self.state.check_zap_and_award(user, trigger_type='chat')
        if awarded and zap_message:
            self._award_zap_trigger_entry(user)
            # Add a small delay to allow the triggering message to appear in chat first
            await asyncio.sleep(0.5)
            await message.channel.send(zap_message)
            await self._apply_zap_faction_bonus(user, message.channel)
        
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