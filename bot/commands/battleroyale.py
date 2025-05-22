import random
import discord
from discord.ext import commands, tasks
from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel
import asyncio  # For concurrent sends

BATTLEROYALE_COMMAND_VERSION = "v1.1.0a"

class BattleRoyaleCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_battle = None  # Stores (message_id, set of user_ids)
        self.timer_started = False

    @commands.command(name="battleroyale")
    async def battleroyale(self, ctx):
        if ctx.channel.name != "dwf-commissioner":
            return

        if self.active_battle:
            await ctx.send("❌ A battle royale is already in progress.")
            return

        wrestlers = load_wrestlers()
        author_id = str(ctx.author.id)
        if author_id not in wrestlers or "wrestler" not in wrestlers[author_id]:
            await ctx.send("❌ You must be a registered wrestler to issue a battle royale.")
            return

        backstage = discord.utils.get(ctx.guild.text_channels, name="dwf-backstage")
        if backstage:
            msg = await backstage.send("💥 A Battle Royale has been declared! React with ✅ to enter the ring!")
            await msg.add_reaction("✅")
            self.active_battle = {
                "message_id": msg.id,
                "participants": set(),
                "guild_id": ctx.guild.id
            }
            self.timer_started = False

        twitch_channel = get_twitch_channel()
        if twitch_channel:
            await twitch_channel.send("⚠️ A battle royale is about to begin! All wrestlers have 2 minutes to check in backstage!")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not self.active_battle:
            return

        if payload.message_id != self.active_battle["message_id"]:
            return

        if str(payload.emoji) != "✅":
            return

        if payload.user_id == self.bot.user.id:
            return

        # Start timer if first real participant
        if not self.timer_started:
            guild = self.bot.get_guild(self.active_battle["guild_id"])
            if guild is None:
                try:
                    guild = await self.bot.fetch_guild(self.active_battle["guild_id"])
                except Exception as e:
                    print(f"⚠️ Failed to fetch guild {self.active_battle['guild_id']}: {e}")
                    return

            backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
            if backstage:
                await backstage.send("⏳ Battle Royale will begin in 2 minutes. Get your reactions in!")

            self.bot.loop.create_task(self.start_battle_after_delay())
            self.timer_started = True

        self.active_battle["participants"].add(str(payload.user_id))

    async def start_battle_after_delay(self):
        await asyncio.sleep(120)  # 2 minutes

        guild = self.bot.get_guild(self.active_battle["guild_id"])
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(self.active_battle["guild_id"])
            except Exception as e:
                print(f"⚠️ Failed to fetch guild {self.active_battle['guild_id']}: {e}")
                self.active_battle = None
                return

        wrestlers = load_wrestlers()
        entrants = []

        for user_id in self.active_battle["participants"]:
            data = wrestlers.get(user_id)
            if data and "wrestler" in data:
                entrants.append((user_id, data["wrestler"]))

        if len(entrants) < 2:
            backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
            if backstage:
                await backstage.send("❌ Not enough participants joined the battle royale.")
            self.active_battle = None
            return

        winner_id, winner_name = random.choice(entrants)

        for uid, data in wrestlers.items():
            if data.get("wrestler") == winner_name:
                data.setdefault("battle_royale_wins", 0)
                data["battle_royale_wins"] += 1

        save_wrestlers(wrestlers)

        twitch_channel = get_twitch_channel()
        if twitch_channel:
            await asyncio.gather(
                twitch_channel.send("💥 The Battle Royale has begun!"),
                twitch_channel.send(f"⚔️ Combatants: {', '.join(name for _, name in entrants)}"),
                twitch_channel.send("🔥 It's absolute chaos in the ring..."),
                twitch_channel.send(f"👑 **{winner_name}** survives and claims victory!")
            )

        backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
        if backstage:
            await backstage.send(f"📊 Battle Royale Result: **{winner_name}** defeated {len(entrants) - 1} others to win!")

        self.active_battle = None

# ✅ Async cog setup
async def setup(bot):
    await bot.add_cog(BattleRoyaleCommand(bot))
    print(f"🧩 BattleRoyaleCommand loaded (version {BATTLEROYALE_COMMAND_VERSION})")
