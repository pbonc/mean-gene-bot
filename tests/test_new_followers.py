import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from bot.commands.new_follower_cog import NewFollowerCog, follower_message


class NewFollowerMessageTests(unittest.TestCase):
    def test_all_variants_are_highlighted_conversational_and_within_chat_limit(self):
        messages = [follower_message("NewViewer", 25, True, index) for index in range(4)]
        self.assertEqual(4, len(set(messages)))
        for message in messages:
            self.assertIn("@NewViewer", message)
            self.assertIn("10 free", message)
            self.assertIn("$25 gift card", message)
            self.assertIn("!raffle random all", message)
            self.assertIn(" or ", message)
            self.assertLessEqual(len(message), 500)

    def test_closed_raffle_tells_follower_when_commands_can_be_used(self):
        message = follower_message("Viewer", 10, False, 0)
        self.assertIn("When the raffle opens, try", message)


class NewFollowerAwardTests(unittest.IsolatedAsyncioTestCase):
    async def test_follow_awards_ten_entries_and_records_event(self):
        class RaffleState:
            is_open = True

            def __init__(self):
                self.awards = []

            def add_entries(self, username, count):
                self.awards.append((username, count))
                return True

            def get_giveaway_amount(self):
                return 25

        raffle = SimpleNamespace(state=RaffleState())
        channel = SimpleNamespace(sent=[])

        async def send(message):
            channel.sent.append(message)

        channel.send = send
        cog = NewFollowerCog.__new__(NewFollowerCog)
        cog.bot = SimpleNamespace(get_cog=lambda name: raffle if name == "RaffleCog" else None)
        cog.state = {"initialized": True, "handled_events": [], "next_variant": 0}
        with TemporaryDirectory() as directory, patch(
            "bot.commands.new_follower_cog.STATE_FILE",
            Path(directory) / "state.json",
        ):
            handled = await cog._handle_follow(
                {"user_name": "NewViewer"}, channel, "123:2026-08-09T00:00:00Z"
            )

        self.assertTrue(handled)
        self.assertEqual([("NewViewer", 10)], raffle.state.awards)
        self.assertEqual(["123:2026-08-09T00:00:00Z"], cog.state["handled_events"])
        self.assertIn("@NewViewer", channel.sent[0])


if __name__ == "__main__":
    unittest.main()
