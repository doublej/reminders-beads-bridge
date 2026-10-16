# CLAUDE.md

This file is the **map**; depth lives in the docs it points to — push detail down.

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

The primary driver is the **Claude voice session, which we do not control**: its only tool is
Apple Reminders CRUD (no new tools, prompt or MCP server), and every write is fire-and-forget.

- **All leverage is daemon-side** — change what the daemon writes, how it reads the agent's writes,
  and how it rewrites reminders in place. An MCP/API cannot help the voice agent.
- **Safety = reversibility + acks, never confirmation.** An "are you sure?" handshake is theater
  (the agent just satisfies it). Make destructive actions undoable (snapshot before delete).
- **Acknowledge via in-place rewrites** (`ok:`/`error:`/`sent:`), read next turn. The nav lane
  (`fetch:`→`file:`/`blocked:`) is the template; prefer it over new checkbox meanings.
- Prompt-borne safety (`docs/AGENT.md`) degrades with context, model swaps and cold starts —
  prefer daemon-enforced, visible-in-store.

## Commands

```bash
uv run rbridge doctor    # verify bd CLI, Reminders permission, registry, lanes
uv run rbridge sync      # one-shot reconcile (safe, idempotent)
uv run rbridge run       # foreground poll loop
uv run rbridge serve     # read-only at-a-glance HTTP endpoint (token-gated, 127.0.0.1)
uv run rbridge status | lint | prime   # links per project / drift diagnosis / voice-takeout playbook
```

- The daemon runs under launchd: after editing any module, `launchctl unload` + `load`
  `~/Library/LaunchAgents/com.jurrejan.reminders-bridge.plist`; log `~/Library/Logs/reminders-bridge.log`.
- The user-facing `rbridge` is a separate `uv tool` install — `uv tool install --force --reinstall .` after changes.
- Checks: `uv run --extra dev ruff check` / `mypy` only, no test suite. Validate with `rbridge sync`
  against a real project + `rbridge lint`; `body.py` changes follow `.claude/rules/body-contract.md`.
- This repo is its own git root (not the `python/` monorepo).

## Architecture

Every poll `daemon.sync_once()` loads the registry (dirs with `.beads/`), refreshes the project /
readme lists, reconciles each visible project (`bd list` → Reminders list → link/adopt/create →
compose body → one EventKit `Batch`), runs the standalone lanes, then persists
`~/.claude/reminders-bridge-state.json`. Full walkthrough and the lane → module map: `docs/architecture.md`.

- Each lane is gated by `daemon._due()`: an EventKit wakeup (`woke`) runs every lane at once; idle
  ticks run a lane only after its `_LANE_EVERY_S`. Loop wait floored at `RBRIDGE_MIN_WAIT_S`.
- **Reconcile's second gate** (`_beads_quiet()`): every `bd` call starts a never-exiting
  `dolt sql-server` (~110 MB), so idle ticks skip projects whose Dolt journal (`beads.journal_size`)
  hasn't moved and reap the server after `RBRIDGE_DOLT_IDLE_STOP_S`. **Do not swap the change
  signal** for `.beads/last-touched` (misses reopen/delete) or the Dolt `manifest` (misses live
  writes, reaper thrashes). Run `testkit/gate_check.py` after a `bd` upgrade.
- Title format `{bead-id}: {title}` — parsed to adopt pre-existing reminders.
- Body is daemon-managed **except** `<bb:notes>`; drift in `<bb:meta>`/`<bb:desc>` is tamper.
- Reconcile is idempotent — a clean sync logs zero changes.
- HTTP plumbing (`api.py`, `events.py`) is **inert**: built, not wired in; `bd` CLI is the source.

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
Optional leading `<bb:restored at="ISO">msg</bb:restored>` banner after tamper, dropped on the
next clean sync. Tamper handling and the round-trip law: `.claude/rules/body-contract.md`.

### Daemon-owned lists (full behaviour: `docs/architecture.md`, `docs/REFERENCE.md`)
- **`_rb_beads_projects`** — checked = hidden, which **deletes** that project's list (destroys
  `<bb:notes>`; bead state safe). Intentional. Unhide → recreated next sync.
- **`_rb_settings`** — one reminder per control, daemon-owned tag body (self-heals). Add one:
  append a `Setting(...)` to `SETTINGS`, read it in `sync_once`.
- **`!_rb_readme`** (`docs/AGENT.md` verbatim, never bead data), **`_rb_activity`**, **`_rb_dashboard`**
  — daemon-owned, drift overwritten.
- Startup renames migrate pre-`_rb_` names in place; only `_LEGACY_NAMES` are deleted.

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

- `docs/architecture.md` — the poll loop, every lane and its modules, daemon-owned lists in full.
- `docs/REFERENCE.md` — operator guide: config/env vars, every list, sessions, tabs, voice vocabulary table + flow.
- `docs/AGENT.md` — the `!_rb_readme` directive (voice/in-Reminders agent).
- `src/reminders_bridge/primer.md` — `rbridge prime`: voice-takeout authoring playbook.
- `GLOSSARY.md` — canonical terms.
- `docs/architecture.mmd` — diagram.
- `.claude/rules/` — path-scoped editing rules (load when matching files are read).
