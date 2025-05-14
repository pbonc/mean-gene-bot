import discord
from discord.ext import commands
from datetime import datetime
from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel

TITLE_LIST = [
    "DWF World Heavyweight Title",
    "DWF Intercontinental Title",
    "DWF NDA Title"
]

EMOJI_NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]

class VacateCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vacate_context = {}

    @commands.command(name="vacate")
    async def vacate(self, ctx):
        if not ctx.guild or ctx.channel.name != "dwf-commissioner":
            await ctx.send("❌ You must use this command in #dwf-commissioner.")
            return

        if not (ctx.author.guild_permissions.manage_messages or ctx.author.guild_permissions.administrator):
            await ctx.send("❌ You do not have permission to use this command.")
            return

        wrestlers = load_wrestlers()
        held_titles = []
        champ_lookup = {}

        for uid, data in wrestlers.items():
            title = data.get("current_title")
            if title in TITLE_LIST:
                held_titles.append(title)
                champ_lookup[title] = (uid, data["wrestler"])

        if not held_titles:
            await ctx.send("❌ There are no currently held titles to vacate.")
            return

        embed = discord.Embed(
            title="🏆 Select a Title to Vacate",
            description="React below to select.",
            color=discord.Color.orange()
        )

        for i, title in enumerate(held_titles[:len(EMOJI_NUMBERS)]):
            champ_name = champ_lookup[title][1]
            embed.add_field(name=EMOJI_NUMBERS[i], value=f"{title}\n👑 {champ_name}", inline=False)

        try:
            prompt = await ctx.send(embed=embed)
            for i in range(len(held_titles)):
                await prompt.add_reaction(EMOJI_NUMBERS[i])
        except discord.Forbidden:
            await ctx.send("⚠️ I don't have permission to add reactions in this channel.")
            return

        self.vacate_context[prompt.id] = {
            "step": "select_title",
            "titles": held_titles,
            "champions": champ_lookup,
            "user": ctx.author.id,
            "channel": ctx.channel.id
        }

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        ctx = self.vacate_context.get(payload.message_id)
        if not ctx or payload.user_id != ctx["user"]:
            return

        emoji = str(payload.emoji)
        if ctx["step"] == "select_title":
            if emoji not in EMOJI_NUMBERS:
                return

            index = EMOJI_NUMBERS.index(emoji)
            if index >= len(ctx["titles"]):
                return

            selected_title = ctx["titles"][index]
            champ_id, champ_name = ctx["champions"][selected_title]

            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(ctx["channel"])

            embed = discord.Embed(
                title="⚖️ Confirm Title Vacate",
                description=f"Are you sure you want to vacate the **{selected_title}**, currently held by **{champ_name}**?",
                color=discord.Color.red()
            )

            try:
                confirm = await channel.send(embed=embed)
                await confirm.add_reaction("✅")
                await confirm.add_reaction("❌")
            except discord.Forbidden:
                await channel.send("⚠️ I can't add reactions here. Check my permissions.")
                return

            self.vacate_context[confirm.id] = {
                "step": "confirm",
                "user": payload.user_id,
                "title": selected_title,
                "champ_id": champ_id,
                "champ_name": champ_name,
                "channel": ctx["channel"]
            }

        elif ctx["step"] == "confirm":
            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(ctx["channel"])
            title = ctx["title"]
            champ_id = ctx["champ_id"]
            champ_name = ctx["champ_name"]

            if str(payload.emoji) == "✅":
                wrestlers = load_wrestlers()
                now = datetime.utcnow().isoformat() + "Z"

                if champ_id in wrestlers:
                    wrestlers[champ_id]["current_title"] = None
                    wrestlers[champ_id].setdefault("title_history", []).append({
                        "title": title,
                        "vacated": now
                    })

                    save_wrestlers(wrestlers)

                    backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
                    if backstage:
                        await backstage.send(f"🏳️ The **{title}** has been vacated by **{champ_name}**.")

                    twitch = get_twitch_channel()
                    if twitch:
                        await twitch.send(f"🏳️ DWF Update: {champ_name} has vacated the **{title}**.")

                    await channel.send(f"✅ Title vacated: {title} is now open.")
                else:
                    await channel.send("⚠️ Could not locate wrestler data.")

            else:
                await channel.send("❌ Vacate action cancelled.")

            self.vacate_context.pop(payload.message_id, None)

# ✅ Async setup
async def setup(bot):
    await bot.add_cog(VacateCommand(bot))
    print("🧩 VacateCommand loaded")
