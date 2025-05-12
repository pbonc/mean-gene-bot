import discord
from discord.ext import commands
from bot.mgb_dwf import announce_new_wrestler
from bot.utils.wrestlers import load_wrestlers, save_wrestlers

class RegisterCommand(commands.Cog):
    @staticmethod
    def clear_pending_registrations():
        wrestlers = load_wrestlers()
        original_count = len(wrestlers)
        filtered = {uid: data for uid, data in wrestlers.items() if "pending" not in data}
        save_wrestlers(filtered)
        print(f"🧹 Cleared pending registrations. {original_count - len(filtered)} removed.")

    def __init__(self, bot):
        RegisterCommand.clear_pending_registrations()
        self.bot = bot
        self.pending_messages = {}  # message_id: (user_id, wrestler_name)

    @commands.command(name="register")
    async def register(self, ctx, *, wrestler_name):
        print("\n💬 !register command received")

        if isinstance(ctx.channel, discord.DMChannel):
            print("⛔ Command used in DM.")
            await ctx.send("❌ You must use this command in the #dwf-backstage channel.")
            return

        print(f"📺 Channel: {ctx.channel.name}")
        if ctx.channel.name != "dwf-backstage":
            print("⛔ Command used in wrong channel.")
            return

        try:
            wrestlers = load_wrestlers()
            user_id = str(ctx.author.id)
            print(f"👤 User ID: {user_id} | Wrestler Name: {wrestler_name}")
        except Exception as e:
            print(f"❌ Crash during wrestler load or ID parsing: {e}")
            await ctx.send("⚠️ Unexpected error during registration. Please report this.")
            return

        if user_id in wrestlers:
            if "wrestler" in wrestlers[user_id]:
                print("⛔ User already registered.")
                await ctx.send("You’ve already registered a persona.")
                return
            if "pending" in wrestlers[user_id]:
                print("⛔ User already has a pending registration.")
                await ctx.send("You already have a registration pending approval.")
                return

        existing_names = [w.get("wrestler") for w in wrestlers.values() if "wrestler" in w]
        print(f"📋 Existing names: {existing_names}")
        if wrestler_name in existing_names:
            print("⛔ Wrestler name is already taken.")
            await ctx.send("That name is already taken.")
            return

        print("🔎 Available text channels before lookup:")
        assert ctx.guild is not None, "❌ ctx.guild is None — command context is broken or bot not in guild"
        for channel in ctx.guild.text_channels:
            print(f"  - #{channel.name}")

        comm_channel = discord.utils.get(ctx.guild.text_channels, name="dwf-commissioner")
        print(f"🔍 Channel lookup result: {comm_channel}")
        if not comm_channel:
            print("⛔ Could not locate #dwf-commissioner.")
            await ctx.send("❌ Could not locate the commissioner channel.")
            return

        try:
            print(f"📤 Sending approval request to #{comm_channel.name}")
            msg = await comm_channel.send(
                f"📝 `{ctx.author}` requests to register as **{wrestler_name}**. ✅ to approve, ❌ to reject."
            )
            self.pending_messages[msg.id] = (user_id, wrestler_name)
            print(f"🕓 Pending message tracked immediately: {msg.id} -> {wrestler_name}")
            wrestlers[user_id] = {"pending": wrestler_name}
            save_wrestlers(wrestlers)
            print("💾 Wrestler data saved.")
            print(f"✅ Message sent to commissioner (ID: {msg.id})")
            
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            print("✅ Reactions added.")
        except Exception as e:
            print(f"❌ FAILED TO SEND OR REACT: {e}")
            await ctx.send("❌ Registration failed to post to the commissioner channel.")
            return

        

        

        try:
            response = await ctx.send("✅ Registration request submitted for approval.")
            await ctx.message.delete()
            await response.delete()
        except discord.Forbidden:
            print("⚠️ Missing permissions to delete registration message.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            print("⛔ Ignoring bot's own reaction")
            return
        print(f"🔍 Reaction received: {payload.emoji} by {payload.user_id} on message {payload.message_id}")

        
        if str(payload.emoji) not in {"✅", "❌"}:
            print("⛔ Irrelevant emoji")
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            print("⛔ Guild not found")
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.NotFound:
                print("⛔ Could not fetch member")
                return

        if not (member.guild_permissions.manage_messages or member.guild_permissions.administrator):
            print("⛔ Member lacks permissions")
            return

        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        print(f"📄 Commissioner message content: {message.content}")

        wrestlers = load_wrestlers()
        user_id = None
        wrestler_name = None

        for uid, data in wrestlers.items():
            if "pending" in data:
                if f"**{data['pending']}**" in message.content:
                    user_id = str(uid)
                    wrestler_name = data["pending"]
                    break

        if not user_id:
            print("⛔ Could not find pending wrestler in JSON for this message")
            return

        
        if str(payload.emoji) == "✅":
            if user_id in wrestlers:
                wrestlers[str(user_id)]["wrestler"] = wrestler_name
                wrestlers[str(user_id)].pop("pending", None)
            await message.reply(f"✅ {wrestler_name} has been approved!")
            announce_new_wrestler(wrestler_name)
        else:
            await message.reply(f"❌ {wrestler_name} was rejected.")
            wrestlers.pop(user_id, None)

        save_wrestlers(wrestlers)
        print(f"💾 Wrestler update saved after reaction: {wrestler_name}")

# ✅ Async cog setup for dynamic load
async def setup(bot):
    cog = RegisterCommand(bot)
    await bot.add_cog(cog)
