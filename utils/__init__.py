def safe_get_guild(bot, guild_id):
    """Safely get a guild by ID. Returns None if not found."""
    try:
        return bot.get_guild(guild_id)
    except Exception:
        return None

def safe_get_channel(bot, guild, name=None, channel_id=None):
    """
    Safely get a text channel by name or by ID in a guild.
    Usage:
        safe_get_channel(bot, guild, name="dwf-commissioner")
        safe_get_channel(bot, guild, channel_id=123456789)
    Returns channel or None.
    """
    try:
        if channel_id is not None:
            return bot.get_channel(channel_id)
        if name and guild:
            # Case-insensitive match for safety
            for channel in guild.text_channels:
                if channel.name.lower() == name.lower():
                    return channel
        return None
    except Exception as e:
        print(f"safe_get_channel error: {e}")
        return None