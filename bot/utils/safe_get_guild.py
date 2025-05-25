async def safe_get_guild(bot, guild_id):
    """
    Safely gets a guild (server) by ID from the bot's connected guilds.
    Returns None if not found.
    """
    return bot.get_guild(guild_id)