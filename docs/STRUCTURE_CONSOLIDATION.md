# Structure consolidation

## Canonical directories

| Purpose | Canonical path | Reason |
|---|---|---|
| Overlay HTML and media | `bot/overlay_static/` | `bot/overlay_server.py` serves this tree and `bot/commands/media_overlay.py` discovers media here. It contains all overlay HTML plus the fuller media collection. |
| Card images | `assets/cards/` | The overlay API enumerates this categorized tree. |
| Mutable runtime state | `data/` | Commands and services resolve project-level state here. |
| Stream-label inputs | `bot/data/labels/` | `bot.labels_stats` and ticker tasks explicitly consume this integration-specific path. |
| Sound effects | `assets/sfx/` | Media commands explicitly discover sound effects here. |
| Retired RPG recovery material | `archive/rpg/` | This is retained recovery material, not an active duplicate. |

## Consolidated in this branch

- Removed root `overlay_static/`, an inactive partial copy of `bot/overlay_static/gifs/`. Thirty-three files were byte-identical. Its only unique real image, `oil.jpg`, was preserved in the canonical media directory.
- Removed root `overlay_cards/`, which contained four tiny placeholder JPEGs and had no runtime references. The routed card structure is `assets/cards/`.
- Removed unused `bot/overlays/`, which contained only empty package markers and an empty misspelled `overkay_server.py`. The active server is `bot/overlay_server.py`.
- Corrected `/gifs` routing and media discovery to use `bot/overlay_static/gifs/` directly. The previous configuration mounted and scanned the parent HTML directory, producing `/gifs/gifs/...` paths even though MGB emits `/gifs/...` URLs.
- Corrected card discovery/static routing from nonexistent `bot/assets/cards/` to canonical root `assets/cards/`.

## Intentionally retained

- `bot/data/` is not a duplicate of root `data/`: its label files are an external stream-label input consumed by ticker code.
- `archive/rpg/` contains a large recovered cog and state snapshots. Removal requires a separate archival decision.
- Disabled cogs and compiled recovered RPG modules remain feature/recovery triage items, not directory duplicates.
- Music-cache variants remain untouched until queue state, catalog identity, and legacy naming can be reconciled safely.

## External configuration note

OBS/browser sources should use the overlay HTTP routes (for example `/`, `/afk`, `/cards`, and `/gifs/...`) rather than filesystem paths under the removed root directories.
