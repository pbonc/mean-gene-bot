# Stream RPG v2: Micro-Strip Design and Roadmap

## Product statement

Stream RPG v2 is a persistent, transparent OBS browser overlay that stages small JRPG-style battles along the bottom of the stream. It should feel alive without competing with the stream. Viewers join once, make at most one choice per round, and see their character act on-screen. Missing choices resolve automatically.

The micro strip is the primary interface. Twitch chat is an input channel and an occasional announcement channel, not the combat log.

## Initial scope

The first release includes:

- One base class that advances into four distinct classes
- Four visible friendly combatants and up to three enemies
- Two common enemy types and one boss encounter
- Join, command, action, check, and result phases
- Automatic actions for viewers who do not enter a command
- Persistent XP, level, advanced class, and a small cosmetic identity
- Transparent OBS output with compact battle and loot flourishes
- A clean v2 code path that does not import the archived RPG

The first release excludes inventories, equipment stats, gacha, currencies, referrals, salaries, pets, summons, prestige classes, branching skill trees, and PvP.

## Overlay dimensions

Design at 1920x96 pixels for a 1920x1080 OBS canvas. The document background remains fully transparent.

- Normal footprint: 96 px high, or 8.9% of a 1080p canvas
- Quiet-state visual content: mostly contained in the bottom 64 px
- Temporary announcement: may use the upper 32 px of the same source
- Friendly actor box: approximately 32x40 px
- Boss actor box: up to 56x48 px
- Name label: shown only for joins, selection, and the acting character
- Health bar: 28-36 px wide and 3-4 px high, positioned above the actor
- Pixel rendering: integer scaling and `image-rendering: pixelated`

The browser source remains 1920x96. OBS can place it at the bottom of the main canvas without cropping or chroma keying.

### Layout zones

```text
0 px                                                        1920 px
|------------------------- transparent strip ---------------------|
|                 temporary announcement / loot flourish          | 32 px
| [P1] [P2] [P3] [P4]        action lane        [E1] [E2] [Boss] | 48 px
| friendly status pips     transient battle text      enemy bars | 16 px
```

- Friendlies occupy roughly the left 28%.
- Enemies occupy roughly the right 25%.
- The center is intentionally open for lunges, projectiles, damage numbers, and short text.
- All persistent UI uses muted colors. High brightness is reserved for actions, rare loot, victory, and defeat.

## Visual behavior

### Quiet state

Actors breathe, bob, or shift by one or two pixels. No large panels are visible. Between encounters, the party may walk in place while scenery silhouettes drift slowly behind them, but scenery must remain sparse and translucent.

### Join moment

A new active viewer runs in from the left, their name appears for two seconds, and they settle into an open party slot. If the active party is full, the viewer joins the reserve roster and receives a small reinforcement flourish without displacing a combatant mid-round.

### Action moment

The acting character's name appears, the sprite moves into the center lane, an effect resolves, the target reacts, damage or healing floats briefly, and the actor returns. Actions are presented sequentially even though the game engine has already calculated the round.

### Announcements

Announcements temporarily occupy the top 32 px and retract automatically. Initial messages are:

- Encounter name
- Command phase and remaining time
- Boss or rare enemy arrival
- Victory or defeat
- Level-up or class advancement
- Rare loot flourish

Routine attacks do not produce Twitch chat messages. The overlay supplies confirmation.

## Party size and participation

The battlefield has four active friendly slots. This is a visual constraint, not a four-viewer participation limit.

- Everyone who uses `!join` enters the expedition roster.
- Four viewers are active for an encounter.
- Reserves rotate between encounters, with preference for new viewers and viewers who have waited longest.
- Reserves can contribute a small, capped support bonus so joining is always useful.
- A disconnected or inactive viewer may still auto-act for the current encounter, then rotate out.

This policy should be visible and predictable. Paid status must not determine combat power or active-party priority.

## Class progression

Every new character begins as an **Adventurer**. The Adventurer has balanced stats and uses `Strike` automatically. At level 5, the viewer selects one of four advanced classes. If no selection is made, the character remains an Adventurer until a later stream.

| Class | Role | Automatic behavior | Viewer special | Visual identity |
|---|---|---|---|---|
| Adventurer | Generalist | Strikes the current target | Rally: small party boost | Brown/tan, short sword |
| Warrior | Defender | Protects the lowest-health ally | Bulwark: party damage reduction for one round | Blue, shield silhouette |
| Mage | Burst damage | Attacks the healthiest enemy | Meteor: strong multi-target damage | Purple, pointed staff/hat |
| Healer | Support | Heals when an ally is threatened; otherwise attacks | Renewal: party heal | Green/white, bright staff |
| Ranger | Fast damage | Targets the weakest enemy | Volley: several light hits | Red/forest green, bow silhouette |

The first version has no ability tree. Class differentiation comes from silhouette, palette, automatic targeting, one passive tendency, and one special animation.

## Initial enemies

| Enemy | Purpose | Behavior | Visual read |
|---|---|---|---|
| Slime | Introductory enemy | Low damage, high readability | Round body, bright color |
| Goblin | Common threat | Attacks weak targets and occasionally guards | Angular body, weapon silhouette |
| Ogre | First boss | Slow heavy attacks and a telegraphed party slam | Large sprite and strong anticipation pose |

Enemy mechanics should be legible through animation. The Ogre raises its weapon before a slam; viewers do not need to read a status panel to understand the threat.

## Battle state machine

```text
IDLE/TRAVEL
    -> JOIN
    -> ENCOUNTER_INTRO
    -> COMMAND
    -> ACTION_PLAYBACK
    -> CHECK
         -> COMMAND when both sides remain
         -> VICTORY when enemies are defeated
         -> DEFEAT when friendlies are defeated
    -> RESULTS
    -> IDLE/TRAVEL
```

### Join phase

- `!join` adds the viewer to the expedition.
- The overlay acknowledges participation visually.
- A battle can start on a timer, a moderator command, or a configured stream event.

### Command phase

- One action is accepted per active viewer.
- Initial inputs: `!attack`, `!defend`, and `!special`.
- Repeating a command replaces the previous choice silently.
- No command means the class chooses an automatic action.
- The overlay shows a small ready pip above each active character; it does not expose the chosen move unless desired for balance.

### Action playback

- Inputs lock at the deadline.
- The engine calculates a deterministic ordered event list.
- Speed, move priority, and a stable tie-breaker establish turn order.
- The overlay plays the events one at a time.
- Combat state must not depend on animation completion or an OBS browser connection.

### Check and results

- After playback, the engine checks defeat conditions.
- An unresolved battle returns to a fresh command phase.
- Results award XP, update progression, rotate the roster, and show a compact flourish.

## Progression

Progression should make returning satisfying without making new viewers irrelevant.

### Launch progression

- XP and levels
- Adventurer-to-advanced-class choice at level 5
- Small stat improvements with conservative caps
- Palette or accent-color selection
- A few earned titles or nameplate marks
- Lifetime victories and boss victories

### Progression principles

- A new Adventurer must contribute meaningfully beside a veteran.
- Most long-term distinction should be cosmetic or behavioral, not exponential power.
- Battle difficulty scales from the active party and encounter tier, not total account age.
- Existing RPG players may receive a non-power legacy title after migration.

## Event contract between engine and overlay

The engine publishes snapshots for recovery and events for animation.

### Snapshot

The latest snapshot contains battle ID, phase, deadline, round, active party, reserves count, enemies, HP, status, and result summary. A newly connected OBS browser source can render the current battle immediately.

### Animation events

Examples include:

- `actor_joined`
- `encounter_started`
- `command_opened`
- `action_started`
- `projectile_spawned`
- `damage_applied`
- `healing_applied`
- `actor_defeated`
- `battle_finished`
- `loot_awarded`
- `level_gained`
- `class_advanced`

Events include a battle ID, round number, sequence number, actor ID, target IDs, effect key, and display values. The overlay ignores duplicated or stale sequence numbers.

Game resolution remains authoritative in Python. The HTML overlay never decides damage, targeting, rewards, or progression.

## New code pathways

The v2 implementation should live in a new package and use the existing overlay server only as transport.

```text
bot/rpg_v2/
    models.py          # player, enemy, encounter, action, event
    engine.py          # pure battle state transitions and resolution
    classes.py         # five class definitions and behaviors
    enemies.py         # enemy definitions and encounter construction
    progression.py     # XP, levels, advancement, cosmetics
    repository.py      # versioned persistence boundary
    service.py         # timers, battle lifecycle, event publication
    commands.py        # thin Twitch command adapter

bot/overlay_static/rpg_micro/
    index.html
    micro.css
    micro.js
    sprites/
    effects/

data/rpg_v2/
    players.json       # acceptable for prototype; replaceable repository
    runtime.json       # recoverable current encounter snapshot
```

The battle engine must be usable without Twitch, OBS, WebSockets, or files. This makes balancing and phase behavior testable with fast unit tests.

## Archive and migration policy

The archived implementation remains under `archive/rpg/` and is read-only historical material.

- Do not restore `archive/rpg/rpg_cog.py` into `bot/commands/`.
- Do not import archived code from v2.
- Preserve archived state and log files as migration inputs and historical records.
- Document useful formulas or behaviors before reimplementing them; do not copy large coupled sections.
- Create a one-way, idempotent migration tool only when the v2 player schema is stable.
- Migrate identity and selected legacy recognition, not old combat state or balance values.
- Keep a manifest mapping old concepts to `keep`, `reinterpret`, or `retire`.

Suggested initial mapping:

| Old concept | Decision |
|---|---|
| Player identity | Keep |
| Lifetime participation recognition | Reinterpret as legacy title/cosmetic |
| XP and levels | Reset for v2 unless a later conversion rule is approved |
| Large class roster | Retire; preserve only as design reference |
| Gacha, tokens, salaries, referrals | Retire |
| Pets and summons | Retire for launch; reconsider as cosmetic assists |
| Existing battle overlay transport | Keep and simplify |
| Existing battle runtime state | Do not migrate |

## Delivery roadmap

### Milestone 0: Decisions and archive boundary

- Approve strip height, active party size, class names, and initial commands.
- Add an archive manifest describing what may be consulted and what is retired.
- Define versioned v2 player and runtime schemas.
- Establish deterministic battle simulations and fixtures.

**Exit condition:** v2 can be developed without editing or importing the archived RPG.

### Milestone 1: Transparent visual prototype

- Build the 1920x96 transparent browser source.
- Use temporary geometric or silhouette sprites.
- Render four friendlies, three enemies, health bars, name reveal, and ready pips.
- Demonstrate idle, lunge, projectile, hit, heal, knockout, victory, and loot animations using scripted events.
- Verify in OBS at 1080p and on a downscaled stream preview.

**Exit condition:** character roles and sides remain distinguishable at normal viewing size without permanent text panels.

### Milestone 2: Pure battle engine

- Implement the state machine and deterministic turn order.
- Add Adventurer, Warrior, Mage, Healer, Ranger, Slime, Goblin, and Ogre.
- Generate ordered animation events from resolved rounds.
- Test timeout defaults, duplicate commands, knockouts, victory, and defeat.

**Exit condition:** complete battles can run in tests without Twitch or an overlay.

### Milestone 3: Twitch and overlay integration

- Add `!join`, `!attack`, `!defend`, and `!special` through a thin command cog.
- Publish snapshots and sequenced events through the current WebSocket infrastructure.
- Add reconnect recovery without replaying the entire animation queue.
- Suppress routine bot responses and add rate-limit protection.

**Exit condition:** a private test stream can complete repeated battles with minimal chat output.

### Milestone 4: Persistence and progression

- Persist identity, XP, level, class choice, cosmetics, and basic history.
- Add level-5 advancement and the four class specials.
- Add roster rotation and reserve support.
- Add legacy recognition migration after explicit review.

**Exit condition:** viewers can leave and return with stable, comprehensible progress.

### Milestone 5: Stream tuning

- Measure joins, commands per round, non-command participation, repeat players, and encounter duration.
- Tune command windows and action playback speed.
- Add moderator controls for pause, start, abort, and quiet mode.
- Decide whether full-screen boss presentation is worthwhile using the same engine and events.

**Exit condition:** the RPG supports the stream's pacing and can be disabled or quieted instantly.

## Decisions to validate in the visual prototype

1. Is 96 px unobtrusive enough, or should quiet mode collapse to 64 px?
2. Are 32x40 px actors distinguishable after Twitch compression and mobile playback?
3. Should names appear only during actions, or remain as tiny initials?
4. Does a four-character active party feel populated without becoming cluttered?
5. Should the command phase be visible continuously or only announced at its start and final five seconds?

These are visual tests, not architecture decisions. The prototype should make them inexpensive to change.
