# Mean-Gene-Bot: Source of Truth

## Cog Loading (How Commands Are Registered)

- All Twitch commands are loaded via `src/twitch_commands/__init__.py` using the `load_all_cogs(bot)` function.
- Each command/cog module has a `prepare(bot)` function.
- Important: Each cog sets a unique attribute on the bot object (e.g. `_dah_cog_loaded` for DarsAgainstHumanity) **to prevent double registration**, no matter how Python imports or reloads the module.
- This is the best practice for TwitchIO bots with dynamic module loading.
- DO NOT reload cogs at runtime unless you explicitly unload them first.
- If you ever see double command execution, check:
  - Only one bot process is running.
  - The loader is only called once.
  - The per-cog `_xyz_cog_loaded` attribute is not being reset by a code reload or accidental bot recreation.

## Commands and Features

- `!dah`: Calls DarsAgainstHumanity cog, see `src/twitch_commands/dah.py`.
- Known edge case: If you hot-reload code without restarting the bot, registration guards may be bypassed. Always restart the bot after changing command/cog files.

## Best Practices

- Always add docs/notes here when you make a loader or core logic change.
- If you need to debug, log the bot's loaded cogs and check for duplicate keys.
- If you change the way cogs are loaded, update this file!
- **pbonc strongly prefers full file regenerations.** If you ask Copilot for a fix, always request a full file so you can copy, test, and verify one step at a time.

## For Copilot

- Read this file before suggesting loader changes, debug steps, or discussing command registration.
- pbonc wants full files for each step, not piecemeal snippets or multiple steps at once.
- After a file is pasted and tested, only then move to the next step if another issue remains.
- **Avoid any language like "final fix", "guaranteed", or similar in answers. Do not claim a solution is final, done, or perfect.** Such language is not appropriate given the complexity and unpredictability of real-world coding.
