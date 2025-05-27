from discord.ext import commands

class Example(commands.Cog):
    """A simple example cog."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="example")
    async def example_command(self, ctx):
        """A basic example command."""
        await ctx.send("Hello from the example cog!")

async def setup(bot):
    await bot.add_cog(Example(bot))
