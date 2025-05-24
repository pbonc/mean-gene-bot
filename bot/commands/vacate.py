import discord
from discord.ext import commands
from bot.utils.wrestlers import load_wrestlers, save_wrestlers, vacate_title
from bot.utils.twitch import send_twitch_message

TITLE_LIST = [
    "DWF World Heavyweight Title",
    "DWF Intercontinental Title",
    "DWF NDA Title",
    "DWF Christeweight Title"
]

class Vacate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="vacate")
    async def vacate(self, ctx, *, selected_title: str = None):
        """Vacates a wrestling title."""
        wrestlers = load_wrestlers()

        # Validate selected_title
        if not selected_title or selected_title not in TITLE_LIST:
            await ctx.send(f"❌ Please specify a valid title: {', '.join(TITLE_LIST)}")
            return

        # Find current champion for this title
        holder_id = next(
            (
                uid for uid, d in wrestlers.items()
                if (d.get("current_title") or "").strip().lower() == selected_title.strip().lower()
            ),
            None
        )

        if holder_id:
            champ = wrestlers[holder_id]["wrestler"]
            vacate_title(wrestlers, selected_title)
            save_wrestlers(wrestlers)
            msg = f"⚠️ The {selected_title} has been vacated! {champ} is no longer champion."
            await ctx.send(msg)
            send_twitch_message(msg)
        else:
            await ctx.send(f"❌ The {selected_title} is already vacant.")

async def setup(bot):
    await bot.add_cog(Vacate(bot))