import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
import threading

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Create Discord client with required intents
intents = discord.Intents.default()
intents.message_content = True
DISCORD_CLIENT = commands.Bot(command_prefix="!", intents=intents)


@DISCORD_CLIENT.event
async def on_ready():
    print(f"✅ Discord bot connected as: {DISCORD_CLIENT.user}")
    for guild in DISCORD_CLIENT.guilds:
        for channel in guild.text_channels:
            if channel.name in [
                "dwf-backstage",
                "dwf-commissioner",
                "dwf-promos",
            ]:
                print(
                    f"✅ Connected to Discord channel: #{channel.name} (ID: {channel.id})"
                )


def load_dwf_commands(bot):
    import random
    from datetime import datetime
    from pathlib import Path
    import json

    # Ensure wrestler file exists with ChatGPT as title holder
    ROSTER_FILE = Path(__file__).parent / "wrestlers.json"
    if not ROSTER_FILE.exists():
        ROSTER_FILE.write_text("{}")

    with ROSTER_FILE.open("r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}

    has_title_holder = any(
        w.get("titles", {}).get("DWF World Heavyweight Title", {}).get("held")
        for w in data.values()
    )

    if not has_title_holder:
        data["0000"] = {
            "wrestler": "ChatGPT",
            "wins": 99,
            "losses": 1,
            "titles": {
                "DWF World Heavyweight Title": {
                    "held": True,
                    "since": datetime.utcnow().isoformat(),
                }
            },
        }
        with ROSTER_FILE.open("w") as f:
            json.dump(data, f, indent=2)

    @DISCORD_CLIENT.command()
    async def match(ctx):
        if ctx.channel.name != "dwf-commissioner":
            await ctx.send(
                "❌ This command can only be used in #dwf-commissioner."
            )
            return

        with ROSTER_FILE.open("r") as f:
            data = json.load(f)

        wrestlers = [w for w in data.values() if "wrestler" in w]
        if len(wrestlers) < 2:
            await ctx.send("❌ Not enough wrestlers to start a match.")
            return

        p1, p2 = random.sample(wrestlers, 2)
        winner = random.choice([p1, p2])
        loser = p2 if winner == p1 else p1

        winner["wins"] = winner.get("wins", 0) + 1
        loser["losses"] = loser.get("losses", 0) + 1

        intro = f"🎬 **{p1['wrestler']}** is stepping into the ring against **{p2['wrestler']}**!"
        outcome = f"💥 The match is underway!"
        result = f"🏆 The winner is... **{winner['wrestler']}**!"

        await ctx.send(intro)
        await ctx.send(outcome)
        await ctx.send(result)

        if "_twitch_channel" in globals() and _twitch_channel:
            await _twitch_channel.send(intro)
            await _twitch_channel.send(outcome)
            await _twitch_channel.send(result)

        with ROSTER_FILE.open("w") as f:
            json.dump(data, f, indent=2)

    @DISCORD_CLIENT.command()
    async def titlematch(ctx):
        if ctx.channel.name != "dwf-commissioner":
            await ctx.send(
                "❌ This command can only be used in #dwf-commissioner."
            )
            return

        with ROSTER_FILE.open("r") as f:
            all_data = json.load(f)

        title_holder = next(
            (
                w
                for w in all_data.values()
                if w.get("titles", {})
                .get("DWF World Heavyweight Title", {})
                .get("held")
            ),
            None,
        )

        if not title_holder:
            await ctx.send("❌ No current title holder found.")
            return

        challengers = [
            w
            for w in all_data.values()
            if w != title_holder and "wrestler" in w
        ]
        if not challengers:
            await ctx.send("❌ No challengers available.")
            return

        challenger = random.choice(challengers)
        winner = random.choice([title_holder, challenger])
        loser = challenger if winner == title_holder else title_holder

        intro = f"👑 **{title_holder['wrestler']}** defends the title against **{challenger['wrestler']}**!"
        outcome = f"⚔️ The title match is underway!"
        result = f"🏆 The winner is... **{winner['wrestler']}**!"

        await ctx.send(intro)
        await ctx.send(outcome)
        await ctx.send(result)

        if "_twitch_channel" in globals() and _twitch_channel:
            await _twitch_channel.send(intro)
            await _twitch_channel.send(outcome)
            await _twitch_channel.send(result)

        winner["wins"] = winner.get("wins", 0) + 1
        loser["losses"] = loser.get("losses", 0) + 1

        if winner != title_holder:
            title_holder["titles"]["DWF World Heavyweight Title"][
                "held"
            ] = False
            winner["titles"] = {
                "DWF World Heavyweight Title": {
                    "held": True,
                    "since": datetime.utcnow().isoformat(),
                }
            }

        with ROSTER_FILE.open("w") as f:
            json.dump(all_data, f, indent=2)

    @DISCORD_CLIENT.command()
    async def rebrand(ctx, *, new_name):
        if ctx.channel.name != "dwf-backstage":
            return

        from pathlib import Path
        import json

        ROSTER_FILE = Path(__file__).parent / "wrestlers.json"
        if not ROSTER_FILE.exists():
            ROSTER_FILE.write_text("{}")

        with ROSTER_FILE.open("r") as f:
            wrestlers = json.load(f)

        user_id = str(ctx.author.id)

        if user_id not in wrestlers or "wrestler" not in wrestlers[user_id]:
            await ctx.send("❌ You don’t have a registered persona to rename.")
            return

        if new_name in [
            w.get("wrestler") for w in wrestlers.values() if "wrestler" in w
        ]:
            await ctx.send("That name is already taken.")
            return

        wrestlers[user_id]["rebrand_pending"] = new_name
        with ROSTER_FILE.open("w") as f:
            json.dump(wrestlers, f, indent=2)

        comm_channel = discord.utils.get(
            ctx.guild.text_channels, name="dwf-commissioner"
        )
        if comm_channel:
            msg = await comm_channel.send(
                f"🔁 `{ctx.author}` requests to rebrand to **{new_name}**. ✅ to approve, ❌ to reject."
            )
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

        response = await ctx.send("Rebrand request submitted for approval.")
        try:
            await ctx.message.delete()
            await response.delete()
            async for msg in ctx.channel.history(limit=50):
                if msg.author == DISCORD_CLIENT.user and (
                    "Registration request" in msg.content
                    or "Rebrand request" in msg.content
                ):
                    await msg.delete()
        except discord.Forbidden:
            print("⚠️ Missing permissions to delete rebrand message.")

    @DISCORD_CLIENT.command()
    async def challenge(ctx, *, target_name=None):
        if ctx.channel.name != "dwf-backstage":
            return

        from pathlib import Path
        import json

        ROSTER_FILE = Path(__file__).parent / "wrestlers.json"
        if not ROSTER_FILE.exists():
            await ctx.send("❌ Roster not found.")
            return

        with ROSTER_FILE.open("r") as f:
            wrestlers = json.load(f)

        user_id = str(ctx.author.id)
        if user_id not in wrestlers or "wrestler" not in wrestlers[user_id]:
            await ctx.send(
                "❌ You must be a registered wrestler to issue a challenge."
            )
            return

        challenger_name = wrestlers[user_id]["wrestler"]

        if target_name:
            target_id = next(
                (
                    uid
                    for uid, w in wrestlers.items()
                    if w.get("wrestler") == target_name
                ),
                None,
            )
            if not target_id:
                await ctx.send("❌ Could not find that wrestler.")
                return
            description = f"⚔️ **{challenger_name}** has challenged **{target_name}**! First to accept with ✅ will face them in the ring!"
        else:
            description = f"⚔️ **{challenger_name}** has issued an open challenge! First wrestler to react with ✅ will face them in the ring!"

        challenge_msg = await ctx.send(description)
        await challenge_msg.add_reaction("✅")

        def check(reaction, user):
            return (
                reaction.message.id == challenge_msg.id
                and str(reaction.emoji) == "✅"
                and user.id != ctx.author.id
                and str(user.id) in wrestlers
                and "wrestler" in wrestlers[str(user.id)]
            )

        try:
            reaction, user = await DISCORD_CLIENT.wait_for(
                "reaction_add", timeout=120.0, check=check
            )
        except asyncio.TimeoutError:
            await ctx.send("⌛ Challenge expired with no takers.")
            return

        opponent = wrestlers[str(user.id)]
        challenger = wrestlers[user_id]

        import random

        winner = random.choice([challenger, opponent])
        loser = opponent if winner == challenger else challenger

        winner["wins"] = winner.get("wins", 0) + 1
        loser["losses"] = loser.get("losses", 0) + 1

        with ROSTER_FILE.open("w") as f:
            json.dump(wrestlers, f, indent=2)

        intro = f"🎯 Challenge accepted: **{challenger['wrestler']}** vs **{opponent['wrestler']}**!"
        action = f"🔥 The match is underway!"
        result = f"🏆 Winner: **{winner['wrestler']}**!"

        await ctx.send(intro)
        await ctx.send(action)
        await ctx.send(result)

        if "_twitch_channel" in globals() and _twitch_channel:
            await _twitch_channel.send(intro)
            await _twitch_channel.send(action)
            await _twitch_channel.send(result)

    @DISCORD_CLIENT.command()
    async def promo(ctx, *, message_text):
        if ctx.channel.name != "dwf-promos":
            return

        from pathlib import Path
        import json

        ROSTER_FILE = Path(__file__).parent / "wrestlers.json"
        if not ROSTER_FILE.exists():
            await ctx.send("❌ Roster not found.")
            return

        with ROSTER_FILE.open("r") as f:
            wrestlers = json.load(f)

        user_id = str(ctx.author.id)
        if user_id not in wrestlers or "wrestler" not in wrestlers[user_id]:
            await ctx.send(
                "❌ You must be a registered wrestler to cut a promo."
            )
            return

        wrestler_name = wrestlers[user_id]["wrestler"]
        comm_channel = discord.utils.get(
            ctx.guild.text_channels, name="dwf-commissioner"
        )
        if comm_channel:
            msg = await comm_channel.send(
                f"""🎤 Promo submitted by **{wrestler_name}**:

        > {message_text}



        ✅ to broadcast, ❌ to discard."""
            )
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            print("⚠️ Missing permissions to delete promo message.")

    @DISCORD_CLIENT.command()
    async def register(ctx, *, wrestler_name):
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send(
                "❌ You must use this command in the #dwf-backstage channel."
            )
            return

        if ctx.channel.name != "dwf-backstage":
            return

        from pathlib import Path
        import json

        ROSTER_FILE = Path(__file__).parent / "wrestlers.json"
        if not ROSTER_FILE.exists():
            ROSTER_FILE.write_text("{}")

        with ROSTER_FILE.open("r") as f:
            wrestlers = json.load(f)

        user_id = str(ctx.author.id)

        if user_id in wrestlers and "wrestler" in wrestlers[user_id]:
            await ctx.send("You’ve already registered a persona.")
            return

        if user_id in wrestlers and "pending" in wrestlers[user_id]:
            await ctx.send("You already have a registration pending approval.")
            return

        if wrestler_name in [
            w.get("wrestler") for w in wrestlers.values() if "wrestler" in w
        ]:
            await ctx.send("That name is already taken.")
            return

        guild = ctx.guild
        comm_channel = discord.utils.get(
            guild.text_channels, name="dwf-commissioner"
        )
        if not comm_channel:
            await ctx.send("Could not locate the commissioner channel.")
            return

        msg = await comm_channel.send(
            f"📝 `{ctx.author}` requests to register as **{wrestler_name}**. ✅ to approve, ❌ to reject."
        )
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        wrestlers[user_id] = {"pending": wrestler_name}
        with ROSTER_FILE.open("w") as f:
            json.dump(wrestlers, f, indent=2)

        response = await ctx.send(
            "Registration request submitted for approval."
        )
        try:
            await ctx.message.delete()
            await response.delete()
        except discord.Forbidden:
            print("⚠️ Missing permissions to delete registration message.")


def set_twitch_channel(channel):
    global _twitch_channel
    _twitch_channel = channel


# Launch Discord bot in its own thread
def run_discord():
    DISCORD_CLIENT.run(TOKEN)


threading.Thread(target=run_discord, daemon=True).start()


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
        print(
            f"✅ Approval received for message ID {payload.message_id} by {user.name}"
        )
        wrestler_name = (
            message.content.split("**")[1]
            if "**" in message.content
            else "Unknown"
        )

        for uid, data in wrestlers.items():
            if data.get("pending") == wrestler_name:
                # Registration approval logic
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

                backstage = discord.utils.get(
                    guild.text_channels, name="dwf-backstage"
                )
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
                        await _twitch_channel.send(announcement)

            elif data.get("rebrand_pending") == wrestler_name:
                data["wrestler"] = wrestler_name
                del data["rebrand_pending"]
                with ROSTER_FILE.open("w") as f:
                    json.dump(wrestlers, f, indent=2)

                approved_user = await DISCORD_CLIENT.fetch_user(int(uid))
                await approved_user.send(
                    f"🔁 Your persona has been rebranded to **{wrestler_name}**!"
                )
                backstage = discord.utils.get(
                    guild.text_channels, name="dwf-backstage"
                )
                if backstage:
                    announcement = f"🔁 **{wrestler_name}** has undergone a dramatic rebranding!"
                    await backstage.send(announcement)
                    if "_twitch_channel" in globals() and _twitch_channel:
                        await _twitch_channel.send(announcement)

                elif message.content.startswith("🎤 Promo submitted by"):
                    parts = message.content.split("**")
                    wrestler_name = parts[1] if len(parts) > 1 else "Unknown"
                    promo_line = message.content.split("")[-1].strip()

                backstage = discord.utils.get(
                    guild.text_channels, name="dwf-backstage"
                )
                if backstage:
                    await backstage.send(
                        f"🎤 **{wrestler_name}** says: {promo_line}"
                    )
                    if "_twitch_channel" in globals() and _twitch_channel:
                        await _twitch_channel.send(
                            f"🎤 {wrestler_name} says: {promo_line}"
                        )

    elif str(payload.emoji) == "❌":
        print(
            f"❌ Rejection received for message ID {payload.message_id} by {user.name}"
        )
        await message.delete()
