import random
import asyncio
from twitchio.ext import commands
from bot.raffle_manager import RaffleManager

raffle = RaffleManager("bot/data/raffle_state.json")

class RaffleCommands(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending_draw_confirmations = set()
        self.pending_clear_confirmations = set()

    @commands.command(name="openraffle")
    async def open_raffle(self, ctx: commands.Context):
        if not ctx.author.is_mod:
            return
        parts = ctx.message.content.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await ctx.send("⚠️ Usage: !openraffle <entry_count>")
            return
        entry_count = int(parts[1])
        raffle_id = f"{ctx.message.timestamp.strftime('%Y%m%d')}_raffle"
        raffle.open_raffle(entry_count, raffle_id)
        raffle.state["raffle_locked"] = False
        raffle.save()
        await ctx.send(f"🎉 Raffle opened! Everyone who chats gets {entry_count} entry(ies)!")

    @commands.command(name="enterraffle")
    async def enter_raffle(self, ctx: commands.Context):
        if raffle.state.get("raffle_locked", False):
            await ctx.send("🔒 The raffle is closed. No new entries allowed.")
            return

        args = ctx.message.content.strip().split(maxsplit=1)
        if len(args) < 2:
            await ctx.send("⚠️ Usage: !enterraffle <number(s)|random [N]>")
            return

        user = ctx.author.name.lower()
        raffle.grant_daily_entry(user)
        subcommand = args[1].lower()

        if subcommand.startswith("random"):
            parts = subcommand.split()
            count = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
            available = raffle.available_entries(user)
            if count > available:
                await ctx.send(f"⛔ You only have {available} entries.")
                return
            numbers = []
            while len(numbers) < count:
                num = str(random.randint(0, 999)).zfill(3)
                if num not in raffle.state["number_to_user"]:
                    numbers.append(num)
            raffle.redeem_entries(user, numbers)
            await ctx.send(f"✅ {user} entered: {', '.join(numbers)}")
            return
        # Manual number entry (must be 3 digits, no duplicates)
        requested_raw = [n.strip() for n in subcommand.split(",")]

        # Normalize and dedupe
        requested = []
        seen = set()
        for num in requested_raw:
            if not num.isdigit() or len(num) != 3 or num != num.zfill(3):
                await ctx.send("⛔ All numbers must be exactly 3 digits with leading zeros (e.g. 007).")
                return
            if num in seen:
                await ctx.send("⛔ Duplicate entry detected. Error Code: Caerdwyn 1")
                return
            seen.add(num)
            requested.append(num)

        if len(requested) > raffle.available_entries(user):
            await ctx.send(f"⛔ You only have {raffle.available_entries(user)} entries.")
            return

        already_taken = [num for num in requested if num in raffle.state["number_to_user"]]
        if already_taken:
            formatted = ", ".join(already_taken)
            await ctx.send(f"⛔ The following number(s) are already taken: ({formatted})")
            return

        raffle.redeem_entries(user, requested)
        await ctx.send(f"✅ {user} entered: {', '.join(requested)}")


    @commands.command(name="drawraffle")
    async def draw_raffle(self, ctx: commands.Context):
        if not ctx.author.is_mod:
            return

        if raffle.state.get("raffle_locked", False) is False:
            await ctx.send("⚠️ You must close the raffle before drawing a winner! Use !closeraffle 5")
            return

        user = ctx.author.name.lower()
        self.pending_draw_confirmations.add(user)

        if len(self.pending_draw_confirmations) < 2:
            await ctx.send(f"🟡 {user} confirmed draw. One more mod confirmation needed...")
            return

        self.pending_draw_confirmations.clear()

        num = str(random.randint(0, 999)).zfill(3)
        winner = raffle.state["number_to_user"].get(num)

        await ctx.send("🎰 Preparing to draw the winning number...")
        await asyncio.sleep(3)
        await ctx.send(f"🎰 The first number is... {num[0]}")
        await asyncio.sleep(10)
        await ctx.send(f"🎰 The second number is... {num[1]}")
        await asyncio.sleep(10)
        await ctx.send(f"🎰 The final number is... {num[2]}")
        await asyncio.sleep(3)

        if winner:
            await ctx.send(f"🎉 The winner is @{winner} with number {num}!")
            raffle.state["entries"] = {}
            raffle.state["number_to_user"] = {}
            raffle.state["persistent_grants"] = {}
            raffle.save()
        else:
            await ctx.send(f"😢 No one had {num}. The prize rolls over!")

    @commands.command(name="closeraffle")
    async def close_raffle(self, ctx: commands.Context):
        if not ctx.author.is_mod:
            return

        args = ctx.message.content.strip().split()
        try:
            minutes = int(args[1]) if len(args) > 1 else 10
        except ValueError:
            minutes = 10

        if minutes > 10:
            minutes = 10
        elif minutes < 1:
            minutes = 1

        await ctx.send(f"⏳ Raffle will close in {minutes} minute(s)! Get your entries in!")

        total_seconds = minutes * 60
        warn_times = [300, 60, 30]
        for t in warn_times:
            if t < total_seconds:
                await asyncio.sleep(total_seconds - t)
                await ctx.send(f"⏳ Raffle closes in {t // 60 if t >= 60 else t} {'minute(s)' if t >= 60 else 'seconds'}!")

        await asyncio.sleep(total_seconds - sum(s for s in warn_times if s < total_seconds))
        raffle.state["raffle_locked"] = True
        raffle.state["raffle_active"] = False
        raffle.save()
        await ctx.send("🔒 Raffle is now closed! No new entries will be accepted.")

    @commands.command(name="giveraffle")
    async def give_raffle(self, ctx: commands.Context):
        if not ctx.author.is_mod:
            return
        parts = ctx.message.content.split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].startswith("@"):
            await ctx.send("⚠️ Usage: !giveraffle <count> @username")
            return
        count = int(parts[1])
        target = parts[2].lstrip("@").lower()
        raffle.grant_persistent_entries(target, count)
        await ctx.send(f"🎁 {target} has been granted {count} persistent entry(ies).")

    @commands.command(name="clearrafflesheet")
    async def clear_raffle_sheet(self, ctx: commands.Context):
        if not ctx.author.is_mod:
            return
        user = ctx.author.name.lower()
        self.pending_clear_confirmations.add(user)

        if len(self.pending_clear_confirmations) < 2:
            await ctx.send(f"🟠 {user} confirmed clear. One more mod confirmation needed...")
            return

        self.pending_clear_confirmations.clear()
        raffle.state["entries"] = {}
        raffle.state["number_to_user"] = {}
        raffle.state["persistent_grants"] = {}
        raffle.save()
        await ctx.send("🧹 Raffle sheet has been cleared. All entries and grants wiped.")

def prepare(bot: commands.Bot):
    bot.add_cog(RaffleCommands(bot))
