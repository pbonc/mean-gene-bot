import unittest

from bot.twitch_watchdog import TwitchWatchdogState, WatchdogAction


class TwitchWatchdogStateTests(unittest.TestCase):
    def test_healthy_observation_does_not_start_disconnect(self):
        state = TwitchWatchdogState(grace_seconds=300)

        result = state.observe(unhealthy=False, now=100.0)

        self.assertEqual(result.action, WatchdogAction.HEALTHY)
        self.assertIsNone(state.disconnected_since)

    def test_disconnect_waits_during_grace_period(self):
        state = TwitchWatchdogState(grace_seconds=300)

        started = state.observe(unhealthy=True, now=100.0)
        waiting = state.observe(unhealthy=True, now=399.9)

        self.assertEqual(started.action, WatchdogAction.DISCONNECT_STARTED)
        self.assertEqual(waiting.action, WatchdogAction.WAITING)
        self.assertAlmostEqual(waiting.disconnected_for, 299.9)

    def test_recovery_resets_disconnect_timer(self):
        state = TwitchWatchdogState(grace_seconds=300)
        state.observe(unhealthy=True, now=100.0)

        recovered = state.observe(unhealthy=False, now=220.0)
        next_disconnect = state.observe(unhealthy=True, now=500.0)

        self.assertEqual(recovered.action, WatchdogAction.RECOVERED)
        self.assertEqual(recovered.disconnected_for, 120.0)
        self.assertEqual(next_disconnect.action, WatchdogAction.DISCONNECT_STARTED)
        self.assertEqual(state.disconnected_since, 500.0)

    def test_sustained_disconnect_escalates_at_grace_boundary(self):
        state = TwitchWatchdogState(grace_seconds=300)
        state.observe(unhealthy=True, now=100.0)

        result = state.observe(unhealthy=True, now=400.0)

        self.assertEqual(result.action, WatchdogAction.GRACE_EXCEEDED)
        self.assertEqual(result.disconnected_for, 300.0)

    def test_rejects_non_positive_grace_period(self):
        with self.assertRaises(ValueError):
            TwitchWatchdogState(grace_seconds=0)


if __name__ == "__main__":
    unittest.main()
