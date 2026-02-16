import sys
import os

# Allow running directly
workspace_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(workspace_root, 'bot'))

from commands.walkin import _parse_walkin_args


def check(msg, expected):
    got = _parse_walkin_args(msg)
    assert got == expected, f"For {msg!r}, expected {expected} but got {got}"


def main():
    # Basic cases
    check('!walkin @dar !fe "Hello there"', ('dar', 'fe', 'Hello there'))
    check('!walkin @DAR !Fe "Hello there"', ('dar', 'fe', 'Hello there'))
    check('!walkin !rainbow "Yay"', (None, 'rainbow', 'Yay'))
    check('!walkin @user123 !sfx-1 "A B C"', ('user123', 'sfx-1', 'A B C'))

    # Invalid forms
    assert _parse_walkin_args('!walkin') == (None, None, None)
    assert _parse_walkin_args('!walkin @dar !fe') == (None, None, None)
    assert _parse_walkin_args('!walkin @dar "Hello"') == (None, None, None)

    print('All walk-in parse tests passed.')


if __name__ == '__main__':
    main()
