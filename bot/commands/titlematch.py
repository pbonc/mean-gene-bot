# File: bot/commands/titlematch.py

import discord
import random
from datetime import datetime
from discord.ext import commands
import asyncio

from bot.mgb_dwf import load_wrestlers, save_wrestlers
from bot.state import get_twitch_channel
from bot.utils import safe_get_guild, safe_get_channel

TITLEMATCH_COMMAND_VERSION = "v2.1.0b"

TITLE_LIST = [
    "DWF Christeweight Title",
    "DWF World Heavyweight Title",
    "DWF Intercontinental Title",
    "DWF NDA Title"
]

EMOJI_NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]

class TitleMatchCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.match_context = {}

    @commands.command(name="titlematch")
    async def titlematch(self, ctx):
        if ctx.channel.name != "dwf-commissioner":
            return

        embed = discord.Embed(title="🏆 Choose a title to contest", color=discord.Color.gold())
        for i, title in enumerate(TITLE_LIST[:len(EMOJI_NUMBERS)]):
            embed.add_field(name=EMOJI_NUMBERS[i], value=title, inline=False)

        prompt = await ctx.send(embed=embed)

        tasks = [prompt.add_reaction(EMOJI_NUMBERS[i]) for i in range(len(TITLE_LIST))]
        await asyncio.gather(*tasks)

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

        guild = await safe_get_guild(self.bot, payload.guild_id)
        if not guild:
            return

        channel = await safe_get_channel(self.bot, guild, channel_id=payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        emoji = str(payload.emoji)

        if data["step"] == "select_title":
            if emoji not in EMOJI_NUMBERS:
                return

            index = EMOJI_NUMBERS.index(emoji)
            if index >= len(TITLE_LIST):
                return

            selected_title = TITLE_LIST[index]
            wrestlers = load_wrestlers()

            valid_wrestlers = {uid: d for uid, d in wrestlers.items() if uid.isdigit()}

            holder_id = next(
                (uid for uid, d in valid_wrestlers.items()
                 if (d.get("current_title") or "").strip().lower() == selected_title.strip().lower()),
                None
            )

            eligible = [(uid, w["wrestler"]) for uid, w in valid_wrestlers.items() if "wrestler" in w]

            if holder_id:
                champ = valid_wrestlers[holder_id]["wrestler"]
                challengers = [(uid, name) for uid, name in eligible if uid != holder_id]
                challengers = random.sample(challengers, min(8, len(challengers)))

                embed = discord.Embed(
                    title=f"{selected_title}",
                    description=f"🏆 Current Champion: **{champ}**\nChoose a challenger:",
                    color=discord.Color.blue()
                )
                for i, (_, name) in enumerate(challengers):
                    embed.add_field(name=EMOJI_NUMBERS[i], value=name, inline=False)

                followup = await channel.send(embed=embed)

                tasks = [followup.add_reaction(EMOJI_NUMBERS[i]) for i in range(len(challengers))]
                await asyncio.gather(*tasks)

                self.match_context[followup.id] = {
                    "step": "select_challenger",
                    "user": payload.user_id,
                    "title": selected_title,
                    "champion_id": holder_id,
                    "challengers": challengers,
                    "channel": channel.id
                }

            else:
                challengers = random.sample(eligible, min(8, len(eligible)))
                embed = discord.Embed(
                    title=f"{selected_title}",
                    description="🏷️ This title is currently **vacant**.\nChoose two competitors:",
                    color=discord.Color.dark_grey()
                )
                for i, (_, name) in enumerate(challengers):
                    embed.add_field(name=EMOJI_NUMBERS[i], value=name, inline=False)

                followup = await channel.send(embed=embed)

                tasks = [followup.add_reaction(EMOJI_NUMBERS[i]) for i in range(len(challengers))]
                await asyncio.gather(*tasks)

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
            if emoji not in EMOJI_NUMBERS:
                return
            index = EMOJI_NUMBERS.index(emoji)
            if index >= len(data["challengers"]):
                return

            challenger_id, challenger_name = data["challengers"][index]
            champ_id = data["champion_id"]
            wrestlers = load_wrestlers()
            competitors = [(champ_id, wrestlers[champ_id]["wrestler"]), (challenger_id, challenger_name)]

            await self.confirm_match(channel, data["title"], competitors, payload.message_id)

        elif data["step"] == "select_two":
            if emoji not in EMOJI_NUMBERS:
                return
            index = EMOJI_NUMBERS.index(emoji)
            if index >= len(data["challengers"]):
                return

            picked = data["picked"]
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

        twitch_channel = get_twitch_channel()
        if twitch_channel:
            await twitch_channel.send(f"🏆 {title} Match: {competitors[0][1]} vs {competitors[1][1]}")
            await twitch_channel.send(f"👑 **{winner_name}** is now the DWF {title} champion!")

# ✅ Async setup
async def setup(bot):
    await bot.add_cog(TitleMatchCommand(bot))
    print(f"🧩 TitleMatchCommand loaded (version {TITLEMATCH_COMMAND_VERSION})")
