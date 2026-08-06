import unittest

from bot.wot_stats import TankLookupError, resolve_tank, summarize_stats, summarize_tank


class WotStatsSummaryTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "all": {
                "battles": 100,
                "wins": 55,
                "survived_battles": 25,
                "frags": 150,
                "damage_dealt": 200_000,
                "xp": 80_000,
            },
            "damage_assisted_radio": 20_000,
            "damage_assisted_track": 5_000,
            "damage_assisted_wheel": 0,
            "trees_cut": 1234,
            "max_damage": 9000,
            "max_damage_tank_id": 1,
            "max_frags": 10,
            "max_frags_tank_id": 2,
            "max_xp": 2500,
            "max_xp_tank_id": 1,
        }
        self.vehicles = [
            {
                "tank_id": 1,
                "all": {
                    "battles": 72,
                    "damage_assisted_radio": 8000,
                    "damage_assisted_track": 1000,
                    "damage_assisted_wheel": 0,
                },
            },
            {
                "tank_id": 2,
                "all": {
                    "battles": 28,
                    "damage_assisted_radio": 4000,
                    "damage_assisted_track": 1000,
                    "damage_assisted_wheel": 0,
                },
            },
        ]

    def test_summary_calculates_rates_and_assisted_damage(self):
        result = summarize_stats(
            "Darr-x", self.account, self.vehicles, {1: "Tank One", 2: "Tank Two"}
        )
        self.assertIn("100 battles", result["summary"])
        self.assertIn("55.0% wins", result["summary"])
        self.assertIn("2.00 K/D", result["summary"])
        self.assertIn("2,000 avg dmg", result["summary"])
        self.assertIn("250 avg assisted", result["summary"])
        self.assertIn("1,234 trees", result["summary"])
        self.assertIn("most played: Tank One (72 battles)", result["summary"])

    def test_records_include_resolved_tanks_and_assisted_leader(self):
        result = summarize_stats(
            "Darr-x", self.account, self.vehicles, {1: "Tank One", 2: "Tank Two"}
        )
        self.assertIn("damage: 9,000 (Tank One)", result["records"])
        self.assertIn("kills: 10 (Tank Two)", result["records"])
        self.assertIn("XP: 2,500 (Tank One)", result["records"])
        self.assertIn(
            "assisted career leader: 9,000 (Tank One)", result["records"]
        )

    def test_tank_lookup_prefers_exact_then_unique_partial(self):
        vehicles = [
            {"tank_id": 1, "name": "Tiger 131"},
            {"tank_id": 2, "name": "Tiger II"},
            {"tank_id": 3, "name": "Thumper"},
        ]
        self.assertEqual(1, resolve_tank("tiger 131", vehicles)["tank_id"])
        self.assertEqual(3, resolve_tank("thump", vehicles)["tank_id"])
        with self.assertRaises(TankLookupError):
            resolve_tank("tiger", vehicles)
        with self.assertRaises(TankLookupError):
            resolve_tank("not a tank", vehicles)

    def test_duplicate_name_defaults_to_version_with_most_battles(self):
        vehicles = [
            {"tank_id": 1, "name": "T-34", "mode": "wwii", "tier": 5},
            {"tank_id": 2, "name": "T-34", "mode": "cold_war", "era": 1},
        ]
        stats = {
            1: {"all": {"battles": 25}},
            2: {"all": {"battles": 100}},
        }
        self.assertEqual(2, resolve_tank("t-34", vehicles, stats)["tank_id"])
        self.assertEqual(
            1,
            resolve_tank(
                "t-34", vehicles, stats, preferred_mode="wwii"
            )["tank_id"],
        )

    def test_per_tank_summary_includes_core_and_assisted_stats(self):
        vehicle = {"tank_id": 1, "name": "Tiger 131"}
        stats = {
            "all": {
                "battles": 10,
                "wins": 6,
                "survived_battles": 4,
                "frags": 12,
                "damage_dealt": 15_000,
                "damage_assisted_radio": 2_000,
                "damage_assisted_track": 500,
                "xp": 8_000,
                "max_damage": 3_000,
            },
            "max_frags": 5,
            "mark_of_mastery": 4,
        }
        result = summarize_tank(vehicle, stats)
        self.assertIn("Tiger 131 | 10 battles", result)
        self.assertIn("60.0% wins", result)
        self.assertIn("250 avg assisted", result)
        self.assertIn("3,000 max dmg", result)
        self.assertIn("mastery: Ace", result)


if __name__ == "__main__":
    unittest.main()
