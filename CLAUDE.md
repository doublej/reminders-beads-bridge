# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Role

Bridge: Beads ↔ Apple Reminders. One reminder per bead, one list per project. Beads is the source of truth; Reminders is a view + note surface.

## Commands

Dev workflow uses `uv`. Package installs are implicit via `uv run`.

```bash
uv run rbridge doctor    # verify bd CLI, Reminders permission, registry reachable
uv run rbridge sync      # one-shot reconcile (safe, idempotent)
uv run rbridge run       # foreground poll loop
uv run rbridge status    # registry + link counts per project
uv run rbridge lint      # diagnose drift, orphans, missing tags
```

Daemon runs under launchd. After editing any module, reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.jurrejan.reminders-bridge.plist
launchctl load   ~/Library/LaunchAgents/com.jurrejan.reminders-bridge.plist
tail -f ~/Library/Logs/reminders-bridge.log
```

No test suite, linter, or formatter configured. Validate changes by running `rbridge sync` against a real project and inspecting output of `rbridge lint`. For `body.py` edits specifically, the compose → parse → compose roundtrip and the tamper / banner-drop paths are the only contract that matters.

The project lives inside the parent `python/` monorepo. `git add -A` from here stages the whole parent. Always scope: `git add reminders-bridge/<files>`.

## Architecture

Every poll cycle runs `daemon.sync_once()`, which:

1. Reads the beads-kanban registry (`~/.beads-kanban-projects.json`) via `projects.py`, filtering to directories that have `.beads/`.
2. Calls `projects_list.sync()` once to refresh the `{prefix}Projects` list (one reminder per project, completed = hidden) and returns the hidden set; then calls `projects_list.apply_hides()` to delete reminders lists for hidden projects and drop their state entries. The daemon iterates only visible projects.
3. Calls `readme.sync()` once to refresh the `{prefix}Readme` list (README + this file pinned as reminders).
4. For each visible project, calls `reconcile_project()`, which:
   - Shells out `bd list --json --all` (`beads.py`).
   - Fetches the matching Reminders list via EventKit (`reminders.py`).
   - Resolves each bead → reminder through three ordered lookups: state-file link, title-prefix match (adoption + dedup), else create.
   - Composes expected body via `body.py` (XML-tagged: `<bb:meta>`, `<bb:desc>`, `<bb:notes>`, optional `<bb:restored>` banner).
   - Diffs expected vs actual into a `Batch` (creates / updates / deletes) and commits via a single EventKit transaction.
   - Detects completed reminders → calls `bd close`.
   - Prunes reminders whose bead disappeared.
4. Persists the state map (`~/.claude/reminders-bridge-state.json`) linking bead IDs to EventKit reminder IDs.

Key invariants the architecture depends on:
- Title format `{bead-id}: {title}` — `index_by_bead_id` parses this to adopt pre-existing reminders.
- Body is fully managed except `<bb:notes>`. Any drift in `<bb:meta>` / `<bb:desc>` is treated as tamper.
- Reconcile is idempotent. A clean sync should log zero changes.
- There is no event channel from beads; freshness = poll interval (launchd overrides default 30 to 5s).

### HTTP plumbing (inert; not wired into daemon)

`api.py` and `events.py` wrap the beads-kanban HTTP API (`_management/beads-kanban/docs/API.md`): typed client + SSE consumer with polling fallback. Configured via `RBRIDGE_API_URL` / `RBRIDGE_API_TIMEOUT_S`. The daemon still uses `bd` CLI — the client exists so future work can replace `bd list --json --all` with `GET /api/issues?project=…`, subscribe to `issue.*` events instead of polling, and surface agent-session / comment metadata without changing the body contract. No call sites in daemon today. `rbridge doctor` probes `/api/agent/health` + `/api/cwd`; failure is non-fatal.

Agent-control surface exposed and partially wired:

- `!agent` marker in `<bb:notes>` → daemon scans on every cycle (`body.consume_agent_markers`) and dispatches via `_dispatch_agent_marker` in `daemon.py`. Worker is best-effort started (`agent_worker("start")`, errors swallowed) then session is enqueued via `agents_start`. Marker line is rewritten into `<bb:agent queued=… at=…/>` on success or `<bb:agent error=… at=…/>` on API failure. Activity log records `agent-queued` / `agent-error`.

### Standalone session triggers (no beads coupling)

`triggers.py` owns two lists, `Claude: Sessions` and `Codex: Sessions` (overridable via `RBRIDGE_CLAUDE_LIST` / `RBRIDGE_CODEX_LIST`). Each unchecked reminder is one pending session request:
- Title → prompt.
- Body line `cwd: <path>` (optional, `~` expanded) → working directory; default `$HOME`.
- Body line `capture: true` (optional) → run in capture mode (see below).
- Remaining body lines → appended to the prompt.

Two execution modes:

1. **Interactive (default)** — `daemon.sync_once` calls `triggers.process_all()` once per cycle. Each pending reminder is launched via `launch.launch(cwd, prompt, cmd="claude"|"codex")` which spawns a new Ghostty window via `open -na /Applications/Ghostty.app --args …` (override the bundle with `RBRIDGE_GHOSTTY_APP`; binaries via `RBRIDGE_CLAUDE_BIN` / `RBRIDGE_CODEX_BIN`). The reminder is marked completed and activity records `claude-launched` / `codex-launched`. Failed launches stay unchecked and get retried.

3. **Chat (opt-in via `chat: true`)** — `sessions.py` owns this path. Each unchecked `Claude: Sessions` reminder with `chat: true` is a persistent conversation. Body holds `cwd: …`, `chat: true`, `session: <uuid>` headers and a transcript of `you:` / `claude (ts):` blocks. `sessions.poll()` (called from `daemon.sync_once` alongside `captures.poll()`) does two things per cycle: reap finished turns (waitpid-aware zombie detection, parse `--output-format json` event array, find the `result` event, append `claude (ts):` block, write `session:` header back); and scan for pending turns — any reminder whose latest text after the last `claude (…):` line is a non-empty `you:` block (or whole body sans headers, for the first turn) launches `claude -p --output-format json [--resume <sid>]`. Reminder stays unchecked across turns; checking it just makes the daemon skip it. Unchecking + appending a new `you:` block resumes the same session id, so close/reopen is transparent. State persists in `~/.claude/reminders-bridge-sessions.json`. `triggers._process_list` skips chat-mode reminders so they never hit Ghostty or capture paths.

2. **Capture (opt-in via `capture: true`)** — `captures.launch_capture` spawns `claude -p <prompt>` or `codex exec <prompt>` as a background subprocess with stdout piped to `/tmp/rbridge-capture-<reminder>.out`. State lives in `~/.claude/reminders-bridge-captures.json` (override `RBRIDGE_CAPTURE_STATE`). The reminder stays **unchecked** while running. Each daemon cycle calls `captures.poll()`: for any pid that has exited, it reads the tempfile, appends `--- <cmd> output <ts> ---\n<output>` to the reminder body, marks it completed, deletes the tempfile, and records `claude-captured` / `codex-captured` in the activity log. Hard timeout: `RBRIDGE_CAPTURE_TIMEOUT_S` (default 1800s) — at expiry the process group is SIGTERMed and whatever stdout exists is captured anyway. While a reminder is in flight its id is filtered out of `triggers.process_all`'s pending list, so the daemon does not relaunch it. No bead state, no project visibility, no `body.py` involvement.

### Voice exchange mailboxes

`mailbox.py` + `mirror.py` own a third standalone lane (peer to triggers /
captures / sessions): one free-floating Reminders list per open agent ↔
user voice exchange. Driven by the `/voice-chat-takeout` skill from any
Claude Code session — no beads coupling, no project registry lookup.

**Surface per exchange** (slug `[a-z0-9][a-z0-9-]{0,47}`):
- `{RBRIDGE_LIST_PREFIX}{RBRIDGE_VOICE_LIST_PREFIX}<slug>` Reminders list
  (default `Beads: Voice: <slug>`). Two daemon-owned reminders:
  - `How this list works` (header) — overwritten on drift. Body mirrors
    `mailbox.HEADER_BODY_TEMPLATE`: brief path, the four optional response
    prefixes (`decision:` / `note:` / `question:` / `done`), and the exact
    `rbridge mailbox read --slug <s>` command.
  - `Brief for <slug>` — the rendered voice brief. Also daemon-owned;
    user edits get overwritten next sync (the brief is the agent's
    outgoing message; user responses go in *new* reminders).
- A silent breadcrumb reminder titled `Voice exchange open: <slug>` in
  the user's default Reminders list (the one
  `EKEventStore.defaultCalendarForNewReminders()` returns). Body carries
  `<bb:mirror slug="…"/>` so the bridge can find and clean it up. High
  priority, **no alarm, no due date** — discoverability is passive.
- State file `~/.claude/voice-mailboxes/<slug>.json` (override dir with
  `RBRIDGE_MAILBOX_DIR`) plus `<slug>.brief.md` next to it.

**Daemon GC rules** (`mailbox.sync` runs once per cycle from
`daemon.sync_once` alongside `sessions.poll()` / `captures.poll()`):
1. For each state file, refresh header + brief on drift.
2. If the Reminders list no longer exists (user deleted it), drop the
   state file + mirror reminder; record `voice-closed (list-deleted)`.
3. If any unchecked reminder has title `done` (case-insensitive), call
   `mailbox.close()` — deletes list + mirror, drops state, records
   `voice-closed (done-reminder)`.

**Discoverability** is silent by design. Plan rationale: agents may open
exchanges overnight or during meetings, so pushing notifications is wrong
by default. Signals are limited to (a) the default-list mirror reminder,
(b) high-priority flag on header / brief / mirror, (c) idempotent re-open
refreshing the mirror's modification time so it bubbles up in sort order.
No `EKAlarm`, no `osascript -e 'display notification'`, no due-dates. If
the user wants louder signals for a specific exchange they can add an
alarm in Reminders.app themselves — the daemon never overwrites alarms.

**Defensive boundary**: `projects_list.apply_hides()` skips any list name
matching `mailbox.is_voice_list_name()` so the project-hide path can never
delete a voice list, even if a beads project happened to be named
`Voice: <x>`.

**Activity log events**: `voice-opened`, `voice-response` (currently only
fires on `done` detection), `voice-closed` (with reason: `user` /
`cli` / `done-reminder` / `list-deleted`).

**New env vars** (full list also in README):
- `RBRIDGE_VOICE_LIST_PREFIX` (default `Voice: `) — inner prefix for the
  list name. Final = `{RBRIDGE_LIST_PREFIX}{this}{slug}`.
- `RBRIDGE_MAILBOX_DIR` (default `~/.claude/voice-mailboxes`).
- `RBRIDGE_MAILBOX_MIRROR` (default `true`) — set false to disable the
  default-list breadcrumb.

**CLI surface** (no beads dependency, works from any cwd):
- `rbridge mailbox open --slug X --kind REMINDERS --brief -` — read brief
  from stdin, idempotent re-open. Prints the four-line confirmation block
  (list / brief / read / close).
- `rbridge mailbox read --slug X` — JSON dump of user responses (header +
  brief filtered out). Prints a stderr warning if a `done` reminder is
  present.
- `rbridge mailbox close --slug X` — tear down.
- `rbridge mailbox refresh --slug X` — re-up reminders without changing
  the brief on disk.
- `rbridge mailbox list` — enumerate active mailboxes.

`rbridge doctor` reports the count of active mailboxes after the API
check. No daemon dependency for the CLI: `open`/`read`/`close`/`refresh`/
`list` all work even when `rbridge run` is not running — the daemon only
adds GC + drift correction on top.

Other client surface (still not wired):
- `Client.agent_worker(action)` — POST /api/agent {action: start|stop|restart}.
- `Client.agents_start(project, ticket_id, **opts)` — POST /api/agents to launch a coding session against a ticket (opts: useWorktree, model).
- `Client.agent_message(session_id, text)` — inject a user message into a running session.
- `Client.agent_session_history(session_id, project, since=None)` — GET /api/agent-sessions/:id/history; `since=<idx>` is a polling fallback (server-side filter still pending in beads-kanban — see API.md gap).
- `Client.agent_interrupt(session_id)` — DELETE /api/agents/:id.
- `events.SSEClient` — live event stream; per-session frames require the worker WebSocket on :9347 (HTTP only exposes the snapshot).

## Sync rules

### Source-of-truth (one-way, with three exceptions)
- Bead fields (title / description / priority / status / type) → reminder. Never the reverse.
- `<bb:notes>` is reminder-owned, preserved across syncs.
- Reminder → bead signals (the only ones):
  - Completed reminder → `bd close`. Edge: only fires on a False→True transition (`fresh_completion = rem.completed and not link.reminder_completed`), so a closed bead doesn't get re-closed every poll.
  - Uncompleted closed reminder → `bd reopen`. Symmetric edge: `fresh_reopen = (not rem.completed) and link.reminder_completed`.
  - **New reminder with no `bd-id:` prefix in a project list → `bd create`** (capture). Title becomes the bead title; reminder body becomes the bead description; priority defaults to p2. The reminder is then renamed to `{bead-id}: {title}` and its body restructured on the same cycle.

### Capture rules (R→B)
- Skip if title has `{prefix}: ` (already managed), if completed (don't capture+immediately close), or if reminder is already linked.
- Capture lists: only `{RBRIDGE_LIST_PREFIX}{project}` lists. Never the info list (`Readme`) or activity log (`Activity`).
- Failure mode: `bd create` exception → log warning, skip; reminder stays unprefixed and gets retried next cycle.
- State persisted right after capture (before the EventKit batch) so a crash between create and rename does not double-create on retry.

### Body syntax (enforced by `body.py`)
```
<bb:meta>[<type> · p<0-3> · <status>]</bb:meta>

<bb:desc>
<bead description verbatim>
</bb:desc>

<bb:notes>
<user-editable free text>
</bb:notes>
```
Optional prefix `<bb:restored at="ISO">msg</bb:restored>` — present only after tamper detected; auto-drops on the next clean sync. Title is exactly `{bead-id}: {bead-title}`.

### Tamper handling
On tamper (meta / desc diverge from bead, or tags missing), rewrite body from bead state, preserve `<bb:notes>`, prepend the `<bb:restored>` banner. The banner itself is informational, not tamper — the next sync drops it. If notes are unparseable, notes become empty (don't fail).

### Info list
`{prefix}Readme` holds two reminders (README, CLAUDE.md) as verbatim file contents. Overwritten on drift. Completion is user-owned; `readme.py` does not reset it. Do not store bead data here. Legacy suffixes `__info__` and `CLAUDE.MD READ ME` are deleted on startup (see `_LEGACY_SUFFIXES` in `readme.py`).

### Projects list
`{prefix}Projects` (managed by `projects_list.py`) holds one reminder per registered project. Completed reminder = project is hidden; unchecked = synced normally. Body is overwritten on drift; completion state is user-owned and is the only signal the daemon reads back. Reminders for unknown project names get pruned.

When a project is hidden, `daemon.sync_once` actively deletes its `{prefix}{project}` Reminders list (via `reminders.delete_list`) and drops its entry from the state map. This is destructive: any free-form text inside `<bb:notes>` is lost — bead state itself is unaffected. Unhide → next sync recreates the list and links from beads. The destructive choice is intentional: the goal of hiding is to drop the project from agent context, not just freeze it.

### Settings list
`{prefix}Settings` (managed by `settings.py`) holds one reminder per global toggle. Completed = enabled, unchecked = disabled. Add new toggles by appending a `Setting(key, title, body, default)` to `SETTINGS` in `settings.py` and reading the returned dict in `daemon.sync_once`. Title and body are overwritten on drift; completion is user-owned. Unknown reminders are pruned. Current toggles:
- `show_completed` — when enabled, closed beads are surfaced as completed reminders in their project list. When disabled (default), closed beads are pruned from project lists (linked reminder gets deleted next sync). Bead state itself is unaffected; this only controls whether they appear in Reminders.

When `show_completed=False`, `reconcile_project` short-circuits closed beads at the top of the issue loop: it deletes any linked reminder, drops the link, and skips create logic. When `True`, closed beads are syncable, and creates pre-set the EventKit `completed` flag so the new reminder lands already checked.

### Activity log
`{prefix}Activity` holds one rolling reminder `Recent activity` with the last ~200 events (created / closed / reopened / captured / restored / pruned / status change / hidden). Backed by `~/.claude/reminders-bridge-activity.jsonl` (override `RBRIDGE_ACTIVITY`). Daemon-owned, not user-editable — drift is overwritten next sync. Legacy suffix `__log__` is deleted on startup (see `_LEGACY_SUFFIXES` in `activity.py`).

### Lint
`rbridge lint` is read-only. Codes: `missing-meta`, `missing-desc`, `missing-notes`, `bad-status`, `drift`, orphan. The daemon does not fail-stop on lint issues; it rewrites on the next sync.

## Constraints for agents editing this repo

- Sync directions are fixed: B→R for fields, R→B for completion (`bd close`), uncomplete (`bd reopen`), and capture (`bd create`). Do not add more without explicit approval.
- Do not parse `<bb:notes>` for structured data; it is free-form user text.
- Do not touch reminders outside `{RBRIDGE_LIST_PREFIX}{project}` lists.
- iOS Claude / external agents: write into `Beads: <project>` lists for capture, never into `Readme` or `Activity` (drift gets overwritten silently).
- Do not add new `<bb:*>` tags without updating `body.py` parser, lint codes, and this doc together.
- New bead status values: add to `VALID_STATUSES` in `body.py` and the README env-var section.
- Keep modules under ~150 lines. `body.py` owns all body concerns; `readme.py` owns the info list.
- `body.py` change: verify compose → parse roundtrip, tamper detection, and banner drop by composing twice against the same bead.
