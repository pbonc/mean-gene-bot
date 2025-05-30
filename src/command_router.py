from twitchio.ext import commands

class CommandRouter(commands.Cog):
    def __init__(self, bot, sfx_registry):
        self.bot = bot
        self.sfx_registry = sfx_registry

    @commands.Cog.event()
    async def event_message(self, message):
        # Only process user messages, not echoes or bot responses
        if message.echo:
            return
        if message.author and message.author.name.lower() == self.bot.nick.lower():
            return
        if message.tags.get('handled_by_sfx'):
            return
        if message.tags.get('handled_by_overlay'):  # <- Prevent double handling for overlay!
            return
        if not message.content.startswith("!"):
            return

        print(f"[DEBUG] CommandRouter.handle_commands called for: {message.content} by {message.author.name}")
        await self.bot.handle_commands(message)

def prepare(bot):
    sfx_registry = getattr(bot, "sfx_registry", None)
    if not bot.get_cog("CommandRouter"):
        bot.add_cog(CommandRouter(bot, sfx_registry))
        print("Loaded cog : CommandRouter")
    else:
        print("CommandRouter already loaded")