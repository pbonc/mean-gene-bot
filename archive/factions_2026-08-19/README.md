# Retired faction system

The Mean Gene Bot faction system was retired on 2026-08-19. This archive keeps
the final implementation and live SQLite data so memberships, influence, relic
ownership, commissioner state, and activity history remain recoverable.

Archived files:

- `bot/commands/faction_cog.py` — Twitch commands and event/reward integration
- `bot/faction_service.py` — faction persistence and game rules
- `bot/twitch_eligibility.py` — follower eligibility used by faction joining
- `data/factions.db` — final live faction database
- `docs/AUDIT_BOARD_2026-05-27.md` — historical faction implementation audit

The active raffle cog no longer consults factions. Zap winners still receive
the normal one-entry award, but faction influence, faction echo awards, and
relic-based entry modifiers are disabled.

To restore the system, copy the files back to their original paths and restore
the removed raffle hooks from version history. The bot automatically discovers
`bot/commands/faction_cog.py` when it starts.
