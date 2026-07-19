import unittest

from bot.rpg_v2.contracts import (
    CharacterClass,
    EventType,
    RuntimePhase,
    new_animation_event,
    new_battle_overlay_snapshot,
    new_expedition_snapshot,
    new_player_record,
    new_runtime_snapshot,
    new_turn_prompt,
    validate_animation_event,
    validate_battle_overlay_snapshot,
    validate_expedition_snapshot,
    validate_player_record,
    validate_runtime_snapshot,
    validate_turn_prompt,
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

    def test_version_one_contract_is_explicitly_rejected(self):
        player = new_player_record("1234", "Viewer")
        player["version"] = 1

        with self.assertRaisesRegex(ValueError, "expected version 2"):
            validate_player_record(player)

    def test_runtime_accepts_uncapped_expedition_and_participant_rosters(self):
        runtime = new_runtime_snapshot()
        runtime["expedition"] = [{"actor_id": f"viewer-{index}"} for index in range(150)]
        runtime["participants"] = list(runtime["expedition"])
        runtime["enemies"] = [{"actor_id": f"enemy-{index}"} for index in range(20)]

        validate_runtime_snapshot(runtime)
        self.assertEqual(len(runtime["participants"]), 150)

    def test_runtime_defaults_to_journey_without_obsolete_party_fields(self):
        runtime = new_runtime_snapshot(now="2026-07-17T00:00:00Z")

        self.assertEqual(runtime["phase"], RuntimePhase.JOURNEY.value)
        self.assertEqual(runtime["last_event_sequence"], 0)
        self.assertNotIn("active_party", runtime)
        self.assertNotIn("reserve_count", runtime)

    def test_runtime_rejects_duplicate_actor_ids(self):
        runtime = new_runtime_snapshot()
        runtime["expedition"] = [{"actor_id": "same"}, {"actor_id": "same"}]

        with self.assertRaisesRegex(ValueError, "must be unique"):
            validate_runtime_snapshot(runtime)

    def test_turn_prompt_requires_exactly_three_numbered_choices(self):
        prompt = new_turn_prompt(
            battle_id="battle-1",
            turn_id="turn-1",
            actor_id="viewer-1",
            choices=[
                {"number": 1, "skill_id": "slash", "label": "Slash"},
                {"number": 2, "skill_id": "guard", "label": "Guard Ally"},
                {"number": 3, "skill_id": "shield_slam", "label": "Shield Slam"},
            ],
            default_choice=1,
            waits_for_viewer=True,
            deadline="2026-07-18T12:00:08Z",
        )

        validate_turn_prompt(prompt)
        self.assertEqual(prompt["default_choice"], 1)

    def test_absent_viewer_prompt_has_default_and_no_deadline(self):
        prompt = new_turn_prompt(
            battle_id="battle-1",
            turn_id="turn-2",
            actor_id="viewer-2",
            choices=[
                {"number": 1, "skill_id": "strike", "label": "Strike"},
                {"number": 2, "skill_id": "brace", "label": "Brace"},
                {"number": 3, "skill_id": "rally", "label": "Rally"},
            ],
            default_choice=1,
            waits_for_viewer=False,
        )

        self.assertIsNone(prompt["deadline"])

    def test_actor_choice_phase_requires_pending_turn(self):
        runtime = new_runtime_snapshot()
        runtime["phase"] = RuntimePhase.ACTOR_CHOICE.value

        with self.assertRaisesRegex(ValueError, "requires pending_turn"):
            validate_runtime_snapshot(runtime)

    def test_actor_choice_accepts_matching_participant_prompt(self):
        runtime = new_runtime_snapshot()
        runtime["battle_id"] = "battle-1"
        runtime["phase"] = RuntimePhase.ACTOR_CHOICE.value
        runtime["participants"] = [{"actor_id": "viewer-1"}]
        runtime["pending_turn"] = new_turn_prompt(
            battle_id="battle-1",
            turn_id="turn-1",
            actor_id="viewer-1",
            choices=[
                {"number": 1, "skill_id": "bolt", "label": "Arcane Bolt"},
                {"number": 2, "skill_id": "fireball", "label": "Fireball"},
                {"number": 3, "skill_id": "focus", "label": "Focus"},
            ],
            default_choice=1,
            waits_for_viewer=True,
            deadline="2026-07-18T12:00:08Z",
        )

        validate_runtime_snapshot(runtime)

    def test_expedition_snapshot_contract_is_uncapped(self):
        snapshot = new_expedition_snapshot(
            [
                {
                    "actor_id": f"viewer-{index}",
                    "display_name": f"Viewer{index}",
                    "class": "adventurer",
                    "presence": "active",
                    "last_seen_at": 1000.0,
                }
                for index in range(200)
            ],
            active_window_seconds=1200,
            walkoff_window_seconds=2700,
            now="2026-07-18T00:00:00Z",
        )

        validate_expedition_snapshot(snapshot)
        self.assertEqual(len(snapshot["members"]), 200)

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

    def test_battle_overlay_snapshot_contains_authoritative_actor_state(self):
        snapshot = new_battle_overlay_snapshot(
            battle_id="battle-1",
            phase=RuntimePhase.ACTION_PLAYBACK,
            round_number=3,
            friendlies=[{"actor_id": "viewer-1", "name": "Iamdar", "kind": "warrior", "side": "friendly", "hp": 42, "max_hp": 50, "shield": 6}],
            enemies=[{"actor_id": "slime-1", "name": "Slime", "kind": "slime", "side": "enemy", "hp": 9, "max_hp": 24, "shield": 0}],
            last_event_sequence=12,
            now="2026-07-18T00:00:00Z",
        )

        validate_battle_overlay_snapshot(snapshot)
        self.assertEqual(snapshot["friendlies"][0]["hp"], 42)
        self.assertEqual(snapshot["last_event_sequence"], 12)

    def test_battle_overlay_rejects_duplicate_ids_across_sides(self):
        actor = {"actor_id": "same", "name": "Same", "kind": "slime", "side": "friendly", "hp": 1, "max_hp": 1, "shield": 0}
        with self.assertRaisesRegex(ValueError, "must be unique"):
            new_battle_overlay_snapshot(
                battle_id="battle-1",
                phase=RuntimePhase.ACTION_PLAYBACK,
                round_number=1,
                friendlies=[actor],
                enemies=[{**actor, "side": "enemy"}],
            )


if __name__ == "__main__":
    unittest.main()
