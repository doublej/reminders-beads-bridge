# CLAUDE.md

Guidance for Claude Code working in this repo. This file is the **map**; depth
lives in the docs it points to. Keep it under ~200 lines — push detail down.

## Role

Bridge: Beads ↔ Apple Reminders. One reminder per bead, one list per project.
Beads is the source of truth; Reminders is a view + note surface.

<vocabulary>
Canonical terms are defined in GLOSSARY.md — use these names exactly (they are
this project's ubiquitous language). Core: bead (the record) vs reminder (its
mirror), link, reconcile, lane, capture, tamper. Voice roles: user / project
agent / voice agent — never blur them (see GLOSSARY → "Surfaces"). Full
glossary: ./GLOSSARY.md
</vocabulary>

## Design stance (read before proposing any agent-facing change)

The primary driver is the **Claude voice session, which we do not control**: its
only tool is Apple Reminders CRUD, it can't be given new tools / a new prompt /
an MCP server, and every write is fire-and-forget (it can't read the result in
the same turn). The Reminders tunnel exists *because* of this. What follows
bounds every design:

- **All leverage is daemon-side.** Change what the daemon writes for the agent
  to read, how it interprets the agent's writes, and how it rewrites reminders
  in place — never the agent itself. An MCP/API "for capable agents" cannot help
  the voice agent; it only helps other, controllable agents.
- **Safety = reversibility + acks, never confirmation.** A check → "are you
  sure?" → check-again handshake is theater: the agent is executing the user's
  stated intent and will just satisfy the second check, and no human watches a
  checkbox mid-call. Make destructive actions *undoable* (snapshot before
  delete), don't gate them.
- **Acknowledge via in-place rewrites.** Fire-and-forget writes need an ack the
  agent reads next turn — rewrite the reminder to `ok:`/`error:`/`sent:`. The
  nav lane already does this (`fetch:`→`file:`/`blocked:`) and is the template
  for every agent→daemon action; prefer it over adding checkbox meanings.
- Prompt-borne safety (docs/AGENT.md rules) degrades with context length, model
  swaps, and cold starts — prefer daemon-enforced + visible-in-store.

## Commands

Dev workflow uses `uv`. Installs are implicit via `uv run`.

```bash
uv run rbridge doctor    # verify bd CLI, Reminders permission, registry, lanes
uv run rbridge sync      # one-shot reconcile (safe, idempotent)
uv run rbridge run       # foreground poll loop
uv run rbridge serve     # read-only at-a-glance HTTP endpoint (token-gated, 127.0.0.1)
uv run rbridge status    # registry + link counts per project
uv run rbridge lint      # diagnose drift, orphans, missing tags
uv run rbridge prime     # emit the voice-takeout playbook (--json for the contract)
```

Daemon runs under launchd. After editing any module, reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.jurrejan.reminders-bridge.plist
launchctl load   ~/Library/LaunchAgents/com.jurrejan.reminders-bridge.plist
tail -f ~/Library/Logs/reminders-bridge.log
```

The user-facing `rbridge` is a separate `uv tool` install; after repo changes
run `uv tool install --force --reinstall .` to update it (the daemon `.venv`
updates independently).

No test suite, linter, or formatter is wired beyond ruff/mypy (`uv run --extra
dev ruff check` / `mypy`). Validate behavior with `rbridge sync` against a real
project + `rbridge lint`. For `body.py`, the only contract that matters is the
compose → parse → compose roundtrip and the tamper / banner-drop paths — see
`.claude/rules/body-contract.md`.

This repo is its own git root (not the parent `python/` monorepo). Plain
`git add <path>` is correctly scoped; there is no parent to leak into.

## Architecture

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

Load-bearing invariants:
- Title format `{bead-id}: {title}` — parsed to adopt pre-existing reminders.
- Body is fully daemon-managed **except** `<bb:notes>`. Drift in
  `<bb:meta>`/`<bb:desc>` is tamper.
- Reconcile is idempotent — a clean sync logs zero changes.
- No event channel from beads; freshness = the lane's `_LANE_EVERY_S` interval
  on idle ticks (EventKit edits wake all lanes immediately). `poll_ms`/launchd
  set the wake cadence, floored by `RBRIDGE_MIN_WAIT_S`.

### The lanes (one line each; modules in parens)

- **beads reconcile** (`beads.py`, `reminders.py`, `body.py`, `link.py`, `state.py`) — the core B↔R sync above.
- **HTTP plumbing** (`api.py`, `events.py`) — typed beads-kanban client + SSE. **Inert**: built, not wired into the daemon (`bd` CLI is still the source). `doctor` probes it; failure is non-fatal.
- **session triggers** (`triggers.py`, `launch.py`, `captures.py`, `sessions.py`) — `_rb_claude_sessions`/`_rb_codex_sessions`; each unchecked reminder is a pending session in interactive / capture / chat / fixer mode. See `docs/REFERENCE.md` → "Sessions".
- **claude tabs** (`tabs.py`, `tabsbody.py`, `ghostty.py`, `transcript.py`, `inject.py`) — mirror live Ghostty Claude tabs into `_rb_claude_tabs`; `send:` text + completion in **one** write types into the live tab (completion is the trigger; GUI inject, needs Accessibility). A bare `expand:`/`collapse:` line (content-triggered, no checkbox — completion is taken) swaps the compact tail for the full recent transcript. See `docs/REFERENCE.md` → "Claude tabs".
- **voice mailboxes** (`mailbox.py`, `mirror.py`, `navigation.py`, `sandbox.py`, `prime.py`, `primer.md`) — one `_rb_voice_<slug>` list per exchange; file-nav serves `fetch:`/`grep:`/`tree:`. Authoring playbook = `rbridge prime` (`primer.md`); voice-agent directive = `docs/AGENT.md`; vocabulary + flow = `docs/REFERENCE.md`; editing rules = `.claude/rules/voice-surfaces.md`.
- **controls** (`settings.py`, `projects_list.py`, `readme.py`, `activity.py`, `dashboard.py`) — the daemon-owned `_rb_settings` / `_rb_beads_projects` / `!_rb_readme` / `_rb_activity` / `_rb_dashboard` lists (Sync rules below).
- **dashboard endpoint** (`snapshot.py`, `dashpages.py`, `server.py`, `dashboard.py`, `serverctl.py`) — read-only HTTP at-a-glance view + drill-down (`/`, `/project/<name>`, `/sessions`, `/tabs`, `/voice`, `/activity`), compact markdown or `?format=json`. `snapshot.py` assembles each view (files/`bd`/`ps` + read-only EventKit for sessions); `dashpages.py` renders markdown; `server.py` routes; `dashboard.py` mints the rotating token + surfaces the live URL in `_rb_dashboard`; `serverctl.py` is the daemon-owned `serve` subprocess, toggled by the `Dashboard server` setting. Read-only — writes stay in rbridge. See `docs/REFERENCE.md` → "Dashboard endpoint".
- **agent dispatch** (`agent_marker.py`) — `!agent` in `<bb:notes>` → enqueue a coding session; rewritten to `<bb:agent …/>`.
- **command queue** (`commands.py`, `body.py`) — `_rb_commands`; a `close:`/`reopen:`/`note:` reminder is run against the addressed bead and rewritten in place to `ok:`/`error:` (the nav-lane pattern → ack/nack, no checkbox overload). See `docs/AGENT.md` → `_rb_commands`.

## Sync rules (the editing contract)

### Source-of-truth — one-way B→R, with three R→B exceptions
- Bead fields (title/description/priority/status/type) → reminder. Never reverse.
- `RBRIDGE_STATUSES` is a **creation gate, not a retention gate**: a bead becomes
  a reminder only while its status is listed (or closed + `show_completed`); once
  created, a non-listed status (e.g. `blocked`) keeps the reminder and syncs the
  new status into `<bb:meta>` — pruned only when the bead leaves `bd list`.
- `<bb:notes>` is reminder-owned, preserved across syncs (never discarded by a
  status change).
- The only R→B signals: completed reminder → `bd close` (fires on False→True
  only); uncompleted closed reminder → `bd reopen`; new unprefixed reminder in a
  `_rb_beads_<project>` list → `bd create` (capture).

### Capture (R→B)
- Skip iff the leading `<token>:` is an existing bead id, the reminder is
  completed, or it is already linked. A non-id prefix (`Bug:`) is captured.
- Only `_rb_beads_<project>` lists. Never `!_rb_readme` / `_rb_activity`.
- `bd create` failure → warn + skip (retried next cycle). State persists right
  after capture (before the EventKit batch) so a crash can't double-create.

### Body syntax + tamper (enforced by `body.py`)
```
<bb:meta>[<type> · p<0-3> · <status>]</bb:meta>

<bb:desc>
<bead description verbatim>
</bb:desc>

<bb:notes>
<user-editable free text>
</bb:notes>
```
Optional leading `<bb:restored at="ISO">msg</bb:restored>` after tamper —
auto-drops next clean sync. On tamper, rewrite from bead state, preserve
`<bb:notes>` (empty if unparseable — don't fail), prepend the banner. Title is
exactly `{bead-id}: {bead-title}`. Editing `body.py` → see
`.claude/rules/body-contract.md`.

### Daemon-owned lists (invariants; full behavior in `docs/REFERENCE.md`)
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

### Lint
`rbridge lint` is read-only. Codes: `missing-meta`, `missing-desc`,
`missing-notes`, `bad-status`, `drift`, orphan. Never fail-stop — rewritten next sync.

## Constraints for agents editing this repo

- Sync directions are fixed (B→R fields; R→B close/reopen/capture). Do not add
  more without explicit approval.
- `<bb:notes>` is free-form user text — never parse it for structured data.
- Never touch reminders outside `_rb_beads_<project>` lists from the capture path.
- Adding a `<bb:*>` tag or a bead status → update `body.py` parser, lint codes,
  `VALID_STATUSES`, this doc, and `.claude/rules/body-contract.md` together.
- Keep modules under ~150 lines. `body.py` owns body concerns; `tabsbody.py` /
  `primer.md` own the tab / voice-brief strings.
- Voice surfaces have split readers — see `.claude/rules/voice-surfaces.md`
  before editing `mailbox.py` / `navigation.py` / `primer.md` / `docs/AGENT.md`.

## Deeper context

- `docs/REFERENCE.md` — operator guide: config/env vars, every list, sessions, tabs, voice vocabulary table + flow.
- `docs/AGENT.md` — the `!_rb_readme` directive (voice/in-Reminders agent).
- `src/reminders_bridge/primer.md` — `rbridge prime`: voice-takeout authoring playbook.
- `GLOSSARY.md` — canonical terms.
- `docs/architecture.mmd` — diagram.
- `.claude/rules/` — path-scoped editing rules (load when matching files are read).
