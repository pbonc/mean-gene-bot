import tempfile
import unittest
from pathlib import Path

import bot.wot_operations as operations


class WotOperationTests(unittest.TestCase):
    def setUp(self):
        self.original_file = operations.RESULTS_FILE
        self.temp_dir = tempfile.TemporaryDirectory()
        operations.RESULTS_FILE = Path(self.temp_dir.name) / "results.json"

    def tearDown(self):
        operations.RESULTS_FILE = self.original_file
        self.temp_dir.cleanup()

    def test_results_are_recorded_and_aggregated_case_insensitively(self):
        operations.record_operation({"agent": "Alice", "outcome": "pass"})
        operations.record_operation({"agent": "alice", "outcome": "fail"})
        operations.record_operation({"agent": "Bob", "outcome": "pass"})
        stats = operations.operation_stats()
        self.assertEqual(3, stats["total"])
        self.assertEqual(1, stats["agents"]["alice"]["pass"])
        self.assertEqual(1, stats["agents"]["alice"]["fail"])

    def test_agent_and_outcome_are_required(self):
        with self.assertRaises(ValueError):
            operations.record_operation({"agent": "", "outcome": "pass"})
        with self.assertRaises(ValueError):
            operations.record_operation({"agent": "Alice", "outcome": ""})


if __name__ == "__main__":
    unittest.main()
