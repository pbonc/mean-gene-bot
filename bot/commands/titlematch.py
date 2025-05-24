import discord
from discord.ext import commands
from bot.utils.wrestlers import load_wrestlers, save_wrestlers, set_new_champion
from bot.state import get_twitch_channel
import random
import asyncio

EMOJI_NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
EMOJI_NEXT = "➡️"
EMOJI_ABORT = "❌"
TITLE_LIST = [
    "DWF World Heavyweight Title",
    "DWF Intercontinental Title",
    "DWF NDA Title",
    "DWF Christeweight Title"
]

TITLEMATCH_COMMAND_VERSION = "v1.1.0a"

class TitleMatch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}
        self.titlematch_ticker = []  # Keeps session ticker messages

    @commands.command(name="titlematch")
    async def titlematch(self, ctx):
        if ctx.channel.name != "dwf-commissioner":
            await ctx.send("🚫 This command can only be used in #dwf-commissioner.")
            return

        embed = discord.Embed(
            title="Select a Title",
            description="\n".join(f"{EMOJI_NUMBERS[i]} {title}" for i, title in enumerate(TITLE_LIST)),
            color=discord.Color.gold()
        )
        msg = await ctx.send(embed=embed)
        for i in range(len(TITLE_LIST)):
            await msg.add_reaction(EMOJI_NUMBERS[i])
        await msg.add_reaction(EMOJI_ABORT)

        self.active_sessions[msg.id] = {
            "step": "title_select",
            "user_id": ctx.author.id,
            "message_id": msg.id,
            "channel_id": ctx.channel.id
        }

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        data = self.active_sessions.get(payload.message_id)
        if not data or payload.user_id != data["user_id"]:
            return

        emoji = str(payload.emoji)
        channel = self.bot.get_channel(data["channel_id"])
        if not channel:
            return

        if emoji == EMOJI_ABORT:
            await channel.send("❌ Title match process aborted.")
            del self.active_sessions[payload.message_id]
            return

        if data["step"] == "title_select":
            if emoji not in EMOJI_NUMBERS:
                return
            title_idx = EMOJI_NUMBERS.index(emoji)
            title = TITLE_LIST[title_idx]
            data["title"] = title

            wrestlers = load_wrestlers()
            wrestler_entries = {uid: d for uid, d in wrestlers.items() if uid.isdigit()}

            holder_id = next(
                (
                    uid for uid, d in wrestler_entries.items()
                    if (d.get("current_title") or "").strip().lower() == title.strip().lower()
                ),
                None
            )
            data["champion_id"] = holder_id
            data["challenger_page"] = 0

            eligible = [(uid, w["wrestler"]) for uid, w in wrestler_entries.items() if "wrestler" in w]
            data["eligible"] = eligible

            await self.send_challenger_menu(channel, data, reset_picks=True)

        elif data["step"] == "challenger_select":
            paged_challengers = data["paged_challengers"]
            picks = data.setdefault("picked", [])

            if str(payload.emoji) == EMOJI_NEXT:
                await self.send_challenger_menu(channel, data, reset_picks=False, next_page=True)
                return

            if str(payload.emoji) not in EMOJI_NUMBERS:
                return
            idx = EMOJI_NUMBERS.index(str(payload.emoji))
            if idx >= len(paged_challengers):
                return

            selected = paged_challengers[idx]
            if selected[0] in picks:
                return

            picks.append(selected[0])
            need_picks = 2 if data["champion_id"] is None else 1
            if len(picks) < need_picks:
                await self.send_challenger_menu(channel, data, reset_picks=False)
            else:
                wrestlers = load_wrestlers()
                wrestler_entries = {uid: d for uid, d in wrestlers.items() if uid.isdigit()}
                competitors = []
                if data["champion_id"]:
                    competitors.append((data["champion_id"], wrestler_entries[data["champion_id"]]["wrestler"]))
                competitors += [(uid, wrestler_entries[uid]["wrestler"]) for uid in picks]
                winner_id, winner_name = random.choice(competitors)
                title = data["title"]

                # Update champion in data
                set_new_champion(wrestlers, title, winner_name)
                save_wrestlers(wrestlers)

                # Announce results
                competitors_names = [name for _, name in competitors]
                result_msg = f"Match for **{title}**!\nCompetitors: {', '.join(competitors_names)}\n\n🏆 **{winner_name}** is the NEW {title} Champion!"

                await channel.send(result_msg)

                # --- Twitch Broadcast (like challenge command) ---
                twitch_channel = get_twitch_channel()
                if twitch_channel:
                    await asyncio.gather(
                        twitch_channel.send(f"🔥 Title match for {title}!"),
                        twitch_channel.send(f"🤼 Competitors: {', '.join(competitors_names)}"),
                        twitch_channel.send(f"🏆 {winner_name} is the NEW {title} Champion!")
                    )

                # --- Ticker Integration ---
                self.titlematch_ticker.append(f"{winner_name} is the NEW {title} Champion!")
                # Optionally: print for debug
                print("Ticker now:", self.titlematch_ticker)

                del self.active_sessions[payload.message_id]

    async def send_challenger_menu(self, channel, data, reset_picks=True, next_page=False):
        eligible = data["eligible"]
        picks = [] if reset_picks else data.get("picked", [])
        per_page = 8

        champ_id = data["champion_id"]
        pool = [w for w in eligible if w[0] != champ_id] if champ_id else eligible

        total = len(pool)
        max_pages = (total - 1) // per_page + 1 if total > 0 else 1
        page = data.get("challenger_page", 0)
        if next_page:
            page = (page + 1) % max_pages

        start = page * per_page
        end = start + per_page
        paged = pool[start:end]
        data["challenger_page"] = page
        data["paged_challengers"] = paged
        data["step"] = "challenger_select"
        data["picked"] = picks

        title = data["title"]

        champ = None
        if champ_id:
            wrestlers = load_wrestlers()
            wrestler_entries = {uid: d for uid, d in wrestlers.items() if uid.isdigit()}
            champ = wrestler_entries.get(champ_id, {}).get("wrestler", None)
            desc = f"🏆 Current Champion: **{champ}**\nPick a challenger:"
        else:
            desc = "🏷️ This title is **vacant**.\nPick two competitors:"

        for uid in picks:
            picked_name = next((name for u, name in eligible if u == uid), None)
            if picked_name:
                desc += f"\n✅ Picked: {picked_name}"

        embed = discord.Embed(
            title=f"{title} — Challenger Selection (Page {page+1}/{max_pages})",
            description=desc,
            color=discord.Color.blue()
        )
        for i, (_, name) in enumerate(paged):
            embed.add_field(name=EMOJI_NUMBERS[i], value=name, inline=False)
        if total > per_page:
            embed.add_field(name=EMOJI_NEXT, value="Show more", inline=False)
        embed.set_footer(text="React ❌ to abort.")
        msg = await channel.send(embed=embed)
        for i in range(len(paged)):
            await msg.add_reaction(EMOJI_NUMBERS[i])
        if total > per_page:
            await msg.add_reaction(EMOJI_NEXT)
        await msg.add_reaction(EMOJI_ABORT)

        self.active_sessions[msg.id] = data

    # --- Ticker Export Method (optional) ---
    def get_titlematch_ticker(self):
        return self.titlematch_ticker

# ✅ Async cog setup
async def setup(bot):
    await bot.add_cog(TitleMatch(bot))
    print(f"🧩 TitleMatch loaded (version {TITLEMATCH_COMMAND_VERSION})")