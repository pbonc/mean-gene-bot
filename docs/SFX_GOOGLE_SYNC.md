Google Sheets SFX/GIF Sync
==========================

This document describes how to configure the bot to sync SFX/GIF commands to a Google Sheet.

Prerequisites
-------------
- A Google Cloud project with the Google Sheets API enabled.
- A Service Account with a JSON key downloaded to the host where the bot runs.
- A Google Sheet to receive the data. Note the spreadsheet ID from the URL.

Environment variables
---------------------
- `GOOGLE_SERVICE_ACCOUNT_JSON` (required): absolute path to the service account JSON key file.
- `SFX_SPREADSHEET_ID` (required): the spreadsheet ID from the sheet URL.
- `SFX_SHEET_NAME` (optional, default `sfx`): the worksheet/tab name to write.
- `SFX_COMMANDS_SHEET_NAME` (optional, default `sfx_commands`): worksheet/tab for the full SFX command catalog.

How it works
------------
- The bot scans `bot/overlay_static/gifs/` and `assets/sfx/` and maintains a registry of commands.
- When a command is added or removed the bot will attempt to sync the canonical list of commands
  to the configured Google Sheet (it overwrites sheet contents for idempotency).
- It now writes two worksheet tabs in the same spreadsheet:
  - `SFX_SHEET_NAME` (default `sfx`): public-facing media catalog rows.
  - `SFX_COMMANDS_SHEET_NAME` (default `sfx_commands`): full SFX command catalog (public + mod-only).
- Moderators can force an immediate sync via the chat command `!syncsfx`.

Security
--------
- Do NOT commit the service account JSON into the repository. Store it on the host and protect it.
- Use OS-level permissions or a secrets manager to protect the key file.

Testing
-------
1. Install the Python dependencies: `pip install -r requirements.txt` (the requirements include gspread and google-auth).
2. Export the env vars and restart the bot.
3. Add or remove a GIF or SFX file in the appropriate folders and verify the sheet updates, or use `!syncsfx`.
