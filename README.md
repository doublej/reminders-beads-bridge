# reminders-bridge

A macOS daemon that turns Apple Reminders into a control surface for
[Beads](https://github.com/doublej/beads-kanban) issue tracking,
Claude Code / Codex sessions, and voice exchanges with Claude Voice.

**Docs site (diagrams + scenarios + install guide):**
<https://doublej.github.io/reminders-beads-bridge/>

**Deep reference:** [`docs/REFERENCE.md`](docs/REFERENCE.md)

## What it does

- **Beads ↔ Reminders** — one Reminders list per beads project, one
  reminder per issue. Edit notes on your phone, check it to close, add a
  reminder to file a bug.
- **Claude / Codex sessions** — two reminders lists drive sessions in
  three modes (interactive, capture, multi-turn chat). All from
  Reminders.app.
- **Voice exchanges** — the project agent composes a brief; the user
  walks with the voice agent; structured responses come back as
  reminders the project agent drains via `rbridge mailbox read`.
- **Claude tabs** — `_rb_claude_tabs` mirrors every live Ghostty tab running
  Claude Code as one reminder: read a live transcript tail, or type under
  `send:` and check the box to have the bridge switch to that tab and type
  your message into the live session — exactly as you would.

The lanes are independent. You can use any without the others.

## Quick start

```bash
git clone git@github.com:doublej/reminders-beads-bridge.git
cd reminders-beads-bridge
uv sync
uv run rbridge doctor   # verify deps + Reminders permission
uv run rbridge sync     # one-shot reconcile
```

Daemon (runs every 5s under launchd):

```bash
cp launchd/com.jurrejan.reminders-bridge.plist ~/Library/LaunchAgents/com.<you>.reminders-bridge.plist
# edit paths + Label inside the copied plist
launchctl load ~/Library/LaunchAgents/com.<you>.reminders-bridge.plist
tail -f ~/Library/Logs/reminders-bridge.log
```

Full step-by-step (clean macOS, permissions walkthrough, troubleshooting):
<https://doublej.github.io/reminders-beads-bridge/install/>.

## Requirements

- macOS with Reminders.app automation granted (System Settings → Privacy
  & Security → Automation).
- `uv` (Python package manager).
- `bd` v0.49+ on `$PATH` — only required for the Beads sync lane.
- A populated `~/.beads-kanban-projects.json` (beads-kanban writes it
  when you open a project) — only required for the Beads sync lane.

## Repo layout

```
src/reminders_bridge/    Python package — daemon, lanes, EventKit adapter
docs/AGENT.md            Directive served into the Reminders agent context
docs/REFERENCE.md        Full reference (lists, env vars, modes, body XML)
docs/architecture.mmd    Mermaid module map (source of truth)
launchd/                 launchd plist template
site/                    SvelteKit docs site (deployed to GitHub Pages)
```

## License

MIT.
