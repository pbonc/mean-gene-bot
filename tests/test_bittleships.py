import json
import random
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from bot.bittleships_state import CLASSIC_FLEET, BittleshipsManager, parse_coordinate


class BittleshipsManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = str(Path(self.temp_dir.name) / "bittleships.json")
        self.manager = BittleshipsManager(
            state_file=self.state_file,
            rng=random.Random(47),
        )
        self.manager.set_admiral("TheAdmiral")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_coordinate_parser_accepts_standard_grid_values(self):
        self.assertEqual(parse_coordinate("a1"), "A1")
        self.assertEqual(parse_coordinate(" J10 "), "J10")
        self.assertIsNone(parse_coordinate("K1"))
        self.assertIsNone(parse_coordinate("A11"))

    def test_start_places_unique_one_cell_ships(self):
        self.manager.start_game(3)
        self.assertTrue(self.manager.state["active"])
        self.assertEqual(len(self.manager.state["ships"]), 3)
        self.assertEqual(len(set(self.manager.state["ships"])), 3)

    def test_admiral_cannot_receive_or_fire_shots(self):
        self.manager.start_game(3)
        with self.assertRaisesRegex(ValueError, "admiral"):
            self.manager.grant_shots("theAdmiral")
        with self.assertRaisesRegex(ValueError, "admiral"):
            self.manager.fire("THEADMIRAL", "A1")

    def test_shot_is_consumed_and_duplicate_cell_is_rejected(self):
        self.manager.start_game(3)
        self.manager.grant_shots("viewer", 2)
        coordinate = self.manager.state["ships"][0]
        result, remaining, won = self.manager.fire("viewer", coordinate)
        self.assertEqual(result, "hit")
        self.assertEqual(remaining, 1)
        self.assertFalse(won)
        with self.assertRaisesRegex(ValueError, "already"):
            self.manager.fire("viewer", coordinate)
        self.assertEqual(self.manager.state["shots"]["viewer"], 1)

    def test_last_hit_ends_game_and_clears_pending_shots(self):
        self.manager.start_game(1)
        self.manager.grant_shots("viewer", 2)
        result, remaining, won = self.manager.fire("viewer", self.manager.state["ships"][0])
        self.assertEqual(result, "hit")
        self.assertEqual(remaining, 1)
        self.assertTrue(won)
        self.assertFalse(self.manager.state["active"])
        self.assertEqual(self.manager.state["shots"], {})

    def test_public_payload_never_exposes_hidden_ship_coordinates(self):
        self.manager.start_game(3)
        payload = self.manager.public_payload()
        serialized = json.dumps(payload)
        for coordinate in self.manager.state["ships"]:
            self.assertNotIn(coordinate, serialized)
        self.assertNotIn("ships", payload)

    def test_state_survives_reload(self):
        self.manager.start_game(3)
        self.manager.grant_shots("viewer")
        reloaded = BittleshipsManager(state_file=self.state_file)
        self.assertEqual(reloaded.admiral, "theadmiral")
        self.assertEqual(reloaded.state["shots"]["viewer"], 1)
        self.assertEqual(len(reloaded.state["ships"]), 3)

    def _start_classic(self, players=("alpha",), fighter=False):
        self.manager.start_classic_join(3, fighter_enabled=fighter)
        for player in players:
            self.manager.join_classic(player)
        return self.manager.begin_classic()

    def test_classic_fleet_has_standard_lengths_without_overlap(self):
        self.manager.start_classic_join(3)
        fleet = self.manager.state["ships"]
        self.assertEqual(
            [(ship["name"], ship["length"]) for ship in fleet],
            [
                ("Destroyer", 2),
                ("Submarine", 3),
                ("Cruiser", 3),
                ("Battleship", 4),
                ("Aircraft Carrier", 5),
            ],
        )
        all_cells = [cell for ship in fleet for cell in ship["cells"]]
        self.assertEqual(len(all_cells), 17)
        self.assertEqual(len(set(all_cells)), 17)

    def test_classic_join_allows_admiral_but_rejects_duplicates(self):
        self.manager.start_classic_join(3)
        self.manager.join_classic("theadmiral")
        self.manager.join_classic("viewer")
        with self.assertRaisesRegex(ValueError, "already"):
            self.manager.join_classic("VIEWER")

    def test_classic_enforces_randomized_turn_order(self):
        order = self._start_classic(players=("alpha", "bravo"))
        wrong_player = next(player for player in ("alpha", "bravo") if player != order[0])
        with self.assertRaisesRegex(ValueError, "turn"):
            self.manager.classic_fire(wrong_player, "A1")

    def test_classic_join_before_first_shot_enters_current_round(self):
        order = list(self._start_classic(players=("alpha", "bravo")))
        self.manager.join_classic("charlie")
        self.assertEqual(self.manager.state["classic"]["turn_order"], order + ["charlie"])
        self.assertEqual(self.manager.state["classic"]["pending_players"], [])

    def test_classic_join_after_first_shot_enters_end_of_next_round(self):
        order = list(self._start_classic(players=("alpha", "bravo")))
        occupied = {
            cell
            for ship in self.manager.state["ships"]
            for cell in ship["cells"]
        }
        miss = next(
            cell
            for cell in (f"{letter}{number}" for letter in "ABCDEFGHIJ" for number in range(1, 11))
            if cell not in occupied
        )
        self.manager.classic_fire(order[0], miss)
        self.manager.join_classic("charlie")
        self.assertEqual(self.manager.state["classic"]["turn_order"], order)
        self.assertEqual(self.manager.state["classic"]["pending_players"], ["charlie"])

        self.manager.skip_classic_turn()
        self.assertEqual(self.manager.state["classic"]["turn_order"], order + ["charlie"])
        self.assertEqual(self.manager.state["classic"]["turn_index"], 0)
        self.assertEqual(self.manager.state["classic"]["pending_players"], [])

    def test_queued_classic_join_survives_reload(self):
        order = self._start_classic(players=("alpha", "bravo"))
        self.manager.classic_fire(order[0], "A1")
        self.manager.join_classic("charlie")
        reloaded = BittleshipsManager(state_file=self.state_file)
        self.assertEqual(reloaded.state["classic"]["pending_players"], ["charlie"])

    def test_classic_turn_gets_one_minute_deadline(self):
        self._start_classic()
        deadline = datetime.fromisoformat(self.manager.state["classic"]["turn_deadline"])
        seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
        self.assertGreater(seconds, 59)
        self.assertLessEqual(seconds, 60)

    def test_timeout_skip_advances_turn_and_rejects_stale_timer(self):
        order = self._start_classic(players=("alpha", "bravo"))
        classic = self.manager.state["classic"]
        expired_player = order[0]
        expired_deadline = classic["turn_deadline"]
        skipped = self.manager.skip_classic_turn(
            expected_player=expired_player,
            expected_deadline=expired_deadline,
        )
        self.assertEqual(skipped, expired_player)
        self.assertEqual(
            self.manager.state["classic"]["turn_order"][self.manager.state["classic"]["turn_index"]],
            order[1],
        )
        with self.assertRaisesRegex(ValueError, "already advanced|no longer current"):
            self.manager.skip_classic_turn(
                expected_player=expired_player,
                expected_deadline=expired_deadline,
            )

    def test_assigning_player_as_admiral_keeps_them_in_classic_turn_order(self):
        order = self._start_classic(players=("alpha", "bravo"))
        self.manager.set_admiral("alpha")
        classic = self.manager.state["classic"]
        self.assertIn("alpha", classic["players"])
        self.assertEqual(classic["turn_order"], order)
        self.assertIn("alpha", classic["scores"])

    def test_admiral_can_fire_on_their_enforced_classic_turn(self):
        order = self._start_classic(players=("theadmiral", "bravo"))
        if order[0] != "theadmiral":
            self.manager.skip_classic_turn()
        outcome = self.manager.classic_fire("theadmiral", "A1")
        self.assertIn(outcome["result"], ("hit", "miss"))

    def test_classic_sink_awards_hit_and_bonus_point(self):
        self._start_classic()
        destroyer = self.manager.state["ships"][0]
        first = self.manager.classic_fire("alpha", destroyer["cells"][0])
        second = self.manager.classic_fire("alpha", destroyer["cells"][1])
        self.assertEqual(first["score"]["points"], 1)
        self.assertEqual(second["sunk"], "Destroyer")
        self.assertEqual(second["score"], {"hits": 2, "sinks": 1, "points": 3})

    def test_fighter_moves_after_round_and_awards_destroy_bonus(self):
        self._start_classic(fighter=True)
        classic = self.manager.state["classic"]
        original = classic["fighter_cell"]
        occupied = {cell for ship in self.manager.state["ships"] for cell in ship["cells"]}
        miss = next(
            cell for cell in (f"{letter}{number}" for letter in "ABCDEFGHIJ" for number in range(1, 11))
            if cell not in occupied and cell != original
        )
        self.manager.classic_fire("alpha", miss)
        moved = self.manager.state["classic"]["fighter_cell"]
        self.assertNotEqual(moved, original)
        outcome = self.manager.classic_fire("alpha", moved)
        self.assertEqual(outcome["sunk"], "Fighter")
        self.assertEqual(outcome["bonus"], 1)
        self.assertFalse(self.manager.state["classic"]["fighter_alive"])

    def test_classic_ends_when_all_five_ships_are_sunk(self):
        self._start_classic()
        last_outcome = None
        for ship in self.manager.state["ships"]:
            for cell in ship["cells"]:
                last_outcome = self.manager.classic_fire("alpha", cell)
        self.assertTrue(last_outcome["won"])
        self.assertEqual(self.manager.state["phase"], "ended")
        score = self.manager.state["classic"]["scores"]["alpha"]
        self.assertEqual(score, {"hits": 17, "sinks": 5, "points": 22})

    def test_tied_fleet_destruction_starts_fighter_sudden_death(self):
        order = self._start_classic(players=("alpha", "bravo"))
        classic = self.manager.state["classic"]
        classic["scores"]["alpha"] = {"hits": 1, "sinks": 0, "points": 20}
        classic["scores"]["bravo"] = {"hits": 0, "sinks": 0, "points": 22}
        classic["sunk"] = [name for name, _ in CLASSIC_FLEET[:-1]]
        last_ship = self.manager.state["ships"][-1]
        for cell in last_ship["cells"][:-1]:
            self.manager.state["revealed"][cell] = {
                "result": "hit", "target": last_ship["name"], "player": "alpha"
            }
        classic["turn_index"] = order.index("alpha")

        outcome = self.manager.classic_fire("alpha", last_ship["cells"][-1])

        self.assertFalse(outcome["won"])
        self.assertTrue(outcome["sudden_death_started"])
        self.assertTrue(classic["fighter_alive"])
        self.assertEqual(set(classic["sudden_death_players"]), {"alpha", "bravo"})
        self.assertEqual(outcome["next_player"], "bravo")
        self.assertEqual(self.manager.state["phase"], "playing")

    def test_first_sudden_death_fighter_hit_wins(self):
        order = self._start_classic(players=("alpha", "bravo"), fighter=True)
        classic = self.manager.state["classic"]
        classic["sudden_death"] = True
        classic["sudden_death_players"] = list(order)
        classic["turn_index"] = 0
        shooter = order[0]

        outcome = self.manager.classic_fire(shooter, classic["fighter_cell"])

        self.assertTrue(outcome["won"])
        self.assertEqual(outcome["winner"], shooter)
        self.assertEqual(self.manager.state["phase"], "ended")

    def test_classic_public_payload_hides_fleet_and_fighter_positions(self):
        self.manager.start_classic_join(3, fighter_enabled=True)
        payload_text = json.dumps(self.manager.public_payload())
        for ship in self.manager.state["ships"]:
            for cell in ship["cells"]:
                self.assertNotIn(cell, payload_text)
        self.assertNotIn(self.manager.state["classic"]["fighter_cell"], payload_text)

    def test_classic_suspends_and_restores_persistent_giveaway(self):
        self.manager.start_game(4)
        self.manager.grant_shots("viewer", 2)
        giveaway_before = {
            key: deepcopy(self.manager.state[key])
            for key in (
                "mode", "phase", "active", "ship_count", "ships", "shots",
                "revealed", "hits", "misses", "classic", "started_at",
            )
        }
        self.manager.start_classic_join(3, fighter_enabled=True)
        self.manager.join_classic("classicplayer")
        self.manager.begin_classic()
        self.manager.classic_fire(
            "classicplayer",
            self.manager.state["ships"][0]["cells"][0],
        )
        self.assertTrue(self.manager.restore_suspended_game())
        for key, expected in giveaway_before.items():
            self.assertEqual(self.manager.state[key], expected)
        self.assertIsNone(self.manager.state["suspended_game"])

    def test_suspended_giveaway_survives_restart_during_classic(self):
        self.manager.start_game(3)
        original_ships = deepcopy(self.manager.state["ships"])
        self.manager.grant_shots("viewer", 3)
        self.manager.start_classic_join(3)
        reloaded = BittleshipsManager(state_file=self.state_file)
        self.assertTrue(reloaded.restore_suspended_game())
        self.assertEqual(reloaded.state["ships"], original_ships)
        self.assertEqual(reloaded.state["shots"], {"viewer": 3})
        self.assertEqual(reloaded.state["mode"], "single")


class BittleshipsOverlayTests(unittest.TestCase):
    def test_classic_player_list_renders_every_player_without_scrolling(self):
        overlay = (
            Path(__file__).resolve().parents[1]
            / "bot"
            / "overlay_static"
            / "bittleships_overlay.html"
        ).read_text(encoding="utf-8")

        self.assertIn("for (const [index, player] of players.entries())", overlay)
        self.assertNotIn(".slice(0, 6)", overlay)
        self.assertIn("--leader-columns", overlay)
        self.assertIn("overflow-wrap: anywhere", overlay)


if __name__ == "__main__":
    unittest.main()
