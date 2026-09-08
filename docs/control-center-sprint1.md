# MeanGene Control Center — Sprint 1

## Verified implementation target

Inspected the working-tree implementation before editing. `bot.main.main()` owns
startup, optional Discord, overlay/ticker/watchdog tasks, and shutdown. `create_bot()`
constructs Twitch and audio; Twitch owns `hermes_bridge`, `lore_store`, and
`lore_capture`. The Control Center injects those existing references and never
constructs runtime clients. Existing Discord operator construction remains unchanged.

The overlay has a separate application, module-owned runner and background tasks.
Its root-owned serving task uses `OVERLAY_HOST`, `OVERLAY_PORT` (8080 default), and
two fallback ports. No overlay route, asset, authentication, or behavior is changed.

Twitch's existing ticker/watchdog code reads `connected_channels`. This is evidence
of joined channels, not proof of provider health. Discord's `on_ready` event is
historical, not a durable current-health signal. Hermes creates request-scoped HTTP
sessions/runs; there is no persistent connection to reconnect. Lore opens SQLite
connections per operation and exposes no health API. No safe isolated manual
Twitch/Discord reconnect operation was found. Existing watchdog and whole-root
retry behavior must not be invoked by operator controls.

## Configuration and operation

No secret or environment file was read or changed for this implementation.
On a future approved bot launch, supply configuration through the existing process
environment convention:

- `CONTROL_CENTER_PASSWORD`: required, 16–1024 characters, not all whitespace.
  Use a strong unique password; do not reuse provider credentials.
- `CONTROL_CENTER_HOST`: defaults to `127.0.0.1`; only that exact literal is accepted.
- `CONTROL_CENTER_PORT`: defaults to `8090`; integer 1–65535, outside the overlay's
  configured three-port range.

Missing/invalid configuration disables only the Control Center listener with a
fixed, non-sensitive warning. Wildcard, hostname, IPv6, and other network binds
are refused. Valid configuration with a bind/setup failure aborts startup and runs
owned-resource cleanup. No configuration values are included in error messages.

Entry: `http://127.0.0.1:8090/control/login` (adjust the port when configured).
Protected requests without a session return 401. No service was launched or
configuration supplied as part of this sprint; operational activation remains Dar's
choice. There is no separate launcher or deployment step in this change.

## Authentication and mutation security

A GET of the login page issues an opaque five-minute pre-login session and CSRF
challenge. Login POST requires JSON, that challenge, and the exact configured
Origin. Password digests are compared with `hmac.compare_digest`. Failed login
invalidates its challenge; reload to retry. Successful login rotates the session
identifier and CSRF token, preventing fixation. Authenticated sessions expire after
one hour, are held only in server memory, and are invalidated on logout/shutdown.
The session map is bounded to 512 entries, with expired entries pruned on requests.

Cookies are HttpOnly, SameSite=Strict, scoped to `/control/`, and have no Domain
attribute. Secure is deliberately false because this listener supports local HTTP
only; enabling it would break default loopback login. Cookies are not isolated by
port: this is a local operator surface, not isolation from untrusted local software.
No reusable password is stored in browser storage; the password input is cleared
on submission. CSRF values stay in the page's memory/DOM, not URLs or logs.

Every POST checks authentication (except login), a single exact Origin, CSRF, JSON
content type, and object payload. Logout/reconnect accept only empty objects. Host
is also checked against the configured authority to resist hostname rebinding.
No CORS origins are reflected. Error bodies are fixed and sanitized; access logging
is disabled. All responses use no-store, nosniff, no-referrer and a restrictive CSP.
Only the login page, login script and shared login stylesheet are public.

## Functional scope and API

The dark, responsive, self-contained dashboard has persistent navigation and a top
MeanGene/channel bar. Same-origin JavaScript polls status every ten seconds and
clears stale evidence on failures. Login, sign out, status cards and navigation work.
No external assets, framework, browser storage, or provider probes are used.

`GET /control/api/status` returns `status` and the current session's `csrf`.
`DashboardStatus` is a frozen typed dataclass, schema version 1, containing:

- `meangene`: `unknown` (no verified aggregate health signal).
- `channels`: validated names observed in Twitch's joined-channel list; empty means
  the UI displays unknown. Configured channel names are not presented as connected.
- `services`: typed Twitch, Discord, Hermes, Lore cards with name, state, detail,
  and optional typed reconnect capability/reason.

Twitch state is `channels_joined` only with observed names; otherwise unknown.
Absent service references are unavailable. Existing Discord, Hermes and Lore
references yield unknown, never healthy merely because they exist. No exceptions,
configuration dictionaries, credentials, provider outputs, lore records, or internal
service objects are serialized.

`POST /control/login` accepts a password; `POST /control/logout` invalidates the
session. `POST /control/api/reconnect/{twitch|discord|hermes}` always returns 409
with `supported: false` after authentication/origin/CSRF checks. No service lifecycle
methods are routed from these endpoints.

| Service | Reconnect UI | Server | Evidence |
| --- | --- | --- | --- |
| Twitch | Disabled with reason | Unsupported | No established safe isolated operation |
| Discord | Disabled with reason | Unsupported | Existing root startup/resilience is not manual reconnect |
| Hermes | Disabled with reason | Unsupported | Request/response service, no persistent connection |

Commands, Wheel, Raffle, Lore, Hermes, Audio/Media, Logs, and Settings each have a
navigation destination and explicit Sprint 1 read-only placeholder message. None
has mutation controls. Wheel redesign and Last Man Standing versus First To N are
deferred. Dashboard Lore/Hermes cards do not make their corresponding pages live.

## Lifecycle and verification

The root constructs the Control Center once after owned service composition and
before tickers/cogs start. Its application/runner are separate from the overlay.
An outer finally now covers composition and later startup as well as the existing
main gather. Shutdown closes the Control Center before the previous cleanup order.
Cleanup errors in the new listener, Twitch fallback, or completed background tasks
do not replace the original startup failure or prevent remaining cleanup attempts.
The server cleans its partial runner on setup/bind failure or cancellation, serializes
start/close, refuses duplicate start, and has no background tasks of its own.

Tests use fakes, AST-extracted composition-root code and ephemeral loopback aiohttp
facilities. No real bot/provider/audio/browser is needed. See `tests/test_control_center.py`.
Visual browser QA was intentionally not performed because browser startup is
prohibited for this task. Full discovery was avoided because other legacy tests can
import runtime modules; selected audited offline suites were used instead.

Validation commands and results (PowerShell, repository root):

```powershell
python -m py_compile bot/main.py bot/control_center.py
python -m unittest tests.test_control_center tests.test_cleanup_lifecycle -q
# Initial focused run: 32 passed.
python -m unittest tests.test_control_center tests.test_cleanup_lifecycle tests.test_audio_dependencies tests.test_twitch_watchdog tests.test_wom_overlay tests.test_raffle_state_ownership -q
# Initial broader run: 63 tests, one existing Windows subprocess decoding error.
$env:PYTHONUTF8='1'
python -m unittest tests.test_control_center tests.test_cleanup_lifecycle tests.test_audio_dependencies tests.test_twitch_watchdog tests.test_wom_overlay tests.test_raffle_state_ownership -q
# UTF-8 rerun: 63 passed; final run after added lifecycle tests: 65 passed.
New-Item -ItemType Directory -Force .control-test-temp | Out-Null
$env:TMP=(Join-Path (Get-Location) '.control-test-temp')
$env:TEMP=$env:TMP
python -m unittest tests.test_hermes_bridge tests.test_discord_operator tests.test_lore_capture tests.test_lore_store tests.test_lore_ingress -q
# 104 passed; temporary SQLite files stayed inside the workspace.
python -m compileall -q bot/main.py bot/control_center.py tests/test_control_center.py
node --check bot/control_static/dashboard.js
node --check bot/control_static/login.js
git diff --check
```

Final selected suites: 169 passing tests. Compile and JavaScript syntax checks passed.
Final diff check passed (Git reported existing CRLF conversion notices). The first
diff check caught newly introduced trailing whitespace, which was corrected.
A diff-printing inspection command also needed process-local UTF-8 for existing
Unicode source text; its rerun completed. No global encoding configuration changed.
Task-specific source, assets, tests and documentation were reviewed alongside the
complete main diff; existing unrelated working-tree changes were preserved.
