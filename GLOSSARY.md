# Glossary — reminders-bridge ubiquitous language

Canonical names for this project's concepts. Use these exact terms in code,
comments, docs, commits, and agent-facing text. One concept, one word — the
"avoid" column lists synonyms that cause drift.

## Core (beads ↔ reminders)

| Term | Meaning | Avoid |
|---|---|---|
| **bead** | An issue in Beads (`bd`). The **source of truth**. | issue, ticket, task (informal only) |
| **reminder** | The Apple Reminders item that *mirrors* a bead. A view, not the record. | — (never use as a synonym for bead) |
| **link** | State-file mapping bead id ↔ EventKit reminder id. | binding, mapping |
| **reconcile** | One project's diff-and-commit pass (`reconcile_project`). | refresh |
| **sync cycle** | One `daemon.sync_once()` poll iteration. | tick, poll (the cycle ≠ the interval) |
| **registry** | `~/.beads-kanban-projects.json` — the list of projects. | config |
| **project** | A registered directory containing `.beads/`. | repo (a repo may have many) |
| **capture** | R→B: a new unprefixed reminder becomes a `bd create`. | import |
| **adoption** | Matching a pre-existing reminder to a bead by title prefix. | — |
| **tamper** | Drift in `<bb:meta>`/`<bb:desc>` away from bead state. | edit, corruption |
| **prune** | Delete a reminder whose bead vanished from `bd list`. | gc (reserve "GC" for lane cleanup) |
| **lane** | An independent subsystem run as a peer in `sync_once` (beads, triggers, captures, sessions, tabs, voice, settings). | module, feature, subsystem |

## Reminder-body tags (`<bb:*>`, managed by `body.py`)

| Tag | Meaning | Writable by user? |
|---|---|---|
| `<bb:meta>` | `[type · p0–3 · status]` mirrored from the bead. | no (tamper if changed) |
| `<bb:desc>` | Bead description, mirrored. | no (tamper if changed) |
| `<bb:notes>` | Free-form user scratch space, preserved across syncs. | **yes** (only this) |
| `<bb:restored>` | Tamper-recovery banner; drops on next clean sync. | no |
| `<bb:mirror>` | Marker on the default-list voice breadcrumb. | no |
| `<bb:agent>` | Agent-dispatch status, rewritten from an `!agent` marker. | no |

## Lists (the `_rb_` namespace)

| List | Owner | What |
|---|---|---|
| `_rb_beads_<project>` | daemon + user | tickets, one reminder per bead |
| `_rb_beads_projects` | daemon writes, user toggles | one row per project; checked = hidden |
| `!_rb_readme` | daemon, read-only | the voice/in-Reminders agent directive (`docs/AGENT.md`); `!` sorts first |
| `_rb_activity` | daemon, read-only | rolling log of ~200 events |
| `_rb_settings` | daemon writes, user toggles/edits | bridge controls |
| `_rb_claude_tabs` | daemon | live Ghostty Claude-tab mirror |
| `_rb_claude_sessions` / `_rb_codex_sessions` | user creates | session triggers |
| `_rb_voice_<slug>` | daemon + user | one voice **exchange** |

`_rb_voice_` and the bridge-global lists deliberately **drop** the `_rb_beads_`
prefix — they have no beads coupling.

## Settings controls (`<rb:*>`, managed by `settings.py`)

| Tag | Kind | Behavior |
|---|---|---|
| `<rb:toggle/>` | toggle | completed = enabled (e.g. `show_completed`) |
| `<rb:action/>` | action | one-shot; completing fires, auto-unchecks (e.g. `Restart bridge`) |
| `<rb:value min max>N</rb:value>` | value | clamped int (e.g. `poll_ms`) |

## Session / trigger modes (`sessions.py` / `triggers.py` / `captures.py`)

**interactive** (default; opens Ghostty) · **capture** (`capture: true`, headless
one-shot) · **chat** (`chat: true`, multi-turn) · **fixer** (`fixer: true`,
chat with bridge diagnostics preloaded).

## Voice exchange

The three **roles** (never blur them — see *Surfaces* below for who reads what):

| Role | Who | Self-refers / addressed as | Avoid |
|---|---|---|---|
| **user** | the human | third person ("the user", "they") in the brief | — |
| **project agent** | the Claude Code session composing the brief | "I" in the brief | "the agent", coding agent (loose) |
| **voice agent** | the agent the user talks to that reads the brief (and, acting inside Reminders, reads `!_rb_readme`) | "you" in the brief | voice partner, ChatGPT voice, "Claude Voice" *as a role label* |

"Claude Voice" names the current concrete implementation, not the role.

Surface terms:

| Term | Meaning |
|---|---|
| **voice exchange** / **mailbox** | one open conversation, identified by a **slug** |
| **slug** | `[a-z0-9][a-z0-9-]{0,47}` kebab id; topic-first |
| **exchange list** | the `_rb_voice_<slug>` Reminders list (not "voice list") |
| **brief** | the handoff doc the project agent composes for the voice agent |
| **header / brief / mirror reminder** | daemon-owned reminders in/around the exchange |
| **response** / **response kind** | a user reminder in the exchange: `decision` / `note` / `question` / `deferred` / `done` / `free` |
| **deferred** | an explicit punt — talked about, no decision yet, revisit later |
| **writeback contract** | the brief section naming the list + response prefixes |
| **drain** | the project agent reading responses via `rbridge mailbox read` |
| **takeout** | the voice-takeout flow (now driven by `rbridge prime`, no skill) |
| **kind** | the *return channel*: `CLAUDE_VOICE` (one-way TTS) or `REMINDERS` (writeback) |
| **shape** | the *content structure*: decision walk or reference review |
| **file navigation** / **nav** | pulling repo content via `fetch:` / `grep:` / `tree:` reminders |
| **source_cwd** | the mailbox's repo root; nav serves files under it (empty ⇒ nav off) |
| **map** | the speakable-handle ↔ exact-path index the project agent puts in the brief |

Nav verbs rewrite in place: `fetch:`→`file:`, `grep:`→`results:`, `tree:`→`listing:`, refused→`blocked:`.

## Surfaces — who reads what (the routing that drifts)

An instruction only works if it lands where its reader looks.

| Surface | Reader | Carries |
|---|---|---|
| `rbridge prime` → `src/reminders_bridge/primer.md` | **project agent** | how to *author* a brief + open a mailbox |
| the **brief** (in `_rb_voice_<slug>`) | **voice agent** | per-exchange content + the **map** |
| `!_rb_readme` → `docs/AGENT.md` | **voice agent** (acting inside Reminders) | standing directive incl. nav mechanics |
| `CLAUDE.md` + `.claude/rules/` | **project agent / editor** | how to change this codebase |

The **voice agent never reads the primer.** Runtime rules for it go in
`docs/AGENT.md` or the brief; authoring rules go in the primer. Putting a
voice-agent instruction in the primer silently does nothing.
