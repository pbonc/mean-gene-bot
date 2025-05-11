def setup_events(bot):
    @bot.event
    async def event_ready():
        print(f'✅ Logged in as: {bot.nick}')
        print(f'🛡  Bot Nick: {bot.nick}')
        print(f'🔌 Connected Channels: {bot.connected_channels}')
        for chan in bot.connected_channels:
            print(f'🔗 Joined Twitch channel: {chan.name}')
            await chan.send("Welcome to the main event!")

        import mgb_dwf
        mgb_dwf.set_twitch_channel(bot.connected_channels[0])

        if hasattr(mgb_dwf, "on_ready"):
            print("📡 Triggering Discord on_ready hook...")
            await mgb_dwf.on_ready()

    @bot.event
    async def event_message(message):
        if message.echo or message.author.name.lower() == bot.nick.lower():
            return

        if message.content.startswith("!"):
            parts = message.content.split()
            parts[0] = parts[0].lower()
            message.content = " ".join(parts)

        print(f"[{message.author.name}]: {message.content}")
        await bot.handle_commands(message)
