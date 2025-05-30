from twitchio.ext import commands

class MessageRouter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.event()
    async def event_message(self, message):
        print(f"[MessageRouter] event_message received: {message.content} (echo={message.echo})")
        if message.echo:
            return

        handled = False

        overlay_cog = self.bot.get_cog("OverlayCog")
        if overlay_cog:
            if await overlay_cog.try_handle_overlay(message):
                print(f"[MessageRouter] try_handle_overlay({message.content}) -> True")
                handled = True
            else:
                print(f"[MessageRouter] try_handle_overlay({message.content}) -> False")

        sfx_cog = self.bot.get_cog("SFXCog")
        if sfx_cog and not handled:
            if await sfx_cog.try_handle_sfx(message):
                print(f"[MessageRouter] try_handle_sfx({message.content}) -> True")
                handled = True
            else:
                print(f"[MessageRouter] try_handle_sfx({message.content}) -> False")

        raffle_cog = self.bot.get_cog("RaffleCog")
        if raffle_cog and not handled:
            if await raffle_cog.try_handle_raffle(message):
                print(f"[MessageRouter] try_handle_raffle({message.content}) -> True")
                handled = True
            else:
                print(f"[MessageRouter] try_handle_raffle({message.content}) -> False")

        if not handled:
            print(f"[MessageRouter] Passing to handle_commands: {message.content}")
            await self.bot.handle_commands(message)

    # ADD THIS METHOD:
    @commands.Cog.event()
    async def event_command_error(self, ctx, error):
        from twitchio.ext.commands.errors import CommandNotFound
        if isinstance(error, CommandNotFound):
            print(f"[MessageRouter] Suppressed CommandNotFound: {ctx.message.content}")
            return  # Suppress this error!
        # (You may want to handle/log other errors, or re-raise)
        raise error  # Or log, or pass

def prepare(bot):
    if not bot.get_cog("MessageRouter"):
        bot.add_cog(MessageRouter(bot))