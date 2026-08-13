import json
import random
import tempfile
import unittest
from pathlib import Path

from bot.commands.giveaway_cog import parse_giveaway_command
from bot.giveaway_state import GiveawayState, matches_entry


class GiveawayStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state_file = str(Path(self.directory.name) / "giveaway.json")
        self.manager = GiveawayState(self.state_file, rng=random.Random(4))

    def tearDown(self):
        self.directory.cleanup()

    def test_quoted_open_command_preserves_spaces(self):
        self.assertEqual(
            ["open", "Game key and shirt", "friendly phrase"],
            parse_giveaway_command('!giveaway open "Game key and shirt" "friendly phrase"'),
        )

    def test_word_phrase_and_sfx_matching(self):
        self.assertTrue(matches_entry("That friendly phrase works", "friendly phrase"))
        self.assertFalse(matches_entry("unfriendly phrases", "friendly phrase"))
        self.assertTrue(matches_entry("!airhorn", "!AIRHORN"))
        self.assertTrue(matches_entry("!airhorn extra", "!airhorn"))
        self.assertFalse(matches_entry("try !airhorn", "!airhorn"))

    def test_each_user_enters_once_and_state_persists(self):
        self.manager.open("A prize", "hello there")
        self.assertTrue(self.manager.enter("Viewer", "HELLO THERE!"))
        self.assertFalse(self.manager.enter("viewer", "hello there"))
        reloaded = GiveawayState(self.state_file)
        self.assertEqual(["viewer"], reloaded.state["entrants"])

    def test_open_limits_text_to_chat_safe_lengths(self):
        with self.assertRaisesRegex(ValueError, "160"):
            self.manager.open("x" * 161, "word")
        with self.assertRaisesRegex(ValueError, "80"):
            self.manager.open("prize", "x" * 81)

    def test_draw_requires_closed_giveaway_and_records_winner(self):
        self.manager.open("A prize", "!airhorn")
        self.manager.enter("alpha", "!airhorn")
        self.manager.enter("bravo", "!airhorn")
        with self.assertRaisesRegex(ValueError, "Close"):
            self.manager.draw()
        self.manager.close()
        winner = self.manager.draw()
        self.assertIn(winner, ("alpha", "bravo"))
        payload = self.manager.payload(animate=True)
        self.assertEqual(winner, payload["winner"])
        self.assertTrue(payload["animate"])
        self.assertEqual(1, payload["draw_id"])

    def test_public_payload_contains_only_config_and_entrant_names(self):
        self.manager.open("A prize", "word")
        self.manager.enter("alpha", "word")
        payload = self.manager.payload()
        self.assertEqual("giveaway_state", payload["type"])
        self.assertEqual(["alpha"], payload["entrants"])
        self.assertNotIn("rng", json.dumps(payload))


class GiveawayOverlayTests(unittest.TestCase):
    def test_route_snapshot_and_animation_are_registered(self):
        root = Path(__file__).resolve().parents[1]
        server = (root / "bot" / "overlay_server.py").read_text(encoding="utf-8")
        overlay = (root / "bot" / "overlay_static" / "giveaway_overlay.html").read_text(encoding="utf-8")
        self.assertIn('app.router.add_get("/giveaway", giveaway_overlay)', server)
        self.assertIn("request_giveaway_state", server)
        self.assertIn("async function animateDraw", overlay)
        self.assertIn("winner-plate", overlay)
        self.assertIn("step < steps", overlay)
        self.assertNotIn("step <= steps", overlay)
        self.assertIn("function fitWinnerName()", overlay)
        self.assertIn("white-space: nowrap", overlay)


if __name__ == "__main__":
    unittest.main()
