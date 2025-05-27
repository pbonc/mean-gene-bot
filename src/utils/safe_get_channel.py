import discord

async def safe_get_channel(bot, guild, name=None, channel_id=None):
    """
    Safely gets a text channel by name or ID from a guild.
    Returns None if not found.
    """
    # Fetch by channel_id if provided
    if channel_id is not None:
        channel = guild.get_channel(channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            return channel
        # fallback for compatibility
        for ch in guild.channels:
            if ch.id == channel_id and isinstance(ch, discord.TextChannel):
                return ch
        return None

    # Fetch by name if provided
    if name is not None:
        # Try case-insensitive match among text channels
        for channel in guild.text_channels:
            if channel.name.lower() == name.lower():
                return channel
        # fallback: try all channels
        for channel in guild.channels:
            if getattr(channel, "name", None) and channel.name.lower() == name.lower():
                return channel
    return None