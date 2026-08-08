import unittest
from datetime import datetime, timedelta, timezone

from bot.gamewatch import football_updates, format_update, is_watchable, mlb_updates, should_announce
from bot.sports_api import _mlb_team_has_baserunner


def game(sport="NHL", home=0, away=0, period=1, completed=False, state="in"):
    return {
        "id": "1", "sport": sport, "home": "Home", "away": "Away",
        "home_score": home, "away_score": away, "period": period,
        "completed": completed, "state": state, "detail": "2nd 4:20",
        "start_time": datetime.now(timezone.utc),
    }


class GameWatchPolicyTests(unittest.TestCase):
    def test_game_unlocks_fifteen_minutes_before_start(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(is_watchable({**game(state="pre"), "start_time": now + timedelta(minutes=15)}, now))
        self.assertFalse(is_watchable({**game(state="pre"), "start_time": now + timedelta(minutes=16)}, now))

    def test_non_basketball_announces_every_score(self):
        self.assertTrue(should_announce(game(), game(home=1), 10))

    def test_nba_uses_point_time_and_lead_gates(self):
        previous = game("NBA", home=20, away=15)
        self.assertFalse(should_announce(previous, game("NBA", home=24, away=19), 30))
        self.assertTrue(should_announce(previous, game("NBA", home=25, away=20), 30))
        self.assertTrue(should_announce(previous, game("NBA", home=24, away=19), 180))
        self.assertTrue(should_announce(previous, game("NBA", home=20, away=21), 30))

    def test_period_and_final_always_announce(self):
        self.assertTrue(should_announce(game(), game(period=2), 1))
        self.assertTrue(should_announce(game(), game(completed=True, state="post"), 1))

    def test_update_contains_score_and_summary(self):
        text = format_update(game(home=3, away=2))
        self.assertEqual("GameWatch NHL: Away 2, Home 3. 2nd 4:20.", text)

    def test_mlb_does_not_announce_inning_or_pitch_noise(self):
        previous = game("MLB", period=1)
        current = {**game("MLB", period=2), "detail": "Pitch 1 : Strike 1 Looking"}
        self.assertFalse(should_announce(previous, current, 600))
        self.assertEqual([], mlb_updates(previous, current))

    def test_mlb_scoring_update_uses_scoring_play(self):
        previous = {**game("MLB"), "home_team_id": "1", "away_team_id": "2"}
        current = {
            **game("MLB", home=2),
            "home_team_id": "1",
            "away_team_id": "2",
            "scoring_plays": [{
                "team_id": "1", "runs": 2, "home_score": 2,
                "away_score": 0, "text": "Smith homered, Jones scored.",
            }],
        }
        self.assertEqual(
            ["GameWatch MLB: Away 0, Home 2. Smith homered, Jones scored."],
            mlb_updates(previous, current),
        )

    def test_mlb_scoring_play_must_match_scoring_team_and_score(self):
        previous = {
            **game("MLB", home=3, away=0),
            "home_team_id": "29", "away_team_id": "25",
        }
        current = {
            **game("MLB", home=3, away=1),
            "home": "Diamondbacks", "away": "Padres",
            "home_team_id": "29", "away_team_id": "25",
            "scoring_plays": [
                {"team_id": "25", "runs": 1, "home_score": 3, "away_score": 1, "text": "Campusano singled, France scored."},
                {"team_id": "29", "runs": 3, "home_score": 3, "away_score": 0, "text": "Tawa homered, two scored."},
            ],
        }
        self.assertEqual(
            ["GameWatch MLB: Padres 1, Diamondbacks 3. Campusano singled, France scored."],
            mlb_updates(previous, current),
        )

    def test_mlb_pitching_change_and_milestone_are_announced(self):
        previous = {
            **game("MLB"),
            "current_pitchers": {"1": {"id": "10", "name": "Old Arm", "team": "Home"}},
            "milestones": [],
        }
        current = {
            **game("MLB"),
            "current_pitchers": {"1": {"id": "11", "name": "New Arm", "team": "Home"}},
            "milestones": [{"key": "11:no-hitter", "kind": "no-hitter", "pitcher": "New Arm", "team": "Home", "innings": 6.0}],
        }
        updates = mlb_updates(previous, current)
        self.assertIn("GameWatch MLB pitching change: New Arm replaces Old Arm for the Home.", updates)
        self.assertIn("GameWatch MLB no-hitter watch: New Arm of the Home remains in after 6 hitless innings.", updates)

    def test_perfect_game_inference_detects_non_hit_baserunners(self):
        clean = [{"team": {"id": "2"}, "type": {"type": "strikeout"}, "text": "Smith struck out."}]
        walk = [{"team": {"id": "2"}, "type": {"type": "play-result"}, "text": "Smith walked."}]
        self.assertFalse(_mlb_team_has_baserunner(clean, "2"))
        self.assertTrue(_mlb_team_has_baserunner(walk, "2"))

    def test_football_reports_score_without_duplicate_play_message(self):
        previous = {**game("NFL"), "last_play_id": "10"}
        current = {**game("NFL", home=7), "last_play_id": "11", "last_play_text": "Smith 25 yard touchdown run", "last_play_yards": 25}
        updates = football_updates(previous, current)
        self.assertEqual(1, len(updates))
        self.assertIn("touchdown", updates[0])

    def test_football_reports_turnover_and_big_play(self):
        previous = {**game("NFL"), "last_play_id": "10"}
        turnover = {**game("NFL"), "last_play_id": "11", "last_play_text": "Pass intercepted by Jones", "last_play_turnover": True}
        big_play = {**game("NFL"), "last_play_id": "12", "last_play_text": "Smith run for 32 yards", "last_play_yards": 32}
        self.assertIn("Turnover", football_updates(previous, turnover)[0])
        self.assertIn("Big play", football_updates(turnover, big_play)[0])

    def test_football_reports_quarter_and_halftime_boundaries(self):
        first = game("NFL", period=1)
        second = game("NFL", period=2)
        third = game("NFL", period=3)
        self.assertIn("End of the 1st quarter", football_updates(first, second)[0])
        self.assertIn("Halftime", football_updates(second, third)[0])


if __name__ == "__main__":
    unittest.main()
