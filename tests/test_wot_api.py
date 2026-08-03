import unittest
from unittest.mock import AsyncMock

from bot.wot_api import (
    WotApiClient,
    WotConfig,
    _era_for_vehicle,
    _faction_for_vehicle,
    _mode_for_vehicle,
    _nation_for_vehicle,
    _vehicle_type,
)


class WotApiNormalizationTests(unittest.TestCase):
    def test_configuration_is_inert_without_credentials(self):
        config = WotConfig(application_id="")
        self.assertEqual("", config.application_id)

    def test_vehicle_modes_are_normalized(self):
        self.assertEqual("cold_war", _mode_for_vehicle({"era_name": "Cold War Era 2"}))
        self.assertEqual("cold_war", _mode_for_vehicle({"era": 1}))
        self.assertEqual("cold_war", _mode_for_vehicle({"era": "Post War"}))
        self.assertEqual("wwii", _mode_for_vehicle({"tier": 10}))

    def test_vehicle_types_are_display_ready(self):
        self.assertEqual("Tank Destroyer", _vehicle_type("AT-SPG"))
        self.assertEqual("Heavy Tank", _vehicle_type("heavyTank"))

    def test_cold_war_era_is_normalized(self):
        self.assertEqual(2, _era_for_vehicle({"era_name": "Cold War Era 2"}))
        self.assertEqual(3, _era_for_vehicle({"era": 3}))
        self.assertEqual(1, _era_for_vehicle({"era": "Post War"}))
        self.assertEqual(2, _era_for_vehicle({"era": "Escalation"}))
        self.assertEqual(3, _era_for_vehicle({"era": "Détente"}))
        self.assertIsNone(_era_for_vehicle({"tier": 10}))

    def test_nations_and_cold_war_factions_are_normalized(self):
        self.assertEqual("USA", _nation_for_vehicle("usa"))
        self.assertEqual("Mercenary", _nation_for_vehicle("merc"))
        self.assertEqual(
            "Western Alliance",
            _faction_for_vehicle({"era": "Post War", "nation": "usa"}),
        )
        self.assertEqual(
            "Eastern Alliance",
            _faction_for_vehicle({"era": "Escalation", "nation": "ussr"}),
        )
        self.assertEqual(
            "Independent",
            _faction_for_vehicle({"era": "Détente", "nation": "xn"}),
        )
        self.assertIsNone(_faction_for_vehicle({"tier": 10, "nation": "usa"}))

    def test_console_platform_suffix_is_resolved(self):
        client = WotApiClient(WotConfig("app", player_name="Darr"), None)
        client._get = AsyncMock(
            return_value=[{"account_id": 9546892, "nickname": "Darr-x"}]
        )
        self.assertEqual(
            ("9546892", "Darr-x"),
            __import__("asyncio").run(client.resolve_account()),
        )


if __name__ == "__main__":
    unittest.main()
