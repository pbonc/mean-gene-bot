# WoTWoM feature roadmap

`/wotwom` is a separate World of Tanks Modern Armor version of Wheel of
Misfortune. The existing `/wom` route and overlay remain independent.

## Sprint 1 — Foundation and playable shell

Status: implemented

- Add `/wotwom` and `/api/wotwom/inventory`.
- Keep the Wargaming application ID on the server.
- Show a garage-loading screen when the overlay opens.
- Resolve a configured player and load played-vehicle statistics plus
  Tankopedia metadata.
- Provide World War II and Cold War toggles.
- Spin and independently lock Game Mode, Vehicle Class, Garage Vehicle, and
  Challenge.
- Print the final four-part challenge.
- Include the challenges: 1 kill, 2 kills, 3 kills, win, win and survive,
  ammo rack an enemy, and ram kill.

### Local setup

1. Sign in to the [Wargaming Developer Room](https://developers.wargaming.net/)
   and create a server application.
2. Add these values to `.env`:

   ```text
   WOT_APPLICATION_ID=your-application-id
   WOT_ACCOUNT_ID=your-numeric-account-id
   ```

   `WOT_PLAYER_NAME=your-exact-gamertag` can be used instead of an account ID.
   Modern Armor API names may include a platform suffix such as `-x` or `-p`.
3. Restart the bot and open `http://localhost:8080/wotwom`.

## Sprint 2 — Verified garage inventory and mode classification

- Exercise the client with the streamer's real account.
- Record the exact current Tankopedia fields used for WWII versus Cold War.
- Add fixture-based contract tests from sanitized API responses.
- Implement console-service authentication if a private garage field is
  required to distinguish currently owned tanks from tanks previously played.
- Add a cache and a last-known-good fallback so an API outage does not take the
  overlay offline.

Exit criterion: the overlay's tank pool and WWII/Cold War split match the
in-game garage.

## Sprint 3 — Garage delivery detection and chat notification

- Store a durable inventory snapshot outside the overlay page.
- Refresh at bot startup, when `/wotwom` opens, and on a conservative schedule.
- Diff stable tank IDs, not display names.
- Treat the first successful fetch as a baseline and do not announce every
  existing tank.
- Broadcast one message for each newly observed tank:
  `<tank name> delivered to the garage, added to inventory.`
- Add retry/debounce logic so API inconsistencies do not create duplicate chat
  messages.

Exit criterion: a newly acquired tank produces one chat message and becomes
eligible on the next spin.

## Sprint 4 — Production hardening and polish

- Add moderator refresh/status commands.
- Add API health, last refresh, inventory count, and account identity logging.
- Refine reel sound and timing while retaining the familiar WoM presentation.
- Test empty mode pools, renamed tanks, hidden profiles, API rate limiting,
  expired access tokens, and offline startup.
- Run an OBS/browser-source acceptance test at the production resolution.

Exit criterion: the overlay recovers cleanly from API and network failures and
is ready for normal stream use.

## Known API boundary

The public Modern Armor vehicle-statistics endpoint is a record of vehicles
that have statistics for the player. It is an excellent first inventory seed,
but it may include tanks no longer owned and may not show a brand-new tank until
it has been played. Sprint 2 must verify whether authenticated private account
data exposes the true garage before Sprint 3 promises delivery-time detection.
