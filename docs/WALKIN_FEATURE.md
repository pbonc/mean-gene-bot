# Walk-In Feature

The Walk-In feature plays a specific SFX and optionally sends a message the first time a configured user speaks in chat during a stream.

## Command

- Usage: !walkin @username !sfxcommand "Entrance text"
- Mod-only. If `@username` is omitted, the walk-in is set for the invoking user.
- `!sfxcommand` must correspond to an existing SFX command registered by the Media Overlay system.
- The text is exactly what appears between the quotes; quotes themselves are not included.

Examples:
- `!walkin @dar !fe "FE has entered the chat!"`
- `!walkin !damn "It me."`

## Behavior

- First message from the configured user triggers:
  - Plays their SFX via AudioManager.
  - Sends the configured text to chat (if provided).
- Per-stream flag `played` prevents repeat triggers.
- All `played` flags reset when the bot restarts.

## Storage

- JSON stored at `data/walkins.json` with structure:
  ```json
  {
    "users": {
      "username": { "sfx_command": "fe", "text": "Sample", "played": false }
    }
  }
  ```

## Notes

- SFX validation uses the Media Overlay cog's `media_commands` map. Only commands with an SFX entry are valid.
- Audio playback runs off the event loop in a thread to avoid blocking.
