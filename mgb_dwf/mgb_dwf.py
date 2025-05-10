@DISCORD_CLIENT.event
async def on_raw_reaction_add(payload):
    if payload.user_id == DISCORD_CLIENT.user.id:
        return

    if payload.event_type != "REACTION_ADD":
        return

    guild = DISCORD_CLIENT.get_guild(payload.guild_id)
    if not guild:
        return

    channel = guild.get_channel(payload.channel_id)
    if not channel or channel.name != "dwf-commissioner":
        return

    message = await channel.fetch_message(payload.message_id)
    user = await DISCORD_CLIENT.fetch_user(payload.user_id)

    from pathlib import Path
    import json
    import random

    ROSTER_FILE = Path(__file__).parent / "wrestlers.json"
    if not ROSTER_FILE.exists():
        return

    with ROSTER_FILE.open("r") as f:
        wrestlers = json.load(f)

    if str(payload.emoji) == "✅":
        print(f"✅ Approval received for message ID {payload.message_id} by {user.name}")

        wrestler_name = (
            message.content.split("**")[1]
            if "**" in message.content
            else "Unknown"
        )

        for uid, data in wrestlers.items():
            if data.get("pending") == wrestler_name:
                # Registration approval
                wrestlers[uid] = {
                    "wrestler": wrestler_name,
                    "wins": 0,
                    "losses": 0,
                    "titles": {
                        "DWF World Heavyweight Title": {
                            "held": False,
                            "since": None,
                        }
                    },
                }
                with ROSTER_FILE.open("w") as f:
                    json.dump(wrestlers, f, indent=2)

                approved_user = await DISCORD_CLIENT.fetch_user(int(uid))
                await approved_user.send(
                    f"✅ Your persona, {wrestler_name}, has been approved! Welcome to the DWF!"
                )

                backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
                if backstage:
                    announcements = [
                        "📣 BREAKING: **{wrestler_name}** has officially signed a new contract with the DWF!",
                        "📝 **{wrestler_name}** has joined the DWF roster! Big things coming!",
                        "🔥 Rumor confirmed: **{wrestler_name}** is all in with the DWF!",
                        "🚨 **{wrestler_name}** inks a deal with the DWF! Welcome aboard!",
                    ]
                    announcement = random.choice(announcements).format(
                        wrestler_name=wrestler_name
                    )
                    await backstage.send(announcement)
                    if "_twitch_channel" in globals() and _twitch_channel:
                        await _twitch_ch
