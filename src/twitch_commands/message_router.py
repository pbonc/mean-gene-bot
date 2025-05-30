from twitchio.ext import commands

class MessageRouter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.event()
    async def event_message(self, message):
        print(f"[MessageRouter] event_message received: {message.content} (echo={message.echo})")
        if message.echo:
            return

        overlay_cog = self.bot.get_cog("OverlayCog")
        if overlay_cog:
            handled = await overlay_cog.try_handle_overlay(message)
            print(f"[MessageRouter] try_handle_overlay({message.content}) -> {handled}")
            if handled:
                return

        sfx_cog = self.bot.get_cog("SFXCog")
        if sfx_cog:
            handled = await sfx_cog.try_handle_sfx(message)
            print(f"[MessageRouter] try_handle_sfx({message.content}) -> {handled}")
            if handled:
                return

        raffle_cog = self.bot.get_cog("RaffleCog")
        if raffle_cog:
            handled = await raffle_cog.try_handle_raffle(message)
            print(f"[MessageRouter] try_handle_raffle({message.content}) -> {handled}")
            if handled:
                return

        # Only call commands if message was not handled by overlay/sfx/raffle etc.
        print(f"[MessageRouter] Passing to handle_commands: {message.content}")
        await self.bot.handle_commands(message)

def prepare(bot):
    if not bot.get_cog("MessageRouter"):
        bot.add_cog(MessageRouter(bot))