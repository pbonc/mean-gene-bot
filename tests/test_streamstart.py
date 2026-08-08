import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.commands import streamstart_cog
from bot.commands.wotd_cog import WOTDState


class StreamStartTests(unittest.TestCase):
    def test_owner_login_is_exact_and_case_insensitive(self):
        with patch.object(streamstart_cog, "OWNER_ID", ""):
            self.assertTrue(streamstart_cog.is_stream_owner(SimpleNamespace(name="iAmDar")))
            self.assertTrue(streamstart_cog.is_stream_owner(SimpleNamespace(name="IAMDAR")))
            self.assertFalse(streamstart_cog.is_stream_owner(SimpleNamespace(name="notiamdar")))

    def test_configured_owner_id_takes_priority(self):
        with patch.object(streamstart_cog, "OWNER_ID", "123"):
            self.assertTrue(streamstart_cog.is_stream_owner(SimpleNamespace(id="123", name="someone")))
            self.assertFalse(streamstart_cog.is_stream_owner(SimpleNamespace(id="999", name="iamdar")))

    def test_wotd_stream_reset_reports_and_clears_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = f"{directory}/wotd.json"
            with patch("bot.commands.wotd_cog.WOTD_STATE_FILE", state_file):
                state = WOTDState()
                state.is_active = True
                state.current_word = "treads"
                state.prize_value = 20
                state.stream_bias_percent = 45
                previous = state.reset_for_stream_start()
            self.assertEqual(
                {"word": "treads", "entries": 20, "next_entries": 25, "was_active": True},
                previous,
            )
            self.assertFalse(state.is_active)
            self.assertIsNone(state.current_word)
            self.assertEqual(25, state.prize_value)
            self.assertEqual(15, state.stream_bias_percent)

    def test_completed_wotd_is_retained_until_stream_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = f"{directory}/wotd.json"
            with patch("bot.commands.wotd_cog.WOTD_STATE_FILE", state_file):
                state = WOTDState()
                state.is_active = True
                state.current_word = "ammo"
                state.prize_value = 15
                state.award_winner("viewer")
                previous = state.reset_for_stream_start()
            self.assertEqual("ammo", previous["word"])
            self.assertEqual(15, previous["entries"])
            self.assertEqual(20, previous["next_entries"])
            self.assertIsNone(state.last_word)

    def test_each_stream_start_adds_exactly_five_to_carried_prize(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = f"{directory}/wotd.json"
            with patch("bot.commands.wotd_cog.WOTD_STATE_FILE", state_file):
                state = WOTDState()
                state.prize_value = 50
                state.reset_for_stream_start()
                state.reset_for_stream_start()
            self.assertEqual(60, state.prize_value)


if __name__ == "__main__":
    unittest.main()
