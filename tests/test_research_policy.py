import unittest

from bot.research_policy import classify_research_request


class ResearchPolicyTests(unittest.TestCase):
    def assert_required(self, text):
        decision = classify_research_request(text)
        self.assertTrue(decision.research_required, text)
        self.assertIsNotNone(decision.category)
        self.assertIsNotNone(decision.rule)

    def assert_not_required(self, text):
        self.assertFalse(classify_research_request(text).research_required, text)

    def test_high_confidence_requests(self):
        for text in (
            "who won the Phillies game last night?",
            "What was the Twins score last night?",
            "What are the current MLB standings?",
            "Look up the tallest building in Iowa",
            "What is Bitcoin trading at right now?",
            "What are today's breaking news headlines?",
        ):
            with self.subTest(text=text):
                self.assert_required(text)

    def test_known_false_positives(self):
        for text in (
            "What did you do last night?",
            "Tell me a joke about last night.",
            "Who won in that movie last night?",
            'Explain the quote "today is a gift".',
            "In our fictional roleplay, who won the game?",
            "What is a vinyl record?",
            "Do you like the current Phillies uniforms?",
        ):
            with self.subTest(text=text):
                self.assert_not_required(text)

    def test_temporal_sports_participation_requires_research(self):
        for text in (
            "did the Vikings play yesterday?",
            "did Minnesota play last night?",
            "did the Yankees play yesterday?",
            "who did the Twins play yesterday?",
            "are the Vikings playing tonight?",
            "did the Gophers play yesterday?",
            "did Manchester United play yesterday?",
            "what team did the Wild play last night?",
            "was there a Vikings game yesterday?",
            "was there a Twins game last night?",
            "when did the Phillies play yesterday?",
            "did the Moon Dogs play yesterday?",
            "was there a Moon Dogs matchup last night?",
        ):
            with self.subTest(text=text):
                decision = classify_research_request(text)
                self.assertTrue(decision.research_required)
                self.assertEqual(decision.category, "current_sports_result")
                self.assertEqual(decision.rule, "sports_temporal_participation")

    def test_non_sports_play_language_does_not_require_research(self):
        for text in (
            "play some music",
            "let's play Battlefield",
            "how do I play this game?",
            "what game should I play tonight?",
            "play the fart sound",
            "did you play my TTS?",
            "who played Darth Vader?",
            "the actor played Batman",
            "we played cards last night",
            "I played Battlefield yesterday",
        ):
            with self.subTest(text=text):
                self.assert_not_required(text)

    def test_participation_subject_is_structured_and_opponent_is_not_the_subject(self):
        decision = classify_research_request(
            "did the Minnesota Vikings play the Chicago Bears yesterday?"
        )
        self.assertEqual(decision.rule, "sports_temporal_participation")
        self.assertEqual(decision.queried_participant, "Minnesota Vikings")

        dual = classify_research_request(
            "did the Minnesota Vikings and Chicago Bears play yesterday?"
        )
        self.assertEqual(dual.rule, "sports_temporal_participation")
        self.assertIsNone(dual.queried_participant)


if __name__ == "__main__":
    unittest.main()
