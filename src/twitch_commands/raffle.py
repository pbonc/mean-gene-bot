import logging
import os
import random
import asyncio
from twitchio.ext import commands

from raffle import RaffleState

logger = logging.getLogger("raffle")

class RaffleCog(commands.Cog):
    def __init__(self, bot, raffle_state, sfx_registry=None):
        self.bot = bot
        self.raffle_state = raffle_state
        self.sfx_registry = sfx_registry

    @commands.Cog.event()
    async def event_ready(self):
        logger.info(f"Logged in as | {self.bot.nick}")
        for channel in getattr(self.bot, 'initial_channels', []):
            logger.info(f"Joined channel | {channel}")

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        # RAFFLE: Award entries on chat if open and not already awarded
        if self.raffle_state.is_open() and not self.raffle_state.has_chat_award(message.author.name):
            self.raffle_state.add_entries(message.author.name, self.raffle_state.state["entries_per_chat"])
            self.raffle_state.award_chat(message.author.name)
            count = self.raffle_state.state["entries_per_chat"]
            await message.channel.send(f"@{message.author.name} – Here are {count} complimentary number{'s' if count > 1 else ''}.")

        if not message.content.startswith("!"):
            await self.bot.handle_commands(message)
            return

        cmd = message.content.split()[0]

        # SFX file command (non-folder: play sound, do NOT send chat message)
        if self.sfx_registry and cmd in getattr(self.sfx_registry, "file_commands", {}):
            sfx_path = os.path.join("sfx", self.sfx_registry.file_commands[cmd])
            try:
                from playsound import playsound
                playsound(sfx_path)
            except Exception as e:
                logger.error(f"Error playing sound: {e}")
            return

        # SFX folder command (random: play sound and send the file command in chat)
        if self.sfx_registry and cmd in getattr(self.sfx_registry, "folder_commands", {}):
            files = self.sfx_registry.folder_commands[cmd]
            if files:
                sfx_path = os.path.join("sfx", random.choice(files))
                file_cmd = f"!{os.path.splitext(os.path.basename(sfx_path))[0]}"
                try:
                    from playsound import playsound
                    playsound(sfx_path)
                except Exception as e:
                    logger.error(f"Error playing sound: {e}")
                await message.channel.send(file_cmd)
            return

        # Let TwitchIO process any regular commands (below)
        await self.bot.handle_commands(message)

    @commands.command(name="openraffle")
    async def openraffle(self, ctx):
        parts = ctx.message.content.split()
        is_mod = ctx.author.is_mod or ctx.author.is_broadcaster
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
        is_mod = ctx.author.is_mod or ctx.author.is_broadcaster
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
            if not ok:
                await ctx.send(f"@{user} – Unable to register random numbers. You may not have enough numbers or enough picks left.")
            else:
                left = self.raffle_state.get_entries(user)
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
            # If a number is present after, it's the count
            count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else entries
            ok, nums = self.raffle_state.pick_series(user, start, count, direction)
            if not ok:
                await ctx.send(f"@{user} – Unable to register sequence. Numbers may be taken or you lack enough numbers.")
            else:
                left = self.raffle_state.get_entries(user)
                await ctx.send(f"@{user} – Registered numbers: {', '.join(nums)}. You have {left} number{'s' if left != 1 else ''} left.")
            return

        # Handle comma separated batch
        picks = [n.strip().zfill(3) for n in parts[1].split(",") if n.strip().isdigit() and 0 <= int(n.strip()) <= 999]
        if not picks:
            await ctx.send("No valid numbers found.")
            return
        ok, result = self.raffle_state.pick_numbers(user, picks)
        if not ok:
            await ctx.send(f"@{user} – {result}")
        else:
            left = self.raffle_state.get_entries(user)
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
        is_mod = ctx.author.is_mod or ctx.author.is_broadcaster
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
        is_mod = ctx.author.is_mod or ctx.author.is_broadcaster
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
        is_mod = ctx.author.is_mod or ctx.author.is_broadcaster
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
        is_mod = ctx.author.is_mod or ctx.author.is_broadcaster
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
    bot.add_cog(RaffleCog(bot, bot._raffle_state, sfx_registry))