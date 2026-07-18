import unittest

from bot.rpg_v2.contracts import validate_expedition_snapshot
from bot.rpg_v2.presence import ExpeditionPresenceService


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ExpeditionPresenceTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.service = ExpeditionPresenceService(
            active_window_seconds=60,
            walkoff_window_seconds=180,
            clock=self.clock,
        )

    def test_join_creates_adventurer_and_duplicate_join_reuses_identity(self):
        first, created = self.service.join("42", "Viewer")
        second, created_again = self.service.join("42", "VIEWER")

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertIs(first, second)
        self.assertEqual(first.character_class, "adventurer")
        self.assertEqual(self.service.joined_count(), 1)

    def test_name_fallback_identity_is_case_insensitive(self):
        first, _ = self.service.join(None, "SomeViewer")
        second, created = self.service.join(None, "someviewer")

        self.assertFalse(created)
        self.assertEqual(first.actor_id, second.actor_id)

    def test_ordinary_activity_refreshes_only_joined_viewers(self):
        self.assertFalse(self.service.touch("99", "NotJoined"))
        member, _ = self.service.join("42", "Viewer")
        self.clock.advance(30)

        self.assertTrue(self.service.touch("42", "Viewer"))
        self.assertEqual(member.last_seen_at, 1030.0)

    def test_presence_becomes_idle_then_walks_off_without_deletion(self):
        self.service.join("42", "Viewer")
        self.clock.advance(61)
        idle = self.service.snapshot()

        self.assertEqual(idle["members"][0]["presence"], "idle")

        self.clock.advance(120)
        walked_off = self.service.snapshot()
        self.assertEqual(walked_off["members"], [])
        self.assertEqual(self.service.joined_count(), 1)

    def test_returning_viewer_reappears_on_chat(self):
        self.service.join("42", "Viewer")
        self.clock.advance(181)
        self.assertEqual(self.service.snapshot()["members"], [])

        self.assertTrue(self.service.touch("42", "Viewer"))
        self.assertEqual(len(self.service.snapshot()["members"]), 1)

    def test_snapshot_is_versioned_and_accepts_large_roster(self):
        for index in range(250):
            self.service.join(str(index), f"Viewer{index}")

        snapshot = self.service.snapshot()
        validate_expedition_snapshot(snapshot)
        self.assertEqual(snapshot["type"], "rpg_v2_expedition")
        self.assertEqual(snapshot["version"], 2)
        self.assertEqual(len(snapshot["members"]), 250)

    def test_invalid_timeout_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must exceed"):
            ExpeditionPresenceService(active_window_seconds=60, walkoff_window_seconds=60)


if __name__ == "__main__":
    unittest.main()
