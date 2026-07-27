import os
import sys
import unittest

# Allow running directly
workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, workspace_root)

from bot.commands.walkin import _parse_walkin_args


class WalkinParseTests(unittest.TestCase):
    def check(self, msg, expected):
        self.assertEqual(_parse_walkin_args(msg), expected)

    def test_valid_forms(self):
        self.check('!walkin @dar !fe "Hello there"', ('dar', 'fe', 'Hello there'))
        self.check('!walkin @DAR !Fe "Hello there"', ('dar', 'fe', 'Hello there'))
        self.check('!walkin !rainbow "Yay"', (None, 'rainbow', 'Yay'))
        self.check('!walkin @user123 !sfx-1 "A B C"', ('user123', 'sfx-1', 'A B C'))

    def test_invalid_forms(self):
        self.check('!walkin', (None, None, None))
        self.check('!walkin @dar !fe', (None, None, None))
        self.check('!walkin @dar "Hello"', (None, None, None))


if __name__ == '__main__':
    unittest.main()
