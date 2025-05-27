import asyncio
from twitchio.ext import commands
from bot.config import TWITCH_TOKEN, CHANNEL, BOT_NICK
from bot.version import BOT_VERSION
from bot.loader import load_all, is_valid_command_name, log_skip
from bot import mgb_dwf
from bot.state import set_twitch_channel
from bot.tasks.sfx_watcher import SFXWatcher

from bot.battleship import BattleshipGame
from bot.raffle_manager import RaffleManager

class MeanGeneBot(commands.Bot):
    def __init__(self, sfx_debug=False, verbose=False):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix="!",
            initial_channels=[CHANNEL]
        )

        self.sfx_debug = sfx_debug
        self.verbose = verbose
        self.sfx_watcher = SFXWatcher(self, verbose=(self.sfx_debug or self.verbose))
        load_all(self, sfx_debug=sfx_debug)

        self.battleship_game = None
        self.battleship_registration_open = False
        self.battleship_registration_task = None
        self.battleship_turn_task = None
        self.raffle_manager = RaffleManager(filename="raffle.json")

    async def event_ready(self):
        print("🧪 event_ready() fired!")

        print(f"✅ Logged in as: {self.nick}")
        print(f"🛡️  Bot Nick: {self.nick}")
        print(f"🔌 Connected Channels: {self.connected_channels}")

        for chan in self.connected_channels:
            print(f"🔗 Joined Twitch channel: {chan.name}")
            try:
                await chan.send("Welcome to the main event!")
                print(f"✅ Sent arrival message to {chan.name}")
            except Exception as e:
                print(f"⚠️ Failed to send message to {chan.name}: {e}")

        try:
            if self.connected_channels:
                set_twitch_channel(self.connected_channels[0])
                print("🔗 Set Twitch channel in global state")

            if hasattr(mgb_dwf, "on_ready"):
                print("📡 Triggering mgb_dwf.on_ready...")
                await mgb_dwf.on_ready()
            else:
                print("⚠️ mgb_dwf.on_ready not found")
        except Exception as e:
            print(f"❌ Error while calling mgb_dwf.on_ready: {e}")

        print("🎉 event_ready() completed without errors")

    async def event_message(self, message):
        if message.echo or message.author.name.lower() == self.nick.lower():
            return

        if message.content.startswith("!"):
            parts = message.content.split()
            parts[0] = parts[0].lower()
            message.content = " ".join(parts)

        print(f"[{message.author.name}]: {message.content}")
        await self.handle_commands(message)

        # Only allow !battleship join to join a game (not just !battleship)
        if message.content.lower().strip() == "!battleship join":
            if self.battleship_game and (self.battleship_game.active or self.battleship_registration_open):
                username = message.author.name.lower()
                if username not in self.battleship_game.players:
                    self.battleship_game.register_player(username)
                    await message.channel.send(f"@{username} joined Battleship!")
                else:
                    await message.channel.send(f"@{username}, you're already in the game!")
            else:
                await message.channel.send("No Battleship game in progress. Start one with !battleship start <n> or !battleship test <n>.")
            return

        # Battleship intel command for user's turn (allow only once per turn)
        if message.content.lower().strip() == "!battleship intel":
            if self.battleship_game and self.battleship_game.active and not self.battleship_game.is_game_over():
                username = message.author.name.lower()
                current_player = self.battleship_game.get_current_player()
                if username != current_player:
                    await message.channel.send(f"@{username}, you can only use !battleship intel during your turn!")
                    return
                # Disregard if already used intel this turn
                if self.battleship_game.has_used_intel(username):
                    return
                # Mark as used
                self.battleship_game.mark_intel(username)
                # Cancel and restart the timer
                if self.battleship_turn_task:
                    self.battleship_turn_task.cancel()
                squares = self.battleship_game.get_random_open_cells(5)
                if squares:
                    await message.channel.send(f"@{username}, INTEL: Try one of these open cells: {' '.join(squares)}")
                else:
                    await message.channel.send(f"@{username}, no open cells left to suggest!")
                await self.announce_next_battleship_turn(message.channel)
            else:
                await message.channel.send("No Battleship game in progress or it's not your turn.")
            return

        # Battleship guess command for player's turn (outside of TwitchIO command system)
        if message.content.lower().startswith("!battleship "):
            args = message.content.strip().split()
            if len(args) == 2 and self.battleship_game and self.battleship_game.active and not self.battleship_game.is_game_over():
                username = message.author.name.lower()
                cell = args[1].upper()
                current_player = self.battleship_game.get_current_player()
                if not current_player:
                    await message.channel.send(f"No active player turn.")
                    return
                if username != current_player:
                    await message.channel.send(f"@{username}, it's not your turn! Current turn: @{current_player}")
                    return
                if self.battleship_game.has_guessed(username):
                    await message.channel.send(f"@{username}, you have already guessed this round.")
                    return
                result, is_hit, nearby = self.battleship_game.guess(username, cell)
                # Handle invalid guess (reset timer)
                if result == "Invalid":
                    if self.battleship_turn_task:
                        self.battleship_turn_task.cancel()
                    await message.channel.send(f"@{username}, that's not a valid cell! Please guess a cell like D4 (A1–J10).")
                    await self.announce_next_battleship_turn(message.channel)
                    return
                # Handle already guessed (reset timer)
                if result == "Already guessed":
                    if self.battleship_turn_task:
                        self.battleship_turn_task.cancel()
                    msg = f"@{username}, {cell} has already been guessed! Try a different cell."
                    if nearby:
                        msg += " Nearby open Squares: " + " ".join(nearby)
                    await message.channel.send(msg)
                    await self.announce_next_battleship_turn(message.channel)
                    return
                # Always award raffle entry BEFORE checking for game over
                if is_hit:
                    msg = f"@{username}, that's a Hit!"
                    if not self.battleship_game.test_mode:
                        self.raffle_manager.grant_persistent_entries(username, 1)
                        msg += " You earned a raffle entry!"
                    else:
                        msg += " (Test mode: No raffle entry awarded.)"
                    await message.channel.send(msg)
                else:
                    await message.channel.send(f"@{username}, that's a Miss!")
                self.battleship_game.mark_guessed(username)
                # Cancel the existing turn timeout, if any, since a guess was made
                if self.battleship_turn_task:
                    self.battleship_turn_task.cancel()
                    self.battleship_turn_task = None
                # Only check for game over AFTER awarding the entry
                if self.battleship_game.is_game_over():
                    await self.handle_battleship_game_end(message.channel)
                else:
                    await self.advance_battleship_turn(message.channel)
            return

    async def event_command_error(self, ctx, error):
        if isinstance(error, commands.errors.CommandNotFound):
            full_message = ctx.message.content.strip()
            if not full_message.startswith("!"):
                return
            attempted = full_message[1:].split()[0].lower()
            user = ctx.author.name
            user_info = await self.fetch_users(names=[user])
            created = user_info[0].created_at.replace(tzinfo=None) if user_info and user_info[0].created_at else None
            reason = "invalid characters in command" if not is_valid_command_name(attempted) else "command not found"
            log_skip(reason, user, attempted, created)

    async def event_error(self, error: Exception, data=None):
        import logging
        import traceback
        logging.error("Unhandled exception", exc_info=error)
        print("\n💥 Unhandled exception in event loop:")
        if error:
            traceback.print_exception(type(error), error, error.__traceback__)

    # --- Battleship Commands ---

    @commands.command(name="battleship")
    async def battleship_command(self, ctx):
        """
        Handles !battleship start <num_ships> and !battleship test <num_ships>
        """
        args = ctx.message.content.strip().split()
        user = ctx.author.name.lower()
        # Only allow broadcaster or mods to start games
        if len(args) >= 3 and args[1] in ("start", "test"):
            if self.battleship_registration_open or (self.battleship_game and self.battleship_game.active):
                await ctx.send("A Battleship game is already registering or in progress. Wait for it to finish!")
                return
            if not await self.is_mod_or_broadcaster(ctx):
                await ctx.send("Only mods or broadcaster can start a battleship game.")
                return
            num_ships = 5
            try:
                num_ships = int(args[2])
                if num_ships < 1 or num_ships > 20:
                    raise ValueError
            except Exception:
                await ctx.send("Usage: !battleship start <1-20> or !battleship test <1-20>")
                return
            test_mode = args[1] == "test"
            self.battleship_game = BattleshipGame(num_ships, test_mode=test_mode)
            self.battleship_registration_open = True
            await ctx.send(
                f"Battleship {'TEST ' if test_mode else ''}game opened! Type !battleship join to enter. Registration open for 2 minutes."
            )
            # Start registration timer
            if self.battleship_registration_task:
                self.battleship_registration_task.cancel()
            self.battleship_registration_task = asyncio.create_task(
                self.close_battleship_registration(ctx.channel)
            )
            return

    async def close_battleship_registration(self, channel):
        await asyncio.sleep(120)  # 2 minute registration period
        self.battleship_registration_open = False
        if not self.battleship_game or not self.battleship_game.players:
            await channel.send("Battleship: No players registered, game canceled.")
            self.battleship_game = None
            return
        self.battleship_game.start_game()
        await channel.send(
            f"Battleship registration closed. Players: {', '.join(self.battleship_game.players)}"
        )
        await self.announce_next_battleship_turn(channel)

    async def announce_next_battleship_turn(self, channel):
        if not self.battleship_game or not self.battleship_game.active or self.battleship_game.is_game_over():
            await self.handle_battleship_game_end(channel)
            return
        player = self.battleship_game.get_current_player()
        if player:
            await channel.send(
                f"@{player}, it's your turn! Type !battleship <cell> (e.g., !battleship D4) within 1 minute. You can also type !battleship intel to get a hint."
            )
            # Cancel any existing turn task before starting a new one
            if self.battleship_turn_task:
                self.battleship_turn_task.cancel()
            self.battleship_turn_task = asyncio.create_task(self.handle_battleship_turn_timeout(channel, player))
        else:
            await channel.send("No players currently in the Battleship game.")

    async def handle_battleship_turn_timeout(self, channel, player):
        await asyncio.sleep(60)  # 1 minute for turn
        if (
            self.battleship_game
            and self.battleship_game.active
            and not self.battleship_game.is_game_over()
            and not self.battleship_game.has_guessed(player)
            and self.battleship_game.get_current_player() == player
        ):
            await channel.send(f"@{player} did not guess in time. Turn skipped.")
            self.battleship_game.mark_guessed(player)
            await self.advance_battleship_turn(channel)

    async def advance_battleship_turn(self, channel):
        if not self.battleship_game:
            return
        self.battleship_game.next_turn()
        if self.battleship_game.is_game_over():
            await self.handle_battleship_game_end(channel)
        else:
            await self.announce_next_battleship_turn(channel)

    async def handle_battleship_game_end(self, channel):
        if not self.battleship_game:
            return
        if self.battleship_game.is_game_over():
            hits = self.battleship_game.raffle_hits
            if not self.battleship_game.test_mode:
                if hits:
                    entries = ", ".join(f"{user} ({count})" for user, count in hits.items())
                    await channel.send(f"All ships have been hit! Game over. Raffle entries: {entries}")
                else:
                    await channel.send("All ships have been hit! Game over. No raffle entries were awarded.")
            else:
                await channel.send("All ships have been hit! Game over (Test mode: No raffle entries awarded).")
            self.battleship_game = None
            if self.battleship_turn_task:
                self.battleship_turn_task.cancel()
                self.battleship_turn_task = None
        else:
            await channel.send("Battleship round ended. Start a new game with !battleship start <n>.")

    async def is_mod_or_broadcaster(self, ctx):
        badges = ctx.author.badges or {}
        return "broadcaster" in badges or "moderator" in badges 