from twitchio.ext import commands

class MessageRouter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        # Always fetch latest cog instances
        overlay_cog = self.bot.get_cog("OverlayCog")
        if overlay_cog and await overlay_cog.try_handle_overlay(message):
            return

        sfx_cog = self.bot.get_cog("SFXCog")
        if sfx_cog and await sfx_cog.try_handle_sfx(message):
            return

        # Add more handlers here as needed

        await self.bot.handle_commands(message)

def prepare(bot):
    if not bot.get_cog("MessageRouter"):
        bot.add_cog(MessageRouter(bot))