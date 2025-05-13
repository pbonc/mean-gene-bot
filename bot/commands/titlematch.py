import discord
import random
import json
from discord.ext import commands
from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel
from datetime import datetime

TITLEMATCH_COMMAND_VERSION = "v2.0.0a"

TITLE_LIST = [
    "DWF World Heavyweight Title",
    "DWF Intercontinental Title",
    "DWF NDA Title"
]

EMOJI_NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]

class TitleMatchCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.match_context = {}  # message_id: dict with title and challengers

    @commands.command(name="titlematch")
    async def titlematch(self, ctx):
        if ctx.channel.name != "dwf-commissioner":
            return

        embed = discord.Embed(title="🏆 Choose a title to contest", color=discord.Color.gold())
        for i, title in enumerate(TITLE_LIST[:len(EMOJI_NUMBERS)]):
            embed.add_field(name=EMOJI_NUMBERS[i], value=title, inline=False)

        prompt = await ctx.send(embed=embed)

        for i in range(len(TITLE_LIST)):
            await prompt.add_reaction(EMOJI_NUMBERS[i])

        self.match_context[prompt.id] = {
            "step": "select_title",
            "user": ctx.author.id,
            "channel": ctx.channel.id
        }

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        data = self.match_context.get(payload.message_id)
        if not data or payload.user_id != data["user"]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        emoji = str(payload.emoji)

        if data["step"] == "select_title":
            index = EMOJI_NUMBERS.index(emoji) if emoji in EMOJI_NUMBERS else -1
            if index == -1 or index >= len(TITLE_LIST):
                return

            selected_title = TITLE_LIST[index]
            wrestlers = load_wrestlers()

            holder_id = next((uid for uid, d in wrestlers.items()
                              if d.get("current_title") == selected_title), None)

            eligible = [(uid, w["wrestler"]) for uid, w in wrestlers.items() if "wrestler" in w]
            if holder_id:
                champ = wrestlers[holder_id]["wrestler"]
                eligible = [(uid, name) for uid, name in eligible if uid != holder_id]
                challengers = random.sample(eligible, min(8, len(eligible)))

                embed = discord.Embed(
                    title=f"{selected_title}",
                    description=f"🏆 Current Champion: **{champ}**\nChoose a challenger:",
                    color=discord.Color.blue()
                )
                for i, (_, name) in enumerate(challengers):
                    embed.add_field(name=EMOJI_NUMBERS[i], value=name, inline=False)

                followup = await channel.send(embed=embed)
                for i in range(len(challengers)):
                    await followup.add_reaction(EMOJI_NUMBERS[i])

                self.match_context[followup.id] = {
                    "step": "select_challenger",
                    "user": payload.user_id,
                    "title": selected_title,
                    "champion_id": holder_id,
                    "challengers": challengers,
                    "channel": channel.id
                }
            else:
                embed = discord.Embed(
                    title=f"{selected_title}",
                    description="🏷️ This title is currently **vacant**.\nChoose two competitors:",
                    color=discord.Color.dark_grey()
                )
                challengers = random.sample(eligible, min(8, len(eligible)))
                for i, (_, name) in enumerate(challengers):
                    embed.add_field(name=EMOJI_NUMBERS[i], value=name, inline=False)

                followup = await channel.send(embed=embed)
                for i in range(len(challengers)):
                    await followup.add_reaction(EMOJI_NUMBERS[i])

                self.match_context[followup.id] = {
                    "step": "select_two",
                    "user": payload.user_id,
                    "title": selected_title,
                    "champion_id": None,
                    "challengers": challengers,
                    "channel": channel.id,
                    "picked": []
                }

        elif data["step"] == "select_challenger":
            index = EMOJI_NUMBERS.index(emoji)
            challenger_id, challenger_name = data["challengers"][index]
            champ_id = data["champion_id"]

            competitors = [(champ_id, load_wrestlers()[champ_id]["wrestler"]), (challenger_id, challenger_name)]
            await self.confirm_match(channel, data["title"], competitors, payload.message_id)

        elif data["step"] == "select_two":
            index = EMOJI_NUMBERS.index(emoji)
            picked = data["picked"]
            if index >= len(data["challengers"]) or len(picked) >= 2:
                return

            selected = data["challengers"][index]
            if selected[0] not in picked:
                picked.append(selected[0])

            if len(picked) == 2:
                wrestlers = load_wrestlers()
                competitors = [(uid, wrestlers[uid]["wrestler"]) for uid in picked]
                await self.confirm_match(channel, data["title"], competitors, payload.message_id)

        elif data["step"] == "confirm":
            if emoji == "✅":
                await self.resolve_match(channel, data["title"], data["competitors"])
            else:
                await channel.send("❌ Title match cancelled.")
            self.match_context.pop(payload.message_id, None)

    async def confirm_match(self, channel, title, competitors, previous_id):
        embed = discord.Embed(
            title="⚖️ Confirm Title Match",
            description=f"{competitors[0][1]} 🆚 {competitors[1][1]}\nFor the **{title}**",
            color=discord.Color.green()
        )
        confirm = await channel.send(embed=embed)
        await confirm.add_reaction("✅")
        await confirm.add_reaction("❌")

        self.match_context[confirm.id] = {
            "step": "confirm",
            "user": self.match_context[previous_id]["user"],
            "title": title,
            "competitors": competitors,
            "channel": channel.id
        }

    async def resolve_match(self, channel, title, competitors):
        wrestlers = load_wrestlers()
        now = datetime.utcnow().isoformat() + "Z"

        winner_id, winner_name = random.choice(competitors)
        loser = [w for w in competitors if w[0] != winner_id][0]

        for uid, name in competitors:
            record = wrestlers[uid].setdefault("record", {"wins": 0, "losses": 0})
            if uid == winner_id:
                record["wins"] += 1
                wrestlers[uid]["current_title"] = title
                wrestlers[uid].setdefault("title_history", []).append({
                    "title": title, "won": now
                })
            else:
                record["losses"] += 1
                if wrestlers[uid].get("current_title") == title:
                    wrestlers[uid]["current_title"] = None

        save_wrestlers(wrestlers)

        # Broadcast
        backstage = discord.utils.get(channel.guild.text_channels, name="dwf-backstage")
        if backstage:
            await backstage.send(f"📣 Title Match Result: **{winner_name}** defeated **{loser[1]}** for the {title}!")

        twitch_channel = get_twitch_channel()
        if twitch_channel:
            await twitch_channel.send(f"🏆 {title} Match: {competitors[0][1]} vs {competitors[1][1]}")
            await twitch_channel.send(f"👑 **{winner_name}** is now the DWF {title} champion!")

# ✅ Async setup
async def setup(bot):
    await bot.add_cog(TitleMatchCommand(bot))
    print(f"🧩 TitleMatchCommand loaded (version {TITLEMATCH_COMMAND_VERSION})")
