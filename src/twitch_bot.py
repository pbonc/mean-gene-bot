import os
import logging
from twitchio.ext import commands
import aiohttp
import asyncio
from dotenv import load_dotenv
import random
from playsound import playsound

from raffle import RaffleState

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot_debug.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")
TWITCH_CHANNELS_RAW = os.getenv("TWITCH_CHANNELS", "yourchannel,iamdar")

if not TWITCH_TOKEN: raise RuntimeError("TWITCH_TOKEN is not set! Check your .env file.")
if not TWITCH_CLIENT_ID: raise RuntimeError("TWITCH_CLIENT_ID is not set! Check your .env file.")
if not TWITCH_CLIENT_SECRET: raise RuntimeError("TWITCH_CLIENT_SECRET is not set! Check your .env file.")
if not TWITCH_CHANNELS_RAW: raise RuntimeError("TWITCH_CHANNELS is not set! Check your .env file.")

TWITCH_CHANNELS = [ch.strip() for ch in TWITCH_CHANNELS_RAW.split(",") if ch.strip()]

raffle_state = RaffleState()

class MeanGeneTwitchBot(commands.Bot):
    def __init__(self, sfx_registry):
        super().__init__(token=TWITCH_TOKEN, prefix="!", initial_channels=TWITCH_CHANNELS)
        self.sfx_registry = sfx_registry
        logger.info(f"Initialized MeanGeneTwitchBot for channels: {TWITCH_CHANNELS}")

    async def event_ready(self):
        logger.info(f"Logged in as | {self.nick}")
        for channel in TWITCH_CHANNELS:
            logger.info(f"Joined channel | {channel}")

    async def event_message(self, message):
        if message.echo:
            return

        # RAFFLE: Award entries on chat if open and not already awarded
        if raffle_state.is_open() and not raffle_state.has_chat_award(message.author.name):
            raffle_state.add_entries(message.author.name, raffle_state.state["entries_per_chat"])
            raffle_state.award_chat(message.author.name)
            count = raffle_state.state["entries_per_chat"]
            await message.channel.send(f"@{message.author.name} – Here are {count} complimentary number{'s' if count > 1 else ''}.")

        if not message.content.startswith("!"):
            await self.handle_commands(message)
            return

        cmd = message.content.split()[0]

        # SFX file command (non-folder: play sound, do NOT send chat message)
        if self.sfx_registry and cmd in self.sfx_registry.file_commands:
            sfx_path = os.path.join("sfx", self.sfx_registry.file_commands[cmd])
            try:
                playsound(sfx_path)
            except Exception as e:
                logger.error(f"Error playing sound: {e}")
            return

        # SFX folder command (random: play sound and send the file command in chat)
        if self.sfx_registry and cmd in self.sfx_registry.folder_commands:
            files = self.sfx_registry.folder_commands[cmd]
            if files:
                sfx_path = os.path.join("sfx", random.choice(files))
                file_cmd = f"!{os.path.splitext(os.path.basename(sfx_path))[0]}"
                try:
                    playsound(sfx_path)
                except Exception as e:
                    logger.error(f"Error playing sound: {e}")
                await message.channel.send(file_cmd)
            return

        # Raffle commands
        if cmd.startswith("!openraffle"):
            await self.cmd_openraffle(message)
            return
        if cmd.startswith("!raffle"):
            await self.cmd_raffle(message)
            return
        if cmd.startswith("!giveentries"):
            await self.cmd_giveentries(message)
            return
        if cmd.startswith("!tradeentries"):
            await self.cmd_tradeentries(message)
            return
        if cmd.startswith("!myentries"):
            count = raffle_state.get_entries(message.author.name)
            await message.channel.send(f"@{message.author.name} – You have {count} number{'s' if count != 1 else ''}.")
            return
        if cmd.startswith("!mypicks"):
            picks = raffle_state.get_user_picks(message.author.name)
            if not picks:
                await message.channel.send(f"@{message.author.name} – You have no picks in the current raffle.")
            else:
                await message.channel.send(f"@{message.author.name} – Your picks: {', '.join(sorted(picks))}")
            return
        if cmd.startswith("!closeraffle"):
            await self.cmd_closeraffle(message)
            return
        if cmd.startswith("!drawraffle"):
            await self.cmd_drawraffle(message)
            return
        if cmd.startswith("!clearraffle"):
            await self.cmd_clearraffle(message)
            return
        if cmd.startswith("!testdraw"):
            await self.cmd_testdraw(message)
            return

        await self.handle_commands(message)

    async def cmd_openraffle(self, message):
        parts = message.content.split()
        is_mod = message.author.is_mod or message.author.is_broadcaster
        if not is_mod:
            await message.channel.send("Only mods can open the raffle.")
            return
        if len(parts) < 2 or not parts[1].isdigit():
            await message.channel.send("Usage: !openraffle X (X = 1-10)")
            return
        x = int(parts[1])
        if not (1 <= x <= 10):
            await message.channel.send("Entries per chat must be between 1 and 10.")
            return
        raffle_state.open_raffle(x)
        await message.channel.send(f"Raffle is now open! Anyone who chats gets {x} free number{'s' if x > 1 else ''}!")

    async def cmd_giveentries(self, message):
        parts = message.content.split()
        is_mod = message.author.is_mod or message.author.is_broadcaster
        if not is_mod:
            await message.channel.send("Only mods can give entries.")
            return
        if len(parts) < 3 or not parts[2].isdigit():
            await message.channel.send("Usage: !giveentries @user X")
            return
        user = parts[1].lstrip('@')
        amount = int(parts[2])
        if not (1 <= amount <= 10):
            await message.channel.send("Can only give 1-10 entries at a time.")
            return
        before = raffle_state.get_entries(user)
        raffle_state.add_entries(user, amount)
        after = raffle_state.get_entries(user)
        await message.channel.send(f"@{user} now has {after} number{'s' if after != 1 else ''}.")

    async def cmd_tradeentries(self, message):
        parts = message.content.split()
        if len(parts) < 3 or not parts[2].isdigit():
            await message.channel.send("Usage: !tradeentries @user X")
            return
        from_user = message.author.name
        to_user = parts[1].lstrip('@')
        amount = int(parts[2])
        if not (1 <= amount <= 10):
            await message.channel.send("Can only trade 1-10 numbers at a time.")
            return
        if raffle_state.get_entries(from_user) < amount:
            await message.channel.send(f"@{from_user} – You do not have enough numbers to trade.")
            return
        raffle_state.remove_entries(from_user, amount)
        raffle_state.add_entries(to_user, amount)
        await message.channel.send(f"@{to_user} received {amount} number{'s' if amount != 1 else ''} from @{from_user}.")

    async def cmd_raffle(self, message):
        parts = message.content.split()
        user = message.author.name
        entries = raffle_state.get_entries(user)
        if len(parts) == 1:
            await message.channel.send("Usage: !raffle XXX or !raffle XXX,YYY or !raffle XXX+ N or !raffle random N")
            return
        if parts[1] == "random":
            count = 1
            if len(parts) > 2 and parts[2].isdigit():
                count = int(parts[2])
            ok, numbers = raffle_state.pick_random_numbers(user, count)
            if not ok:
                await message.channel.send(f"@{user} – Unable to register random numbers. You may not have enough numbers or enough picks left.")
            else:
                left = raffle_state.get_entries(user)
                await message.channel.send(f"@{user} – Registered random numbers: {', '.join(numbers)}. You have {left} number{'s' if left != 1 else ''} left.")
            return

        # Handle batch +/-
        if "+" in parts[1] or "-" in parts[1]:
            base = parts[1].rstrip("+-")
            direction = "+" if "+" in parts[1] else "-"
            try:
                start = int(base)
            except ValueError:
                await message.channel.send("Invalid number format.")
                return
            # If a number is present after, it's the count
            count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else entries
            ok, nums = raffle_state.pick_series(user, start, count, direction)
            if not ok:
                await message.channel.send(f"@{user} – Unable to register sequence. Numbers may be taken or you lack enough numbers.")
            else:
                left = raffle_state.get_entries(user)
                await message.channel.send(f"@{user} – Registered numbers: {', '.join(nums)}. You have {left} number{'s' if left != 1 else ''} left.")
            return

        # Handle comma separated batch
        picks = [n.strip().zfill(3) for n in parts[1].split(",") if n.strip().isdigit() and 0 <= int(n.strip()) <= 999]
        if not picks:
            await message.channel.send("No valid numbers found.")
            return
        ok, result = raffle_state.pick_numbers(user, picks)
        if not ok:
            await message.channel.send(f"@{user} – {result}")
        else:
            left = raffle_state.get_entries(user)
            await message.channel.send(f"@{user} – Registered numbers: {', '.join(result)}. You have {left} number{'s' if left != 1 else ''} left.")

    async def cmd_closeraffle(self, message):
        user = message.author.name
        is_mod = message.author.is_mod or message.author.is_broadcaster
        if not is_mod:
            await message.channel.send("Only mods can close the raffle.")
            return
        if raffle_state.nuclear_attempt("closeraffle", user):
            raffle_state.close_raffle()
            raffle_state.clear_nuclear("closeraffle")
            await message.channel.send("Raffle is now closed!")
        else:
            await message.channel.send(f"{user} has requested to close the raffle. Waiting for second mod confirmation...")

    async def cmd_drawraffle(self, message):
        user = message.author.name
        is_mod = message.author.is_mod or message.author.is_broadcaster
        if not is_mod:
            await message.channel.send("Only mods can draw the raffle.")
            return
        if raffle_state.is_open():
            await message.channel.send("Raffle must be closed before drawing.")
            return
        if raffle_state.nuclear_attempt("drawraffle", user):
            raffle_state.clear_nuclear("drawraffle")
            digits, number, winner = raffle_state.draw()
            await message.channel.send(f"Tonight's first number is... {digits[0]}")
            await asyncio.sleep(1)
            await message.channel.send(f"Tonight's second number is... {digits[1]}")
            await asyncio.sleep(1)
            await message.channel.send(f"Tonight's third number is... {digits[2]}")
            await asyncio.sleep(1)
            if winner:
                await message.channel.send(f"@{winner} is the winner!")
            else:
                await message.channel.send("No winner selected, the prize rolls over!")
        else:
            await message.channel.send(f"{user} has requested to draw the raffle. Waiting for second mod confirmation...")

    async def cmd_clearraffle(self, message):
        user = message.author.name
        is_mod = message.author.is_mod or message.author.is_broadcaster
        if not is_mod:
            await message.channel.send("Only mods can clear the raffle.")
            return
        if raffle_state.nuclear_attempt("clearraffle", user):
            raffle_state.clear_picks()
            raffle_state.clear_nuclear("clearraffle")
            await message.channel.send("Raffle cleared. All picks reset; entries remain.")
        else:
            await message.channel.send(f"{user} has requested to clear the raffle. Waiting for second mod confirmation...")

    async def cmd_testdraw(self, message):
        user = message.author.name
        is_mod = message.author.is_mod or message.author.is_broadcaster
        if not is_mod:
            await message.channel.send("Only mods can use testdraw.")
            return
        number, winner = raffle_state.test_draw()
        if winner:
            await message.channel.send(f"{number} - @{winner}")
        else:
            await message.channel.send(f"{number} - no user")

def run_twitch_bot(sfx_registry):
    logger.info("Starting Twitch bot event loop.")
    asyncio.set_event_loop(asyncio.new_event_loop())
    bot = MeanGeneTwitchBot(sfx_registry=sfx_registry)
    bot.run()