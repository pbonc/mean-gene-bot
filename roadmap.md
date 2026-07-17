# Mean Gene Bot Roadmap

This file is the execution roadmap for the whole bot. Detailed feature specifications remain in `docs/`; this document records priorities, sprint-sized outcomes, and completion criteria.

## Roadmap conventions

- A sprint is a focused development slice, not necessarily a fixed calendar period.
- Each sprint should end with something demonstrable or operationally safer.
- A sprint is complete only when its exit criteria are met.
- New work should be added under the appropriate workstream rather than mixed into an unrelated sprint.
- Live state in `data/` is not cleanup material. Back up and validate it before migrations.

## Current priorities

1. Prototype the Stream RPG micro strip at its real OBS dimensions.
2. Keep the archived RPG isolated while establishing clean v2 pathways.
3. Preserve bot reliability while new work is introduced.
4. Address storage, telemetry, and repository hygiene in bounded maintenance sprints.

---

# Workstream: Stream RPG v2

## Goal

Create a persistent, transparent micro-RPG along the bottom of OBS. Chat characters wander while idle, automatically battle spawned enemies, display short announcements and loot flourishes, and leave the visible roster after extended inactivity. The RPG should reward participation without encouraging command spam or competing with the stream.

The detailed product and technical specification lives in [docs/RPG_V2_MICRO_STRIP_ROADMAP.md](docs/RPG_V2_MICRO_STRIP_ROADMAP.md).

## Product baseline

- Transparent 1920x96 browser source for a 1920x1080 stream canvas
- Most quiet-state activity contained within the bottom 64 pixels
- Approximately 32x40 pixel actors, subject to OBS and Twitch readability testing
- Four visible chat characters on the left and up to three enemies on the right
- Adventurer base class progressing into Warrior, Mage, Healer, or Ranger
- Slime and Goblin common enemies, followed by an Ogre boss
- Ambient loop: `wander -> encounter -> automatic battle -> rewards -> wander`
- Normal chat activity refreshes presence; combat commands are not required
- Short overlay announcements for encounters, bosses, victory, defeat, levels, and loot
- Persistent identity and progression without importing the old RPG economy

## RPG Sprint 0: Archive boundary and decisions

**Objective:** Make the old and new RPG pathways unambiguous before implementation begins.

- Treat `archive/rpg/` as read-only historical material.
- Add an archive manifest classifying old concepts as keep, reinterpret, or retire.
- Confirm that v2 will not import `archive/rpg/rpg_cog.py` or restore it as an active cog.
- Define versioned player, runtime snapshot, and animation-event schemas.
- Confirm the initial strip height, active party size, actor scale, and class roster.
- Update the detailed RPG specification from command rounds to the ambient automatic battle loop.
- Define legacy recognition separately from combat progression; default to cosmetic titles rather than inherited power.

**Exit criteria:** The v2 package, data paths, schemas, and archive rules are documented well enough that development cannot accidentally reactivate the legacy implementation.

## RPG Sprint 1: Transparent micro-strip prototype

**Objective:** Prove that the idea is readable and pleasant at its actual stream size before building the game.

- Add a new `/rpg-micro` OBS browser-source route without replacing `/battle`.
- Build a 1920x96 page with a fully transparent background.
- Create temporary, visually distinct silhouettes for the five friendly classes and three enemies.
- Render four friendly slots, three enemy slots, tiny health bars, ready/status pips, and temporary name labels.
- Demonstrate wandering, enemy arrival, melee lunge, projectile, healing, hit reaction, knockout, victory, defeat, and loot flourish.
- Add a scripted demo loop independent of Twitch and persistent data.
- Test the source in OBS at 1080p, in a downscaled preview, and against both bright and dark stream content.
- Check whether a 64-pixel quiet mode is useful or whether a fixed 96-pixel source is sufficiently unobtrusive.

**Exit criteria:** Viewers can distinguish sides, broad character roles, health changes, and major events after realistic scaling and compression, without permanent text panels.

## RPG Sprint 2: Standalone automatic battle engine

**Objective:** Implement a deterministic game that can run and be tested without Twitch, OBS, WebSockets, or files.

- Create `bot/rpg_v2/` with models, engine, class definitions, enemies, and progression boundaries.
- Implement the internal state machine: idle, encounter introduction, resolution, result, and return to idle.
- Resolve actors sequentially using speed, move priority, and a stable tie-breaker.
- Give every class a sensible automatic behavior:
  - Adventurer uses a balanced strike.
  - Warrior protects threatened allies.
  - Mage prioritizes high-impact damage.
  - Healer heals when necessary and attacks otherwise.
  - Ranger targets weakened enemies.
- Add Slime, Goblin, and Ogre behaviors with visually telegraphed effects.
- Produce an ordered animation-event list from every resolved action.
- Test targeting, turn order, healing, knockouts, victory, defeat, and deterministic seeded simulations.

**Exit criteria:** Automated test battles complete reliably and produce stable snapshots plus ordered visual events.

## RPG Sprint 3: Overlay event integration

**Objective:** Drive the micro strip from the real engine while keeping game state authoritative on the server.

- Publish recoverable snapshots and sequenced animation events through the existing overlay WebSocket infrastructure.
- Let a newly connected browser source render current state immediately.
- Ignore duplicated and stale events after reconnects.
- Queue visual actions so actors move one at a time while the server remains authoritative.
- Ensure a missing or disconnected overlay never blocks combat resolution.
- Add quiet, normal, paused, and hidden operator modes.

**Exit criteria:** Repeated automated battles render correctly, and refreshing the browser source recovers without restarting the bot or replaying an entire old battle.

## RPG Sprint 4: Chat presence and roster rotation

**Objective:** Let ordinary Twitch participation populate the strip without requiring RPG command spam.

- Add `!join` to create or explicitly activate a character.
- Refresh a joined viewer's presence from ordinary chat messages.
- Start with configurable presence targets:
  - roughly 20 minutes before moving an unseen viewer to reserve
  - roughly 45 minutes before the character walks off the strip
- Treat timeouts as visual roster management, never as loss of XP or character data.
- Rotate four active characters between encounters using wait time and new-viewer visibility.
- Give reserves a small capped support contribution.
- Make returning viewers visibly walk back onto the strip.
- Avoid paid-status combat advantages and avoid requiring messages solely to remain eligible.

**Exit criteria:** A private stream can gain and lose participants naturally through conversation while battles continue with no required combat input.

## RPG Sprint 5: Persistence and progression

**Objective:** Give viewers a reason to return without allowing veteran power to invalidate newcomers.

- Persist viewer identity, XP, level, class, cosmetic choices, and basic battle history.
- Begin every new character as an Adventurer.
- Unlock selection of Warrior, Mage, Healer, or Ranger at level 5.
- Add one distinctive special flourish per advanced class, initially triggered automatically.
- Cap power growth conservatively and place most long-term distinction in cosmetics, titles, and animation variations.
- Add versioned persistence and recovery tests.
- Create a reviewed, one-way, idempotent legacy migration only after the v2 schema stabilizes.

**Exit criteria:** A viewer can leave, return, advance, and retain a recognizable character without old state or veteran progression destabilizing encounters.

## RPG Sprint 6: Stream trial and tuning

**Objective:** Validate that the RPG supports stream growth and does not distract from the main content.

- Measure joins, returning participants, visible-roster wait time, battle duration, and overlay engagement.
- Test an initial encounter cadence of roughly two to five minutes between battles.
- Keep normal encounters around 30-75 seconds and bosses around one to three minutes unless trials suggest otherwise.
- Tune movement, brightness, announcement frequency, and sound independently.
- Add moderator controls for start, pause, resume, abort, force encounter, quiet mode, and hide.
- Document OBS setup and safe fallback behavior.
- Decide whether special bosses merit a separate expanded presentation driven by the same engine.

**Exit criteria:** Several real streams demonstrate that the strip is readable, stable, easily silenced, and compatible with normal conversation.

## RPG post-launch backlog

- Additional enemy families and encounter environments
- Cosmetic pets or reserve assists that do not complicate core combat
- Raid-triggered reinforcements or special encounters
- Community milestones and scheduled bosses
- Optional highlighted viewer specials
- Expanded boss/BRB overlay using the same snapshots and events
- Additional cosmetics, titles, palettes, and animation variants

The following remain explicitly deferred until usage data justifies them: inventories, equipment stats, currencies, gacha, referrals, salaries, PvP, prestige classes, and branching skill trees.

---

# Workstream: Reliability and operations

## Operations Sprint 0: Connection resilience

**Objective:** Prevent a transient Twitch or Discord outage from terminating unrelated bot services.

- Maintain automated coverage for Twitch reconnect behavior inside and outside the configured grace period.
- Add structured connection lifecycle events without exposing tokens.
- Decide and document whether sustained failure restarts one service or exits under a supervisor.
- Add a concise startup health summary.

**Exit criteria:** A short DNS or network interruption reconnects without terminating overlays or unrelated services.

## Operations Sprint 1: Storage lifecycle

**Objective:** Make large caches and growing backups manageable without risking live data.

- Provide a dry-run storage report for music cache, duplicates, backups, and reclaimable space.
- Add configurable music-cache limits and safe eviction rules.
- Protect queued, currently playing, configured, and recently used media.
- Bound raffle backup retention and avoid identical backups.
- Confirm all consumers before consolidating duplicate static media roots.

**Exit criteria:** Operators can understand and safely control storage growth through an allowlisted, dry-run-first workflow.

## Operations Sprint 2: Logging and telemetry

**Objective:** Retain useful evidence without unbounded files or noisy routine messages.

- Use named loggers and rotating handlers.
- Rotate telemetry independently and avoid loading the full telemetry file for tail operations.
- Keep broadcast and polling detail at DEBUG.
- Add service and correlation fields for connection and lifecycle events.

**Exit criteria:** Normal operation produces compact logs, while a failure can still be reconstructed end to end.

---

# Workstream: Bot architecture and maintenance

## Maintenance Sprint 0: Active-feature inventory

**Objective:** Clearly identify what the repository actively runs and what is historical or recoverable material.

- Classify each cog, overlay, root-level utility, compiled artifact, and temporary script as keep, repair, replace, archive, or remove.
- Require a known use case and a smoke test for active features.
- Separate immutable configuration and seed data from mutable runtime state.
- Document canonical locations for overlays, assets, logs, backups, and caches.

**Exit criteria:** A contributor can determine whether a file is active without relying on filenames or oral history.

## Maintenance Sprint 1: Application boundaries

**Objective:** Reduce coupling in startup and the largest modules without combining this work with RPG development.

- Separate bootstrap, lifecycle supervision, Twitch, Discord, overlays, and scheduled-task ownership.
- Replace import-time dependency checks with explicit startup checks.
- Establish an application context rather than adding new global state.
- Split oversized modules only through behavior-preserving, tested changes.

**Exit criteria:** Services have explicit owners and can fail, start, and stop without hidden import side effects.

## Maintenance Sprint 2: Baseline tests and operator documentation

**Objective:** Make routine changes safer and operation less dependent on memory.

- Add compile/import, command-routing, persistence, and external-response fixture tests.
- Document startup, shutdown, backup, restore, token refresh, cache cleanup, and incident diagnosis.
- Replace the empty root README with a short project entry point linking to detailed guides.

**Exit criteria:** Core checks run repeatably and a new operator can perform common recovery tasks from documentation.

---

# Workstream: Music and media

## Candidate sprints

- Separate song queue, downloader/cache, playback, Sheets synchronization, and command responsibilities.
- Normalize media filenames and prevent duplicate `.mp3.mp3` outputs.
- Add cache health reporting and explicit protected-entry rules.
- Establish a single canonical overlay asset root after consumer verification.

These items need prioritization before they become committed sprints.

---

# Workstream: Sports and ticker

## Candidate sprints

- Share one long-lived HTTP session and a common fetch/cache pipeline.
- Fetch league data concurrently with deadlines and provider backoff.
- Add stale-while-revalidate and negative caching.
- Make stream-day timezone boundaries explicit.
- Add fixture tests for scheduled, live, final, postponed, and malformed responses.

These items need prioritization before they become committed sprints.

---

# Ideas and uncommitted work

Add new ideas here before scheduling them. Each idea should eventually state the viewer/operator problem, intended outcome, dependencies, risks, and a measurable exit criterion.

- Full-screen RPG boss presentation driven by the micro-strip engine
- Bot management and health dashboard
- Improved Discord/Twitch cross-platform command ownership
- Additional stream-growth experiments that do not rely on chat spam

---

# Completed sprints

Move completed sprint summaries here with the completion date, relevant commit or pull request, and any deferred follow-up work.

