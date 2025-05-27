import asyncio
from twitchio.ext import commands
from bot.raffle_manager import RaffleManager
from bot.battleship import BattleshipGame

class MeanGeneBot(commands.Bot):
    def __init__(self, sfx_debug=False, verbose=False):
        super().__init__(
            token="YOUR_TWITCH_TOKEN",
            prefix="!",
            initial_channels=["YOUR_CHANNEL"]
        )

        self.raffle_manager = RaffleManager(filename="entries.json")
        self.battleship_game = None
        self.battleship_registration_open = False
        self.battleship_registration_task = None
        self.battleship_turn_task = None
        self.active_raffle = False
        self.raffle_awarded_users = set()
        self.raffle_award_amount = 1

    async def event_ready(self):
        print(f"✅ Logged in as: {self.nick}")

    async def event_message(self, message):
        if message.echo or message.author.name.lower() == self.nick.lower():
            return

        await self.handle_commands(message)

        # Openraffle: Give entry on chat
        if self.active_raffle:
            user = message.author.name.lower()
            if user not in self.raffle_awarded_users:
                await self.raffle_manager.award_entries(user, self.raffle_award_amount, message.channel)
                self.raffle_awarded_users.add(user)

        # Battleship join
        if message.content.lower().strip() == "!battleship join":
            if self.battleship_game and (self.battleship_game.active or self.battleship_registration_open):
                username = message.author.name.lower()
                if username not in self.battleship_game.players:
                    self.battleship_game.register_player(username)
                    await message.channel.send(f"@{username} joined Battleship!")
                else:
                    await message.channel.send(f"@{username}, you're already in the game!")
            else:
                await message.channel.send("No Battleship game in progress. Start one with !battleship start <n>.")
            return

        # Battleship guess
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
                if result == "Invalid":
                    await message.channel.send(f"@{username}, that's not a valid cell! Please guess a cell like D4 (A1–J10).")
                    await self.announce_next_battleship_turn(message.channel)
                    return
                if result == "Already guessed":
                    msg = f"@{username}, {cell} has already been guessed! Try a different cell."
                    if nearby:
                        msg += " Nearby open Squares: " + " ".join(nearby)
                    await message.channel.send(msg)
                    await self.announce_next_battleship_turn(message.channel)
                    return
                if is_hit:
                    await self.raffle_manager.award_entries(username, 1, message.channel)
                    await message.channel.send(f"@{username}, that's a Hit!")
                else:
                    await message.channel.send(f"@{username}, that's a Miss!")
                self.battleship_game.mark_guessed(username)
                if self.battleship_turn_task:
                    self.battleship_turn_task.cancel()
                    self.battleship_turn_task = None
                if self.battleship_game.is_game_over():
                    await self.handle_battleship_game_end(message.channel)
                else:
                    await self.advance_battleship_turn(message.channel)
            return

    @commands.command(name="openraffle")
    async def openraffle_command(self, ctx):
        args = ctx.message.content.strip().split()
        if len(args) == 2 and args[1].isdigit():
            self.active_raffle = True
            self.raffle_awarded_users = set()
            self.raffle_award_amount = int(args[1])
            await ctx.send(f"Raffle opened! Speak in chat to receive {args[1]} entry(ies).")
        else:
            await ctx.send("Usage: !openraffle <number>")

    @commands.command(name="myentries")
    async def myentries_command(self, ctx):
        user = ctx.author.name.lower()
        n = self.raffle_manager.get_entries(user)
        await ctx.send(f"🎟 Entries for @{user}: {n}")

    @commands.command(name="battleship")
    async def battleship_command(self, ctx):
        args = ctx.message.content.strip().split()
        user = ctx.author.name.lower()
        if len(args) >= 3 and args[1] in ("start", "test"):
            if self.battleship_registration_open or (self.battleship_game and self.battleship_game.active):
                await ctx.send("A Battleship game is already registering or in progress. Wait for it to finish!")
                return
            num_ships = 5
            try:
                num_ships = int(args[2])
                if num_ships < 1 or num_ships > 20:
                    raise ValueError
            except Exception:
                await ctx.send("Usage: !battleship start <1-20>")
                return
            test_mode = args[1] == "test"
            self.battleship_game = BattleshipGame(num_ships, test_mode=test_mode)
            self.battleship_registration_open = True
            await ctx.send(
                f"Battleship {'TEST ' if test_mode else ''}game opened! Type !battleship join to enter. Registration open for 2 minutes."
            )
            if self.battleship_registration_task:
                self.battleship_registration_task.cancel()
            self.battleship_registration_task = asyncio.create_task(
                self.close_battleship_registration(ctx.channel)
            )

    async def close_battleship_registration(self, channel):
        await asyncio.sleep(120)  # 2 minutes
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
                f"@{player}, it's your turn! Type !battleship <cell> (e.g., !battleship D4) within 1 minute."
            )
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
            await channel.send("All ships have been hit! Game over.")
            self.battleship_game = None
            if self.battleship_turn_task:
                self.battleship_turn_task.cancel()
                self.battleship_turn_task = None
        else:
            await channel.send("Battleship round ended. Start a new game with !battleship start <n>.")