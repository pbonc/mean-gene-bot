import unittest

from bot.commands.icyhot import ICY_EMOTE, TWITCH_MESSAGE_LIMIT, icyhot_message


class IcyHotCommandTests(unittest.TestCase):
    def test_message_uses_maximum_number_of_emotes_under_limit(self):
        message = icyhot_message()
        emotes = message.split()

        self.assertEqual(len(message), 499)
        self.assertLessEqual(len(message), TWITCH_MESSAGE_LIMIT)
        self.assertEqual(emotes, [ICY_EMOTE] * 50)
        self.assertGreater(len(message + " " + ICY_EMOTE), TWITCH_MESSAGE_LIMIT)


if __name__ == "__main__":
    unittest.main()
