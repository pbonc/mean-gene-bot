import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.commands import custom_text_cog as module


class FakeBot:
    def __init__(self):
        self.commands = {}

    def get_command(self, name):
        return self.commands.get(name)

    def add_command(self, command):
        self.commands[command.name] = command

    def remove_command(self, name):
        return self.commands.pop(name, None)


class CustomTextCogTests(unittest.TestCase):
    def test_barons_exact_response_is_present(self):
        self.assertIn(
            "Go say hi to Baron and Caerdwyn over on Picarto: https://picarto.tv/BaronEngel",
            module.CustomTextCog.baron_command._callback.__code__.co_consts,
        )

    def test_loads_and_registers_persisted_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "commands.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"hello2": {"response": "Hello!"}}, handle)
            with patch.object(module, "COMMAND_FILE", path):
                bot = FakeBot()
                cog = module.CustomTextCog(bot)
            self.assertIn("hello2", cog.entries)
            self.assertIn("hello2", bot.commands)

    def test_mod_or_broadcaster_permission(self):
        self.assertTrue(module._is_mod_or_broadcaster(SimpleNamespace(is_mod=True)))
        self.assertTrue(module._is_mod_or_broadcaster(SimpleNamespace(is_broadcaster=True)))
        self.assertFalse(module._is_mod_or_broadcaster(SimpleNamespace()))

    def test_rejects_control_and_bidi_characters(self):
        self.assertIsNotNone(module.FORBIDDEN_TEXT.search("bad\ntext"))
        self.assertIsNotNone(module.FORBIDDEN_TEXT.search("bad\u202etext"))
        self.assertIsNone(module.FORBIDDEN_TEXT.search("safe https://example.com text"))

    def test_management_and_baron_names_are_reserved(self):
        self.assertEqual({"baron", "cmd", "customcmd"}, module.RESERVED_NAMES)


if __name__ == "__main__":
    unittest.main()
