# Mean Gene Bot triage — 2026-07-16

This is a read-only inventory of runtime data plus a small reliability review. Runtime state was not deleted or relocated.

## Executive triage

1. **P0 — transient network failure kills the whole process.** On 2026-07-16 at 00:12, DNS resolution failed for Discord while Twitch was also disconnected. TwitchIO began reconnecting, but MGB's watchdog raised on the closed websocket. Because the watchdog shares the top-level `asyncio.gather`, the exception shut down every service. The immediate mitigation now gives TwitchIO a configurable grace period (`TWITCH_RECONNECT_GRACE_SECONDS`, default 300 seconds) before escalation.
2. **P1 — runtime storage has no explicit lifecycle.** `data/` is about 25,035 MiB. `data/music_cache/` accounts for about 24,944 MiB (5,571 files). This is primarily a product cache, not source bloat, but it needs quotas, eviction rules, orphan reporting, and an operator command.
3. **P1 — static media is duplicated.** The 33 files shared by root `overlay_static/` and `bot/overlay_static/gifs/` are byte-identical and duplicate about 161 MiB. The server and media commands use `bot/overlay_static`, making root `overlay_static/` the likely redundant copy. Confirm OBS/browser-source references before removing it.
4. **P1 — telemetry is unbounded.** `logs/telemetry.jsonl` is about 39.9 MiB. Ordinary `.log` files are count-pruned to ten, but telemetry has no rotation or retention and `tail_events()` reads the entire file into memory.
5. **P1 — high-frequency success logs obscure failures.** Overlay broadcasts can occur every second and were logged at INFO, producing thousands of low-value entries. These messages now use DEBUG; warnings and failures remain visible.
6. **P2 — backups are count-unbounded.** `data/backups/` contains 1,544 timestamped raffle backups. They are only about 17.6 MiB today, but shutdown-based backups need retention and deduplication.
7. **P2 — sports polling repeats four implementations.** NHL, NBA, MLB, and NFL each create a new HTTP session and repeat parsing/cache code. Fetches run sequentially, so a ticker rebuild can wait on four independent timeouts. Empty/error results are not consistently negative-cached, inviting repeated requests during provider or DNS failures.
8. **P2 — source recovery artifacts remain active-looking.** Examples include two compiled `rpg_cog` files for different Python versions, `rpg_cog_restored.py`, disabled cogs, `archive/`, root `tmp_*` scripts, `temp_fix.txt`, a 1.19 MiB disassembly, and an empty README/Dockerfile. These should be classified as active, test fixture, recovery artifact, or removable.
9. **P2 — environment/startup drift.** Windows startup checks/creates `venv` but ultimately runs `.venv`; the Unix script uses `venv`. Several files contain mojibake. Dependency checks execute at import time, complicating tests and diagnostics.
10. **P2 — working runtime state is tracked.** Several `data/*.json` files are tracked and currently modified. Separate immutable seed/config data from mutable state before broad cleanup. The retired faction database is preserved under `archive/factions_2026-08-19/`.

## Proposed sprints

### Sprint 0 — stop outages and establish evidence (P0, 1–2 sessions)

- Reproduce websocket loss with a fake connection; add watchdog tests for recovery inside grace and sustained failure outside grace.
- Add one structured connection-state event: disconnect start, reconnect success, grace exceeded, token failure.
- Decide the desired terminal behavior after grace: in-process Twitch-only restart or process exit under a supervisor. Prefer a supervisor plus meaningful exit code if MGB is operated as one process.
- Add a startup health summary without printing secrets.
- Exit criterion: a 1–4 minute DNS/network interruption reconnects without terminating overlays or Discord.

### Sprint 1 — storage and repository hygiene (P1, 2–3 sessions)

- Produce a dry-run cleanup command reporting cache size, orphaned songs, duplicates, backup age/count, and projected reclaimed space.
- Confirm root `overlay_static/` has no external consumers, then remove the byte-identical duplicate tree (about 161 MiB).
- Add music-cache policy: configurable max GiB, minimum free disk, LRU metadata, protected/current queue entries, and explicit purge confirmation.
- Retain a bounded number/age of raffle backups and avoid writing a new backup when content is unchanged.
- Move recovery notes and one-off scripts into a clearly labeled archive or delete them after review.
- Exit criterion: cleanup is repeatable, defaults to dry-run, and never removes active queue/state files.

### Sprint 2 — observability that helps (P1, 1–2 sessions)

- Replace root `basicConfig` with named loggers and rotating handlers (size plus backup count).
- Rotate telemetry separately; change tailing so it does not load the whole JSONL file.
- Define levels: DEBUG for broadcast/poll details, INFO for lifecycle and operator actions, WARNING for recoverable degradation, ERROR for failed outcomes.
- Add correlation fields for service (`twitch`, `discord`, `sports`, `overlay`) and avoid duplicate traceback + print output.
- Exit criterion: a normal stream produces a compact operational log, while one disconnect can be reconstructed end-to-end.

### Sprint 3 — sports polling redesign (P1/P2, 2–3 sessions)

- Use one long-lived `aiohttp.ClientSession` and a shared fetch/parse pipeline.
- Fetch leagues concurrently with a global deadline and per-provider concurrency limit.
- Use adaptive TTLs: short for live games, moderate for scheduled games, long/off for out-of-season leagues.
- Add stale-while-revalidate and negative/error caching with exponential backoff and jitter.
- Make timezone and 5 AM streaming-day boundary explicit; current UTC parsing is compared as if local time.
- Add fixture-based tests for live/final/scheduled/postponed games and malformed ESPN payloads.
- Record request count, latency, status, cache hit, stale result, and last success without logging full payloads.
- Exit criterion: ticker generation never blocks on all four leagues and provider failure preserves the last known useful score state.

### Sprint 4 — architecture and feature triage (P2, several scoped sessions)

- Split `bot/main.py` into bootstrap, lifecycle supervision, Twitch, Discord, and scheduled-task ownership.
- Split the very large song-request module by queue, downloader/cache, playback, Sheets sync, and commands.
- Inventory every cog/overlay with status: keep, repair, replace, retire. Require an owner/use case and a smoke test for “keep.”
- Replace import-time dependency checks and globals with an application context and explicit startup steps.
- Establish baseline tests and CI for compile/import, state serialization, command routing, and external API fixtures.
- Write an operator README covering startup, shutdown, backup/restore, token refresh, cache cleanup, and incident diagnosis.

## Cleanup guardrails

- Never bulk-delete `data/` based on age alone; it mixes cache, mutable state, configuration, databases, and backups.
- Back up and validate JSON/SQLite state before migrations.
- Do not commit `.env`, cookies, OAuth tokens, telemetry payloads, or live databases.
- Prefer a generated cleanup report and allowlist over ad-hoc deletion commands.
- Make one canonical static asset root and update all code and OBS references before removing duplicates.

## Suggested order

Finish Sprint 0 first. Then run Sprint 1's inventory/dry-run in parallel with Sprint 2 design. Complete logging before sports redesign so polling behavior can be measured. Treat Sprint 4 as separate feature-sized changes, not a single rewrite.
