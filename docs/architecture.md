# reminders-bridge — architecture

Developer walkthrough of the daemon loop and its lanes. Operator-facing behaviour lives in `docs/REFERENCE.md`; the diagram is `docs/architecture.mmd`.

## The poll loop

Every poll, `daemon.sync_once()` runs the lanes in order:

1. Load the registry (`projects.py`) — dirs with `.beads/`.
2. `projects_list.sync()` → refresh `_rb_beads_projects`, return the hidden set;
   `apply_hides()` deletes hidden projects' lists. Only visible projects iterate.
3. `readme.sync()` → pin `docs/AGENT.md` into `!_rb_readme`.
4. Per visible project, `reconcile_project()`: `bd list --json --all` (`beads.py`)
   → fetch the Reminders list (`reminders.py`) → resolve each bead→reminder
   (link → title-prefix adoption → create) → compose body (`body.py`) → diff into
   a `Batch` (creates/updates/deletes) committed in one EventKit transaction →
   detect completed→`bd close`, prune vanished beads.
5. Standalone lanes (no beads coupling), each a peer call: `triggers.process_all`,
   `captures.poll`, `sessions.poll`, `tabs.sync`, `mailbox.sync`, `settings.sync`.
6. Persist the state map (`~/.claude/reminders-bridge-state.json`).

Each lane (incl. beads reconcile) is gated by `_due()` in `daemon.py`: on an
EventKit-change wakeup (`woke`) every lane runs immediately; on a pure-interval
idle tick a lane runs only when its `_LANE_EVERY_S` interval has elapsed. This
keeps idle CPU low without changing sync semantics — interactive edits stay
instant via `woke`; only non-Reminders changes (new bead/tab, finished child)
wait out the interval. The loop wait is also floored at `RBRIDGE_MIN_WAIT_S` and
skips the watcher settle-pump on cycles that wrote nothing.

Reconcile carries a second gate on top of `_due()`, because it is the one lane
whose cost is a *process*: any `bd` call auto-starts a detached, never-exiting
`dolt sql-server` per project (~110MB). On an idle tick `_beads_quiet()` skips a
project whose Dolt journal (`beads.journal_size`) has not moved — nothing on the
beads side can have happened — and after `RBRIDGE_DOLT_IDLE_STOP_S` reaps that
project's server. Reminder-side changes never reach the journal; they arrive as
`woke`, which forces a full pass. `RBRIDGE_RECONCILE_FULL_S` is the fallback for
the observer-failed-to-install case only. **Do not swap the change signal** for
`.beads/last-touched` or the Dolt `manifest` — both were tried and fail (the
first misses `reopen`/`delete`, the second misses every live write and moves on
server stop, which makes the reaper thrash). `testkit/gate_check.py` asserts the
two properties the signal must keep; run it after a `bd` upgrade.

Load-bearing invariants:
- Title format `{bead-id}: {title}` — parsed to adopt pre-existing reminders.
- Body is fully daemon-managed **except** `<bb:notes>`. Drift in
  `<bb:meta>`/`<bb:desc>` is tamper.
- Reconcile is idempotent — a clean sync logs zero changes.
- No event channel from beads; freshness = the lane's `_LANE_EVERY_S` interval
  on idle ticks (EventKit edits wake all lanes immediately). `poll_ms`/launchd
  set the wake cadence, floored by `RBRIDGE_MIN_WAIT_S`.

## The lanes (one line each; modules in parens)

- **beads reconcile** (`beads.py`, `reminders.py`, `body.py`, `link.py`, `state.py`) — the core B↔R sync above.
- **HTTP plumbing** (`api.py`, `events.py`) — typed beads-kanban client + SSE. **Inert**: built, not wired into the daemon (`bd` CLI is still the source). `doctor` probes it; failure is non-fatal.
- **session triggers** (`triggers.py`, `launch.py`, `captures.py`, `sessions.py`) — `_rb_claude_sessions`/`_rb_codex_sessions`; each unchecked reminder is a pending session in interactive / capture / chat / fixer mode. See `docs/REFERENCE.md` → "Sessions".
- **claude tabs** (`tabs.py`, `tabsbody.py`, `ghostty.py`, `transcript.py`, `inject.py`) — mirror live Ghostty Claude tabs into `_rb_claude_tabs`; `send:` text + completion in **one** write types into the live tab (completion is the trigger; GUI inject, needs Accessibility). A bare `expand:`/`collapse:` line (content-triggered, no checkbox — completion is taken) swaps the compact tail for the full recent transcript. See `docs/REFERENCE.md` → "Claude tabs".
- **voice mailboxes** (`mailbox.py`, `mirror.py`, `navigation.py`, `sandbox.py`, `prime.py`, `primer.md`) — one `_rb_voice_<slug>` list per exchange; file-nav serves `fetch:`/`grep:`/`tree:`. Authoring playbook = `rbridge prime` (`primer.md`); voice-agent directive = `docs/AGENT.md`; vocabulary + flow = `docs/REFERENCE.md`; editing rules = `.claude/rules/voice-surfaces.md`.
- **controls** (`settings.py`, `projects_list.py`, `readme.py`, `activity.py`, `dashboard.py`) — the daemon-owned `_rb_settings` / `_rb_beads_projects` / `!_rb_readme` / `_rb_activity` / `_rb_dashboard` lists (Sync rules below).
- **dashboard endpoint** (`snapshot.py`, `dashpages.py`, `server.py`, `dashboard.py`, `serverctl.py`) — read-only HTTP at-a-glance view + drill-down (`/`, `/project/<name>`, `/sessions`, `/tabs`, `/voice`, `/activity`), compact markdown or `?format=json`. `snapshot.py` assembles each view (files/`bd`/`ps` + read-only EventKit for sessions); `dashpages.py` renders markdown; `server.py` routes; `dashboard.py` mints the rotating token + surfaces the live URL in `_rb_dashboard`; `serverctl.py` is the daemon-owned `serve` subprocess, toggled by the `Dashboard server` setting. Read-only — writes stay in rbridge. See `docs/REFERENCE.md` → "Dashboard endpoint".
- **agent dispatch** (`agent_marker.py`) — `!agent` in `<bb:notes>` → enqueue a coding session; rewritten to `<bb:agent …/>`.
- **manager lane** (`manager.py`) — `_rb_manager`; any unchecked reminder is free text to the deckhand manager (`POST /manager/say`), acked in place to `sent:` the same cycle, steps appended as `GET /manager?since=` brings them, `reply:` when done. Inert without `~/Library/Application Support/Deckhand/token`.
- **command queue** (`commands.py`, `body.py`) — `_rb_commands`; a `close:`/`reopen:`/`note:` reminder is run against the addressed bead and rewritten in place to `ok:`/`error:` (the nav-lane pattern → ack/nack, no checkbox overload). See `docs/AGENT.md` → `_rb_commands`.

## Daemon-owned lists
- **`_rb_beads_projects`** — checked = hidden, which **deletes** that project's
  list (destroys `<bb:notes>`; bead state safe). Intentional: hiding drops the
  project from agent context. Unhide → recreated next sync.
- **`_rb_settings`** — one reminder per control; body is a daemon-owned
  `<rb:toggle/>`/`<rb:action/>`/`<rb:value>` tag (self-heals). `show_completed`
  (toggle), `dashboard` (toggle → daemon spawns/reaps the `serve` child via
  `serverctl`), `restart` (action → `os.execv`), `poll_ms` (value, clamped
  100–600000, live). Add one: append a `Setting(...)` to `SETTINGS`, read it in
  `sync_once`.
- **`!_rb_readme`** — `docs/AGENT.md` verbatim; `!` sorts first; completion
  user-owned. Don't store bead data.
- **`_rb_activity`** — rolling ~200-event log, daemon-owned, drift overwritten.
- **`_rb_dashboard`** — one reminder: the live `rbridge serve` URL with a rotating
  token (HMAC of a shared secret, time-windowed). Daemon-owned, drift overwritten;
  body notes when the server is down. Agent entry point for the at-a-glance view.
- Lossless calendar renames migrate pre-`_rb_` list names in place; only dead
  historical names are deleted on startup (`_LEGACY_NAMES`).
