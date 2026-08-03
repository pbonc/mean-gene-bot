import tempfile
import unittest
from pathlib import Path

import bot.wot_sold as sold


class WotSoldTests(unittest.TestCase):
    def setUp(self):
        self.original_file = sold.SOLD_FILE
        self.temp_dir = tempfile.TemporaryDirectory()
        sold.SOLD_FILE = Path(self.temp_dir.name) / "sold.json"

    def tearDown(self):
        sold.SOLD_FILE = self.original_file
        self.temp_dir.cleanup()

    def test_mark_sold_queues_one_announcement_and_restore_clears_status(self):
        vehicle = {"tank_id": 7, "name": "Test Tank", "mode": "wwii", "tier": 5}
        sold.mark_sold(vehicle)
        sold.mark_sold(vehicle)
        self.assertEqual(["Test Tank"], [v["name"] for v in sold.sold_vehicles()])
        self.assertEqual(1, len(sold.pending_sold_announcements()))
        self.assertIn("set to sold status", sold.pending_sold_announcements()[0]["message"])
        self.assertTrue(sold.restore_vehicle(7))
        self.assertEqual([], sold.sold_vehicles())
        self.assertEqual([], sold.pending_sold_announcements())


if __name__ == "__main__":
    unittest.main()
