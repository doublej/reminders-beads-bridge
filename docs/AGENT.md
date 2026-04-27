# Using Beads through Apple Reminders

You're reading this inside Apple Reminders. You can drive a project's Beads issue tracker entirely from this app — no shell, no repo access required. A daemon polls every few seconds and reconciles changes both ways.

## What you're looking at

- A projects list `Beads: Projects` listing every registered project as a reminder. Check a reminder to **hide** that project — its `Beads: <project>` list is deleted within seconds. Uncheck to bring it back; the next sync recreates the list and reminders from beads. Hiding is destructive for any free-form `<bb:notes>` you wrote (bead state itself is safe).
- A settings list `Beads: Settings` with one reminder per global toggle. Check = enabled, uncheck = disabled. Current toggles:
  - **Show completed tasks** — when on, closed beads appear as completed reminders inside each project list. When off (default), closed beads are pruned from project lists to keep your context focused on open work.
- One Reminders list per project, named `Beads: <project>`. Each reminder = one Beads ticket.
- Reminder title is exactly `<bead-id>: <ticket title>`. The prefix is the bead id; do not change it.
- Reminder body has three XML-tagged sections:
  - `<bb:meta>[type · pN · status]</bb:meta>` — type / priority / status. Read-only (rewritten next sync).
  - `<bb:desc>…</bb:desc>` — the bead description. Read-only.
  - `<bb:notes>…</bb:notes>` — yours. Free text. Preserved across syncs.
- An optional `<bb:restored at="…">…</bb:restored>` banner appears once if you accidentally overwrote meta or desc; it disappears on the next clean sync.

## What you can do

### Create a ticket — write a new reminder
- Add a reminder in a `Beads: <project>` list. Title = the ticket title you want. Body, if any, becomes the description.
- Within seconds the title gets a `<bead-id>:` prefix and the body becomes the structured form above.
- Default priority is p2 (medium). To set a different priority, mark it in Reminders (high → p0, none/low → p3); the next sync clamps to one of p0/p1/p2/p3.
- Do **not** include a `<bead-id>:` prefix yourself — let the daemon assign it.

### Close a ticket — mark the reminder complete
- Tap the circle. Within seconds the matching bead is closed in Beads.

### Reopen a ticket — uncheck the reminder
- Unchecking a completed reminder reopens the matching bead (status returns to `open`) within seconds.

### Launch a coding agent on a ticket — write `!agent` in `<bb:notes>`
- Add a line `!agent` (on its own) inside the `<bb:notes>` section of a reminder.
- Optional args, space-separated: `model=<name>` (e.g. `model=claude-opus-4-7`), `useWorktree=true`.
  - Example: `!agent model=claude-opus-4-7 useWorktree=true`
- On the next poll the daemon enqueues the agent against the bead via the kanban API, then rewrites the marker line into either:
  - `<bb:agent queued="<bead-id>" at="<iso>"/>` on success, or
  - `<bb:agent error="<code>" at="<iso>"/>` on failure (e.g., kanban server unreachable).
- The marker tag is non-actionable; remove it (or write a fresh `!agent` line) to launch again.

### Open a local Claude Code or Codex session — write a reminder in `Claude: Sessions` or `Codex: Sessions`
These two lists are *not* part of the beads system. They live alongside the `Beads: …` lists and are scanned independently every sync cycle.

- Add an unchecked reminder to `Claude: Sessions` (or `Codex: Sessions`).
- **Title** = the prompt the new Claude / Codex session should start with.
- **Body** (optional):
  - First line `cwd: <path>` sets the working directory (`~` allowed). Default is `$HOME`.
  - Anything else in the body is appended to the prompt.
- Within a few seconds the daemon opens a new Ghostty window in that directory, runs `claude` (or `codex`) with the composed prompt as argv, and marks the reminder completed (it stays in the list as an audit trail).
- A failed launch leaves the reminder unchecked and gets retried next cycle.

### Add notes — edit inside `<bb:notes>` only
- Whatever you type between `<bb:notes>` and `</bb:notes>` is yours and survives every sync.
- Editing `<bb:meta>` or `<bb:desc>` is pointless — they get rewritten on the next poll, with a one-time "restored" banner so you know it happened.

### Search
- `Beads: <project>` lists hold open + in-progress tickets. Closed tickets stay until you complete them in Reminders or are removed at the bead level.

## Priority mapping

| Bead | Reminders | Display |
|------|-----------|---------|
| p0 | 1 | High (!) |
| p1 | 1 | High |
| p2 | 5 | Medium |
| p3 | 9 | Low / none |

## Lists you must not write into

- `Beads: Readme` — this list. Daemon overwrites any edits.
- `Beads: Activity` — rolling activity log of bridge events. Read-only from your side.
- `Beads: Projects` — daemon-owned. The only signal you control here is the checkbox per project (check to hide, uncheck to show). Title and body get rewritten on drift. Adding new reminders has no effect: unknown project names are pruned.
- `Beads: Settings` — daemon-owned. Only the checkbox matters: check to enable a setting, uncheck to disable. Title and body are rewritten on drift; new reminders you add are pruned (unknown setting names).

## What is not supported (yet)

- Editing the title (other than for capture) — your edit is overwritten next sync.
- Editing `<bb:desc>` — same.
- Adding comments to a bead — write them inside `<bb:notes>` for now; they live on the reminder, not the bead.
- Live agent progress in the reminder — the marker turns into a `queued` tag once enqueued; check the kanban UI for live status.

## Quick recipe

> "Add a Beads ticket: in `Beads: project-foo`, create a reminder titled `Investigate flaky parser test`, body = `repro: run pytest -k flaky three times`. Mark it high priority."

That single action lands a new bead in the project within seconds, prefixed and structured by the daemon.
