from twitchio.ext import commands

class CommandRouter(commands.Cog):
    def __init__(self, bot, sfx_registry):
        self.bot = bot
        self.sfx_registry = sfx_registry

    # Remove event_message handler. If you want to preserve special routing logic,
    # implement a try_handle_command(self, message) here and call it from MessageRouter.

    # Example stub for future use:
    # async def try_handle_command(self, message):
    #     # [Optional custom command routing logic]
    #     return False

def prepare(bot):
    sfx_registry = getattr(bot, "sfx_registry", None)
    if not bot.get_cog("CommandRouter"):
        bot.add_cog(CommandRouter(bot, sfx_registry))
        print("Loaded cog : CommandRouter")
    else:
        print("CommandRouter already loaded")