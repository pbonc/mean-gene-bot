import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import bot.wot_inventory as inventory


def payload(*vehicles):
    return {
        "account_id": "9546892",
        "nickname": "Darr-x",
        "source": "played_vehicle_statistics",
        "vehicles": [
            {
                "tank_id": tank_id,
                "name": name,
                "mode": "wwii",
                "tier": 1,
                "era": None,
                "nation": "USA",
                "type": "Light Tank",
            }
            for tank_id, name in vehicles
        ],
    }


class WotInventorySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.original_file = inventory.SNAPSHOT_FILE
        self.original_fetch = inventory.fetch_wot_inventory
        self.temp_dir = tempfile.TemporaryDirectory()
        inventory.SNAPSHOT_FILE = Path(self.temp_dir.name) / "snapshot.json"

    def tearDown(self):
        inventory.SNAPSHOT_FILE = self.original_file
        inventory.fetch_wot_inventory = self.original_fetch
        self.temp_dir.cleanup()

    def test_first_refresh_is_silent_baseline(self):
        inventory.fetch_wot_inventory = AsyncMock(
            return_value=payload((1, "T1"), (2, "T2"))
        )
        _, discovered = asyncio.run(inventory.refresh_wot_snapshot())
        self.assertEqual([], discovered)
        self.assertEqual(2, inventory.snapshot_status()["vehicle_count"])
        self.assertEqual([], inventory.pending_deliveries())

    def test_new_tank_is_queued_once_and_can_be_acknowledged(self):
        inventory.fetch_wot_inventory = AsyncMock(return_value=payload((1, "T1")))
        asyncio.run(inventory.refresh_wot_snapshot())
        inventory.fetch_wot_inventory = AsyncMock(
            return_value=payload((1, "T1"), (2, "M2 Light"))
        )
        _, discovered = asyncio.run(inventory.refresh_wot_snapshot())
        self.assertEqual(["M2 Light"], [tank["name"] for tank in discovered])
        self.assertEqual(["M2 Light"], [tank["name"] for tank in inventory.pending_deliveries()])

        asyncio.run(inventory.acknowledge_delivery(2))
        self.assertEqual([], inventory.pending_deliveries())
        _, discovered_again = asyncio.run(inventory.refresh_wot_snapshot())
        self.assertEqual([], discovered_again)


if __name__ == "__main__":
    unittest.main()
