import unittest

from bot.rpg_v2.contracts import (
    CharacterClass,
    EventType,
    RuntimePhase,
    new_animation_event,
    new_player_record,
    new_runtime_snapshot,
    validate_animation_event,
    validate_player_record,
    validate_runtime_snapshot,
)


class RpgV2ContractTests(unittest.TestCase):
    def test_new_player_is_minimal_adventurer(self):
        player = new_player_record("1234", "Viewer", now="2026-07-17T00:00:00Z")

        self.assertEqual(player["class"], CharacterClass.ADVENTURER.value)
        self.assertEqual(player["level"], 1)
        self.assertEqual(player["xp"], 0)
        self.assertNotIn("salary_claimed_this_stream", player)
        self.assertNotIn("class_change_tokens", player)

    def test_player_rejects_unknown_class(self):
        player = new_player_record("1234", "Viewer")
        player["class"] = "revenant"

        with self.assertRaisesRegex(ValueError, "unknown character class"):
            validate_player_record(player)

    def test_runtime_enforces_micro_strip_actor_limits(self):
        runtime = new_runtime_snapshot()
        runtime["active_party"] = [{"id": str(index)} for index in range(5)]

        with self.assertRaisesRegex(ValueError, "four actors"):
            validate_runtime_snapshot(runtime)

    def test_runtime_defaults_to_wandering(self):
        runtime = new_runtime_snapshot(now="2026-07-17T00:00:00Z")

        self.assertEqual(runtime["phase"], RuntimePhase.WANDER.value)
        self.assertEqual(runtime["last_event_sequence"], 0)

    def test_animation_event_is_ordered_and_json_safe(self):
        event = new_animation_event(
            EventType.DAMAGE_APPLIED,
            battle_id="battle-1",
            round_number=2,
            sequence=7,
            actor_id="viewer-1",
            target_ids=["slime-1"],
            effect="strike",
            values={"damage": 4},
            now="2026-07-17T00:00:00Z",
        )

        validate_animation_event(event)
        self.assertEqual(event["sequence"], 7)
        self.assertEqual(event["values"], {"damage": 4})


if __name__ == "__main__":
    unittest.main()
