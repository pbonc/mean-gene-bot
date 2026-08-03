import unittest
from datetime import datetime, timedelta, timezone

from bot.gamewatch import format_update, is_watchable, should_announce


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


if __name__ == "__main__":
    unittest.main()
