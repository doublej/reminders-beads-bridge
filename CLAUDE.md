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
3. Calls `readme.sync()` once to refresh the `! {prefix}Readme` list (pins `docs/AGENT.md` as a reminder for the iOS/web Claude agent reading inside Reminders). Leading `! ` is intentional — sorts the list first on `reminder_list_search_v0` so cold-start agents find the directive immediately.
4. For each visible project, calls `reconcile_project()`, which:
   - Shells out `bd list --json --all` (`beads.py`).
   - Fetches the matching Reminders list via EventKit (`reminders.py`).
   - Resolves each bead → reminder through three ordered lookups: state-file link, title-prefix match (adoption + dedup), else create.
   - Composes expected body via `body.py` (XML-tagged: `<bb:meta>`, `<bb:desc>`, `<bb:notes>`, optional `<bb:restored>` banner).
   - Diffs expected vs actual into a `Batch` (creates / updates / deletes) and commits via a single EventKit transaction.
   - Detects completed reminders → calls `bd close`.
   - Prunes reminders whose bead disappeared.
5. Persists the state map (`~/.claude/reminders-bridge-state.json`) linking bead IDs to EventKit reminder IDs.

Key invariants the architecture depends on:
- Title format `{bead-id}: {title}` — `index_by_bead_id` parses this to adopt pre-existing reminders.
- Body is fully managed except `<bb:notes>`. Any drift in `<bb:meta>` / `<bb:desc>` is treated as tamper.
- Reconcile is idempotent. A clean sync should log zero changes.
- There is no event channel from beads; freshness = poll interval (launchd overrides default 30 to 5s).

### HTTP plumbing (inert; not wired into daemon)

`api.py` and `events.py` wrap the beads-kanban HTTP API (`_management/beads-kanban/docs/API.md`): typed client + SSE consumer with polling fallback. Configured via `RBRIDGE_API_URL` / `RBRIDGE_API_TIMEOUT_S`. The daemon still uses `bd` CLI — the client exists so future work can replace `bd list --json --all` with `GET /api/issues?project=…`, subscribe to `issue.*` events instead of polling, and surface agent-session / comment metadata without changing the body contract. No call sites in daemon today. `rbridge doctor` probes `/api/agent/health` + `/api/cwd`; failure is non-fatal.

Agent-control surface exposed and partially wired:

- `!agent` marker in `<bb:notes>` → daemon scans on every cycle (`body.consume_agent_markers`) and dispatches via `agent_marker.dispatch`, invoked from the `consume_agent_markers` callback inside `daemon._diff_existing`. Worker is best-effort started (`agent_worker("start")`, errors swallowed) then session is enqueued via `agents_start`. Marker line is rewritten into `<bb:agent queued=… at=…/>` on success or `<bb:agent error=… at=…/>` on API failure. Activity log records `agent-queued` / `agent-error`.

### Standalone session triggers (no beads coupling)

`triggers.py` owns two lists, `Claude: Sessions` and `Codex: Sessions` (overridable via `RBRIDGE_CLAUDE_LIST` / `RBRIDGE_CODEX_LIST`). Each unchecked reminder is one pending session request:
- Title → prompt.
- Body line `cwd: <path>` (optional, `~` expanded) → working directory; default `$HOME`.
- Body line `capture: true` (optional) → run in capture mode (see below).
- Remaining body lines → appended to the prompt.

Three execution modes:

1. **Interactive (default)** — `daemon.sync_once` calls `triggers.process_all()` once per cycle. Each pending reminder is launched via `launch.launch(cwd, prompt, cmd="claude"|"codex")` which spawns a new Ghostty window via `open -na /Applications/Ghostty.app --args …` (override the bundle with `RBRIDGE_GHOSTTY_APP`; binaries via `RBRIDGE_CLAUDE_BIN` / `RBRIDGE_CODEX_BIN`). The reminder is marked completed and activity records `claude-launched` / `codex-launched`. Failed launches stay unchecked and get retried.

2. **Capture (opt-in via `capture: true`)** — `captures.launch_capture` spawns `claude -p <prompt>` or `codex exec <prompt>` as a background subprocess with stdout piped to `/tmp/rbridge-capture-<reminder>.out`. State lives in `~/.claude/reminders-bridge-captures.json` (override `RBRIDGE_CAPTURE_STATE`). The reminder stays **unchecked** while running. Each daemon cycle calls `captures.poll()`: for any pid that has exited, it reads the tempfile, appends `--- <cmd> output <ts> ---\n<output>` to the reminder body, marks it completed, deletes the tempfile, and records `claude-captured` / `codex-captured` in the activity log. Hard timeout: `RBRIDGE_CAPTURE_TIMEOUT_S` (default 1800s) — at expiry the process group is SIGTERMed and whatever stdout exists is captured anyway. While a reminder is in flight its id is filtered out of `triggers.process_all`'s pending list, so the daemon does not relaunch it. No bead state, no project visibility, no `body.py` involvement.

3. **Chat (opt-in via `chat: true`)** — `sessions.py` owns this path. Each unchecked `Claude: Sessions` reminder with `chat: true` is a persistent conversation. Body holds `cwd: …`, `chat: true`, `session: <uuid>` headers and a transcript of `you:` / `claude (ts):` blocks. `sessions.poll()` (called from `daemon.sync_once` alongside `captures.poll()`) does two things per cycle: reap finished turns (waitpid-aware zombie detection, parse `--output-format json` event array, find the `result` event, append `claude (ts):` block, write `session:` header back); and scan for pending turns — any reminder whose latest text after the last `claude (…):` line is a non-empty `you:` block (or whole body sans headers, for the first turn) launches `claude -p --output-format json [--resume <sid>]`. Reminder stays unchecked across turns; checking it just makes the daemon skip it. Unchecking + appending a new `you:` block resumes the same session id, so close/reopen is transparent. State persists in `~/.claude/reminders-bridge-sessions.json`. `triggers._process_list` skips chat-mode reminders so they never hit Ghostty or capture paths.

### Claude tabs lane (live Ghostty mirror, no beads coupling)

`tabs.py` + `tabsbody.py` + `inject.py` + `ghostty.py` + `transcript.py` own a lane (peer to triggers / captures / sessions / mailbox) that mirrors **live Ghostty tabs running Claude Code** into the `Claude: Tabs` list (override `RBRIDGE_TABS_LIST`; deliberately drops the `Beads: ` prefix). `tabs.sync()` runs once per cycle from `daemon.sync_once`. Discovery learned from the `node/claude-activity-watcher` tool.

- **Discovery** (`ghostty.discover()`): parse `ps -axo pid=,ppid=,tty=,command=`, find the Ghostty root pid(s) (command contains `Ghostty.app/Contents/MacOS/ghostty`), then keep every process whose argv0 basename is `claude`, has a real tty, is not `claude daemon …`, and whose ppid chain reaches a Ghostty root. cwd via `lsof`; one `Tab` per process. **Important:** uses absolute `/bin/ps` and `/usr/sbin/lsof` — under launchd `PATH` is minimal and `lsof` won't resolve by name.
- **Session resolution** (`transcript.resolve(pid, cwd)`): prefer the authoritative `~/.claude/sessions/<pid>.json` (exact `sessionId`, `cwd`, `status`); fall back to newest `*.jsonl` in `~/.claude/projects/<encoded-cwd>/`. `encode_cwd` replaces `/`, `.`, `_` with `-` (verified against the live dir — dotted segments like `.claude-worktrees` encode to `--claude-...`). The **title** used for matching is the jsonl's last `aiTitle` (Claude's generated tab title), falling back to the session file's `name`. This is the same string Claude paints onto the Ghostty tab.
- **Reminder per tab** keyed by pid (`priority 1`, title `{aiTitle|project} · {tty}`). Body is daemon-owned, overwritten each cycle: header (`tab` title / `project`·`status` / `cwd` / `tty`·`pid`·`mode` / `session`), a live transcript tail (last `RBRIDGE_TABS_TAIL_MSGS`, default 6), a `sent` log, and a trailing `send:` region. `tabsbody.py` owns all body string concerns (peer to `body.py`); `tabsbody.parse_send` is the **only** thing read back from the user.
- **Send (R→GUI, the lane's one write-back signal): types into the live tab, as the user would.** Type under `send:` then **check the reminder** — completion is the explicit send trigger (avoids firing on half-typed text). `tabs.sync` reads the payload and calls `inject.type_into_tab(title, text)`. macOS gives **no silent path** (TIOCSTI is root-only; writing to the tty only paints the display), so `inject.py` drives the GUI via `osascript`/System Events: activate Ghostty, find the tab whose tab-bar radio button (or single-surface window) title — **first 2 chars stripped** (status glyph + space) — equals the target title, `AXPress`/`AXRaise` to focus it, **re-verify the focused title**, then `Cmd+V` (paste, clipboard saved/restored) + Return. Every failure raises `InjectError` *before* any keystroke, so a wrong/unreachable tab aborts instead of mis-typing. On success → append `you (ts): …`, clear `send:`, uncheck. On failure → keep the payload under `send:` + show `last_error`, uncheck (no auto-retry storm; user re-checks to retry). **Constraints:** needs Accessibility permission for the daemon's process, and the tab must be on the **active Space** (cross-Space windows are invisible to AX). There is a sub-200 ms race if the user switches tabs between focus-verify and paste.
- **GC:** a tab whose pid is gone → delete its reminder + state (`tab-closed`). This lane is a live mirror, not a chat store. State: `~/.claude/reminders-bridge-tabs.json` (per-tab reminder id / sent log / last_error). Activity events: `tab-opened`, `tab-send`, `tab-send-failed`, `tab-closed`. CLI: `rbridge tabs` (read-only listing); `rbridge doctor` reports the live tab count + Accessibility state.

### Voice exchange mailboxes

`mailbox.py` + `mirror.py` own a third standalone lane (peer to triggers /
captures / sessions): one free-floating Reminders list per open agent ↔
user voice exchange. Driven by the `/voice-chat-takeout` skill from any
Claude Code session — no beads coupling, no project registry lookup.

**Vocabulary** (canonical table in `README.md` → "Voice exchange mailboxes" →
"Vocabulary"; keep usage consistent across this file, `docs/AGENT.md`, the
skill `~/.claude/skills/voice-chat-takeout/`, and the
`/voice-deep-takeout` command):

Three roles:
- **user** — the human. Third-person inside the brief; never addressed
  directly in writing (the voice agent speaks *with* the user out loud).
- **project agent** — the Claude Code session the user works in.
  Composes the brief. Self-refers as "I" inside the brief.
- **voice agent** — the agent on the phone the user talks to. Reads
  the brief. Addressed as "you" inside the brief. Currently Claude
  Voice in practice; brief should never assume a specific product.

Surface terms:
- **voice exchange** / **mailbox** — the open conversation, identified by slug.
- **brief** — handoff doc the project agent composes for the voice agent.
- **exchange list** — `{voice prefix}<slug>` Reminders list (default `Voice: <slug>`).
- **header / brief / mirror reminder** — daemon-owned reminders.
- **response** + **response kind** (`decision` / `note` / `question` /
  `deferred` / `done` / `free`) — user-added reminders in the
  exchange list. `deferred` is for explicit punts (talked about, no
  decision yet, revisit later).
- **writeback contract** — REMINDERS-brief block naming the list + prefixes.
- **drain** — the project agent reads responses via `rbridge mailbox read`.
- **takeout** — user-facing skill: `/voice-chat-takeout` (mailbox flow) or
  `/voice-deep-takeout` (deep paste-into-voice flow).

**Surface per exchange** (slug `[a-z0-9][a-z0-9-]{0,47}`):
- `{RBRIDGE_VOICE_LIST_PREFIX}<slug>` Reminders list
  (default `Voice: <slug>`). **Independent of `RBRIDGE_LIST_PREFIX`** —
  the voice flow has no beads coupling, so the list deliberately drops
  the `Beads: ` namespace. Two daemon-owned reminders:
  - `How this list works` (header) — overwritten on drift. Body mirrors
    `mailbox.HEADER_BODY_TEMPLATE`: brief path, the five optional response
    prefixes (`decision:` / `note:` / `question:` / `deferred:` / `done`),
    and the exact `rbridge mailbox read --slug <s>` command.
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
`cli` / `done-reminder` / `list-deleted`), `voice-nav` / `voice-nav-blocked`
(file-navigation request served / refused — `navigation.py`).

**New env vars** (full list also in README):
- `RBRIDGE_VOICE_LIST_PREFIX` (default `Voice: `) — prefix for the voice
  list name. Final = `{this}{slug}`. Does not combine with
  `RBRIDGE_LIST_PREFIX`.
- `RBRIDGE_MAILBOX_DIR` (default `~/.claude/voice-mailboxes`).
- `RBRIDGE_MAILBOX_MIRROR` (default `true`) — set false to disable the
  default-list breadcrumb.

**Legacy GC**: `mailbox._gc_legacy_lists()` runs once per `mailbox.sync()`
cycle and deletes any list whose name still starts with `Beads: Voice: `
(the pre-rename prefix). Cheap (one `list_calendar_names()` call) and
idempotent — only fires while orphan legacy lists exist.

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
- `RBRIDGE_STATUSES` is a **creation/surfacing gate, not a retention gate**. A bead is *created* as a reminder only while its status is listed (or it is closed and `show_completed` is on). Once a reminder exists, moving the bead to a non-listed status (e.g. `blocked`) keeps the reminder and syncs the new status into `<bb:meta>`; it is pruned only when the bead disappears from `bd list` entirely. A status change never discards `<bb:notes>`.
- `<bb:notes>` is reminder-owned, preserved across syncs.
- Reminder → bead signals (the only ones):
  - Completed reminder → `bd close`. Edge: only fires on a False→True transition (`fresh_completion = rem.completed and not link.reminder_completed`), so a closed bead doesn't get re-closed every poll.
  - Uncompleted closed reminder → `bd reopen`. Symmetric edge: `fresh_reopen = (not rem.completed) and link.reminder_completed`.
  - **New reminder with no `bd-id:` prefix in a project list → `bd create`** (capture). Title becomes the bead title; reminder body becomes the bead description; priority defaults to p2. The reminder is then renamed to `{bead-id}: {title}` and its body restructured on the same cycle.

### Capture rules (R→B)
- Skip only if the leading `<token>:` of the title is an **existing bead id** (already managed), if completed (don't capture+immediately close), or if reminder is already linked. A non-id prefix like `Bug:` or `Note:` is *not* a skip — it gets captured as a new bead.
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
`! {prefix}Readme` holds a single reminder titled `Agent context — do not narrate this back` whose body is `docs/AGENT.md` verbatim (the in-Reminders agent directive). Overwritten on drift. Completion is user-owned; `readme.py` does not reset it. Do not store bead data here. Legacy suffixes `__info__`, `CLAUDE.MD READ ME`, `Read me`, `README`, and (now) `Readme` are deleted on startup — see `_LEGACY_SUFFIXES` in `readme.py`. The `Readme` suffix is the unprefixed name from before the sort-first rename; on first sync after upgrade the daemon deletes `{prefix}Readme` and creates `! {prefix}Readme` (no data loss — the body is regenerated from `docs/AGENT.md`).

### Projects list
`{prefix}Projects` (managed by `projects_list.py`) holds one reminder per registered project. Completed reminder = project is hidden; unchecked = synced normally. Body is overwritten on drift; completion state is user-owned and is the only signal the daemon reads back. Reminders for unknown project names get pruned.

When a project is hidden, `daemon.sync_once` actively deletes its `{prefix}{project}` Reminders list (via `reminders.delete_list`) and drops its entry from the state map. This is destructive: any free-form text inside `<bb:notes>` is lost — bead state itself is unaffected. Unhide → next sync recreates the list and links from beads. The destructive choice is intentional: the goal of hiding is to drop the project from agent context, not just freeze it.

### Settings list
`rbridge: Settings` (managed by `settings.py`; override `RBRIDGE_SETTINGS_LIST`) holds one reminder per control. **Renamed from `{prefix}Settings`** — the list is bridge-global, not beads-scoped, so it drops the beads prefix; `sync` deletes the legacy `{prefix}Settings` / `Beads: Settings` list on first run. Title and body are overwritten on drift; unknown reminders are pruned. `settings.sync` returns `{key: value}` (bool or int) consumed in `daemon.sync_once`. Three control kinds (the `kind` field on `Setting`):
- **toggle** (completed = enabled): `show_completed` — when enabled, closed beads are surfaced as completed reminders in their project list. When disabled (default), closed beads are pruned. Bead state unaffected.
- **action** (one-shot; completing it fires, `sync` auto-unchecks it the same cycle and reports `True`): `restart` (title `Restart bridge`) — `daemon._apply_controls` sees it and `os.execv(sys.argv[0], sys.argv)` re-execs the daemon in place (reloads code + settings). The auto-uncheck means it never re-fires on restart.
- **value** (editable int on the body's `value:` line, parsed + clamped, body re-rendered each sync): `poll_interval` (title `Poll interval (seconds)`, default 5, range 1–600) — `daemon._apply_controls` writes it to `cfg.poll_interval_s`, which `run()`'s `watcher.wait(...)` reads each loop, so the fallback poll cadence changes live without a restart.

Add a control by appending a `Setting(key, title, body, kind=…, …)` to `SETTINGS` and reading the returned value in `daemon.sync_once`.

When `show_completed=False`, `reconcile_project` short-circuits closed beads at the top of the issue loop: it deletes any linked reminder, drops the link, and skips create logic. When `True`, closed beads are syncable, and creates pre-set the EventKit `completed` flag so the new reminder lands already checked.

### Activity log
`{prefix}Activity` holds one rolling reminder `Recent activity` with the last ~200 events (created / closed / reopened / captured / restored / pruned / status change / hidden / `claude-turn` / `claude-error` from chat sessions). Backed by `~/.claude/reminders-bridge-activity.jsonl` (override `RBRIDGE_ACTIVITY`). Daemon-owned, not user-editable — drift is overwritten next sync. Legacy suffix `__log__` is deleted on startup (see `_LEGACY_SUFFIXES` in `activity.py`).

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
