import unittest
from pathlib import Path

from bot.commands.wotwom_cog import parse_external_tankstats


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
        self.assertIn("fetch_player_tank_chat_stats", self.source)

    def test_external_player_tank_lookup_accepts_comma_syntax(self):
        self.assertEqual(
            ("-x", "Player Name", "Tiger 131"),
            parse_external_tankstats("!tankstats -x, Player Name, Tiger 131"),
        )
        self.assertEqual(
            ("-p", "Player Name", "Tiger 131"),
            parse_external_tankstats("!tankstats -p Player Name, Tiger 131"),
        )

    def test_external_player_lookup_keeps_pipe_and_summary_syntax(self):
        self.assertEqual(
            ("-x", "Player Name", "Tiger 131"),
            parse_external_tankstats("!tankstats -x Player Name | Tiger 131"),
        )
        self.assertEqual(
            ("-p", "Player Name", ""),
            parse_external_tankstats("!tankstats -p Player Name"),
        )
        self.assertIsNone(parse_external_tankstats("!tankstats Tiger 131"))


if __name__ == "__main__":
    unittest.main()
