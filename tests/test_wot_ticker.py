import unittest

from bot.wot_ticker import build_ticker_messages


class WotTickerTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "private": {"slots": 1000, "empty_slots": 56},
            "statistics": {
                "all": {"battles": 200, "wins": 110},
                "trees_cut": 12345,
            },
        }
        self.agents = {
            "total": 8,
            "most_pass": {"agent": "Alice", "pass": 5, "fail": 0},
            "most_fail": {"agent": "Bob", "pass": 0, "fail": 3},
        }

    def test_rotates_requested_dar_tank_statistics(self):
        expected = (
            "Dar's Garage: 944 vehicles owned",
            "Dar Tank Record: 200 battles played",
            "Dar Tank Record: 55.0% win rate",
            "Dar's Arborist Record: 12,345 trees knocked over",
        )
        for index, message in enumerate(expected):
            self.assertEqual(
                message,
                build_ticker_messages(self.profile, {}, index)[0],
            )

    def test_agent_leaders_are_included(self):
        messages = build_ticker_messages(self.profile, self.agents, 0)
        self.assertEqual(2, len(messages))
        self.assertIn("most won challenges @Alice (5)", messages[1])
        self.assertIn("most lost challenges @Bob (3)", messages[1])


if __name__ == "__main__":
    unittest.main()
