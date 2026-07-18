import unittest

from bot.rpg_v2.classes import friendly_skills
from bot.rpg_v2.engine import BattleEngine, make_enemy, make_friendly
from bot.rpg_v2.models import Side


class BattleEngineTests(unittest.TestCase):
    def test_every_friendly_class_has_exactly_three_numbered_skills(self):
        expected = {
            "adventurer": ["Strike", "Brace", "Rally"],
            "warrior": ["Slash", "Guard Ally", "Shield Slam"],
            "mage": ["Arcane Bolt", "Fireball", "Focus"],
            "healer": ["Smite", "Heal", "Group Heal"],
            "ranger": ["Quick Shot", "Mark Target", "Volley"],
        }
        for kind, labels in expected.items():
            skills = friendly_skills(kind)
            self.assertEqual([skill.number for skill in skills], [1, 2, 3])
            self.assertEqual([skill.label for skill in skills], labels)

    def test_speed_and_actor_id_produce_stable_turn_order(self):
        engine = BattleEngine(
            "battle-order",
            [make_friendly("r2", "Ranger Two", "ranger"), make_friendly("r1", "Ranger One", "ranger")],
            [make_enemy("slime", "Slime", "slime")],
        )

        self.assertEqual(engine.current_actor().actor_id, "r1")
        engine.resolve_current_turn()
        self.assertEqual(engine.current_actor().actor_id, "r2")

    def test_active_viewer_prompt_has_three_choices_and_class_default(self):
        engine = BattleEngine(
            "battle-prompt",
            [make_friendly("viewer", "Viewer", "warrior")],
            [make_enemy("slime", "Slime", "slime")],
        )

        prompt = engine.turn_prompt(waits_for_viewer=True, deadline="2026-07-18T12:00:08Z")

        self.assertEqual(prompt["actor_id"], "viewer")
        self.assertEqual([choice["number"] for choice in prompt["choices"]], [1, 2, 3])
        self.assertEqual(prompt["default_choice"], 1)
        self.assertEqual(engine.events[-1]["type"], "turn_prompted")

    def test_healer_default_changes_to_heal_when_ally_is_wounded(self):
        healer = make_friendly("healer", "Healer", "healer")
        warrior = make_friendly("warrior", "Warrior", "warrior")
        warrior.hp -= 10
        engine = BattleEngine("battle-heal", [healer, warrior], [make_enemy("ogre", "Ogre", "ogre")])
        # Ranger/other actors are absent; Healer is faster than Warrior and acts first.
        prompt = engine.turn_prompt(waits_for_viewer=False)

        self.assertEqual(prompt["default_choice"], 2)
        before = engine.actor_by_id("warrior").hp
        engine.resolve_current_turn()
        self.assertGreater(engine.actor_by_id("warrior").hp, before)

    def test_invalid_choice_is_rejected_without_consuming_turn(self):
        engine = BattleEngine(
            "battle-invalid",
            [make_friendly("viewer", "Viewer")],
            [make_enemy("slime", "Slime", "slime")],
        )

        with self.assertRaisesRegex(ValueError, "invalid skill choice"):
            engine.resolve_current_turn(9)
        self.assertEqual(engine.current_actor().actor_id, "viewer")
        self.assertEqual(engine.turns_resolved, 0)

    def test_all_three_skills_for_every_class_resolve(self):
        for kind in ("adventurer", "warrior", "mage", "healer", "ranger"):
            for choice in (1, 2, 3):
                with self.subTest(kind=kind, choice=choice):
                    engine = BattleEngine(
                        f"battle-{kind}-{choice}",
                        [make_friendly("viewer", "Viewer", kind)],
                        [make_enemy("ogre", "Ogre", "ogre")],
                        seed=choice,
                    )
                    events = engine.resolve_current_turn(choice)
                    self.assertEqual(events[0]["type"], "skill_selected")
                    self.assertEqual(engine.turns_resolved, 1)

    def test_every_enemy_kind_can_auto_act(self):
        for kind in ("slime", "goblin", "ogre"):
            with self.subTest(kind=kind):
                friendly = make_friendly("viewer", "Viewer")
                friendly.speed = 1
                engine = BattleEngine(
                    f"battle-enemy-{kind}",
                    [friendly],
                    [make_enemy("enemy", kind.title(), kind)],
                    seed=2,
                )
                self.assertEqual(engine.current_actor().side, Side.ENEMY)
                events = engine.resolve_current_turn()
                self.assertEqual(events[0]["type"], "default_selected")

    def test_absent_viewer_default_advances_battle(self):
        engine = BattleEngine(
            "battle-default",
            [make_friendly("viewer", "Viewer")],
            [make_enemy("slime", "Slime", "slime")],
            seed=4,
        )

        events = engine.resolve_current_turn()

        self.assertEqual(events[0]["type"], "default_selected")
        self.assertEqual(engine.turns_resolved, 1)
        self.assertLess(engine.actor_by_id("slime").hp, engine.actor_by_id("slime").max_hp)

    def test_shield_absorbs_damage(self):
        engine = BattleEngine(
            "battle-shield",
            [make_friendly("viewer", "Viewer")],
            [make_enemy("slime", "Slime", "slime")],
            seed=2,
        )
        engine.resolve_current_turn(2)  # Adventurer Brace
        # Slime acts next.
        hp_before = engine.actor_by_id("viewer").hp
        engine.resolve_current_turn()

        self.assertEqual(engine.actor_by_id("viewer").hp, hp_before)
        self.assertLess(engine.actor_by_id("viewer").shield, 8)

    def test_seeded_simulations_are_identical(self):
        def simulate():
            engine = BattleEngine(
                "battle-seeded",
                [
                    make_friendly("a", "A", "adventurer"),
                    make_friendly("w", "W", "warrior"),
                    make_friendly("m", "M", "mage"),
                    make_friendly("h", "H", "healer"),
                    make_friendly("r", "R", "ranger"),
                ],
                [make_enemy("g1", "Goblin", "goblin"), make_enemy("o1", "Ogre", "ogre")],
                seed=99,
            )
            return engine.run_to_completion()

        first = simulate()
        second = simulate()
        self.assertEqual((first.outcome, first.rounds, first.turns), (second.outcome, second.rounds, second.turns))
        self.assertEqual(first.events, second.events)

    def test_large_uncapped_roster_completes(self):
        friendlies = [make_friendly(f"viewer-{index}", f"Viewer {index}") for index in range(150)]
        enemies = [make_enemy(f"ogre-{index}", f"Ogre {index}", "ogre") for index in range(20)]
        engine = BattleEngine("battle-large", friendlies, enemies, seed=12)

        result = engine.run_to_completion(max_rounds=50)

        self.assertEqual(result.outcome, "victory")
        self.assertGreater(result.turns, 0)
        self.assertEqual(result.events[-1]["type"], "battle_finished")

    def test_event_sequences_are_monotonic(self):
        engine = BattleEngine(
            "battle-events",
            [make_friendly("viewer", "Viewer", "mage")],
            [make_enemy("slime", "Slime", "slime")],
            seed=1,
        )
        result = engine.run_to_completion()

        sequences = [event["sequence"] for event in result.events]
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))

    def test_max_rounds_protects_against_stalemate(self):
        engine = BattleEngine(
            "battle-stalemate",
            [make_friendly("viewer", "Viewer")],
            [make_enemy("ogre", "Ogre", "ogre")],
            seed=1,
        )

        result = engine.run_to_completion(max_rounds=1)

        self.assertEqual(result.outcome, "stalemate")
        self.assertEqual(result.rounds, 1)

    def test_victory_and_defeat_paths(self):
        victory = BattleEngine(
            "battle-victory",
            [make_friendly("mage", "Mage", "mage")],
            [make_enemy("slime", "Slime", "slime")],
            seed=5,
        ).run_to_completion()
        weak = make_friendly("weak", "Weak")
        weak.hp = 1
        defeat = BattleEngine(
            "battle-defeat",
            [weak],
            [make_enemy("ogre", "Ogre", "ogre")],
            seed=5,
        ).run_to_completion()

        self.assertEqual(victory.outcome, "victory")
        self.assertEqual(defeat.outcome, "defeat")


if __name__ == "__main__":
    unittest.main()
