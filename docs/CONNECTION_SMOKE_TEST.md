# Connection smoke test

Run this after connection, authentication, dependency, or startup-lifecycle changes:

```powershell
.\.venv\Scripts\python.exe tools\connection_smoke_test.py
```

The test performs no Twitch or Discord chat sends. It:

- validates `TWITCH_OAUTH_TOKEN`, opens Twitch IRC, authenticates, and joins the first configured `TWITCH_CHANNELS` channel;
- opens a Discord gateway connection with no privileged intents and waits for `READY`;
- starts MGB's real overlay server on a temporary loopback port and connects over HTTP and WebSocket.

Each service can be skipped during diagnosis:

```powershell
.\.venv\Scripts\python.exe tools\connection_smoke_test.py --skip-discord
```

The process exits `0` only when every selected check passes. It never prints credential values. This is an integration smoke test, not a full bot startup test: it deliberately avoids state backups, media initialization, Sheets synchronization, scheduled messages, and command execution.
