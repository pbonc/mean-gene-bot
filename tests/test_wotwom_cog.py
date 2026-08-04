import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COG = ROOT / "bot" / "commands" / "wotwom_cog.py"


class WotWomCogAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = COG.read_text(encoding="utf-8")

    def test_wotgarage_is_mod_or_broadcaster_only(self):
        self.assertIn('getattr(ctx.author, "is_mod", False)', self.source)
        self.assertIn('getattr(ctx.author, "is_broadcaster", False)', self.source)
        self.assertIn("if not is_privileged:", self.source)

    def test_opstats_command_is_registered(self):
        self.assertIn('@commands.command(name="opstats")', self.source)
        self.assertIn("most beaten:", self.source)
        self.assertIn("most failures:", self.source)

    def test_sold_status_announcements_are_monitored(self):
        self.assertIn("pending_sold_announcements", self.source)
        self.assertIn("_sold_announcement_monitor", self.source)
        self.assertIn("acknowledge_sold_announcement", self.source)

    def test_external_player_lookup_supports_both_console_platforms(self):
        self.assertIn('mode in {"-x", "-p"}', self.source)
        self.assertIn('payload.partition("|")', self.source)
        self.assertIn("fetch_player_tank_chat_stats", self.source)


if __name__ == "__main__":
    unittest.main()
