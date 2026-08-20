import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from bot.commands.new_follower_cog import NewFollowerCog, first_chatter_message, follower_message


class NewFollowerMessageTests(unittest.TestCase):
    def test_all_follow_variants_are_concise_and_have_one_action(self):
        messages = [follower_message("NewViewer", 25, True, index) for index in range(4)]
        self.assertEqual(4, len(set(messages)))
        for message in messages:
            self.assertIn("@NewViewer", message)
            self.assertIn("10 free", message)
            self.assertIn("$25 gift card", message)
            self.assertIn("!raffle random all", message)
            self.assertNotIn("!raffle pick", message)
            self.assertLessEqual(len(message), 250)

    def test_closed_raffle_tells_follower_when_commands_can_be_used(self):
        message = follower_message("Viewer", 10, False, 0)
        self.assertIn("banked", message)
        self.assertIn("!fish join", message)

    def test_first_chatter_variants_are_short_personal_and_single_action(self):
        messages = [first_chatter_message("NewViewer", index) for index in range(4)]
        self.assertEqual(4, len(set(messages)))
        for message in messages:
            self.assertIn("@NewViewer", message)
            self.assertIn("!fish join", message)
            self.assertLessEqual(len(message), 180)


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

    async def test_first_chatter_is_welcomed_once_and_persisted_before_send(self):
        channel = SimpleNamespace(sent=[])

        async def send(message):
            channel.sent.append(message)

        channel.send = send
        author = SimpleNamespace(id="42", name="newviewer", display_name="NewViewer")
        message = SimpleNamespace(author=author, channel=channel, echo=False, first=True)
        cog = NewFollowerCog.__new__(NewFollowerCog)
        cog.state = {
            "initialized": False, "handled_events": [], "next_variant": 0,
            "welcomed_chatters": [], "next_chatter_variant": 0,
        }
        with TemporaryDirectory() as directory, patch(
            "bot.commands.new_follower_cog.STATE_FILE",
            Path(directory) / "state.json",
        ):
            first = await cog._handle_first_chatter(message)
            duplicate = await cog._handle_first_chatter(message)

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertEqual(["42"], cog.state["welcomed_chatters"])
        self.assertEqual(1, len(channel.sent))
        self.assertIn("@NewViewer", channel.sent[0])


if __name__ == "__main__":
    unittest.main()
