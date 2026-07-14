# testkit — drive the bridge through a replica of the voice agent's tools

This lets you exercise reminders-bridge the way the phone does, without the
phone. It spawns a headless Claude Code agent that has **only** the Apple
Reminders tool surface the Claude voice agent has — nothing else — and points it
at the **real** Reminders database. So a prompt like "add milk to my list" or
"close that ticket" flows agent → replica MCP server → EventKit → real
Reminders, and the daemon reacts exactly as it would to a real voice write. You
get an automatable, promptable stand-in for the voice agent.

## Why it is faithful

- **Verbatim tool descriptions.** The five `reminder_*_v0` tool descriptions are
  copied byte-for-byte from the live Claude tools (captured via a live probe),
  because the description text is what drives the model's behaviour — e.g. the
  create tool's "always create a reminder per item for a list of items" nudge.
  See `tools.py`.
- **Exact wire shapes.** Batched, camelCase inputs (grouped creates,
  update/delete arrays); snake_case responses with optional fields omitted when
  unset; `completionDate` (not a boolean); `listId` targeting. Matches the
  probed live shapes.
- **Real EventKit backing.** `ekstore.py` reuses the daemon's authed
  `EKEventStore`, so writes hit the same store the daemon and the phone share.
- **`user_time_v0` stub.** The create/update descriptions tell the model to call
  `user_time_v0` for the timezone before setting relative dates; denying it would
  cause a call to a missing tool, so it is stubbed, not removed.

## The agent has ONLY these tools

Enforced by four independent layers (belt and suspenders):

1. `--strict-mcp-config` + our `--mcp-config` — no MCP server but the replica.
2. `--disallowedTools` — the built-ins (Bash, Read, Write, web, …) are removed.
3. `ENABLE_TOOL_SEARCH=false` — the six tools load directly; no `ToolSearch`
   discovery step (which would itself be a tool).
4. A `PreToolUse` hook (`deny_hook.py`) that hard-denies anything outside
   `mcp__reminders__*`. Set `RBRIDGE_HOOK_LOG=/path` to log every allow/deny.

Context is kept clean too: the cwd is outside any repo (no project `CLAUDE.md`)
and `--setting-sources project,local` drops the global user `CLAUDE.md`. The
real login is left untouched so OAuth refresh works.

## The agent's text output is SPOKEN

In real use the agent's words are read aloud, and forming them is slow. So
`run.py` surfaces the final assistant text as `utterance` (first-class,
separate from tool calls), and evals should judge it as speech: short, no filler
preamble, worth hearing. `speakable_receipt` in `evals.py` is the template.

## Usage

```bash
# one prompt, human-readable
uv run --extra testkit python testkit/run.py "how many open bugs in reminders-bridge?"

# structured result for assertions (utterance, tool_calls, tool_results, …)
uv run --extra testkit python testkit/run.py --json "add milk to my groceries" | jq .

# from Python
#   from run import run; r = run("close bd-18"); r["tool_calls"], r["utterance"]

# the eval suite (spawns one agent per case; leaves Reminders as it found it)
uv run --extra testkit python testkit/evals.py            # all
uv run --extra testkit python testkit/evals.py isolation  # one
```

`run(prompt, model=?, timeout=?)` returns: `utterance` (spoken text),
`utterances` (every turn), `tool_calls` `[{name, input}]`, `tool_results`
(raw strings), `num_turns`, `is_error`, `stderr`, `raw_events`.

Runtime state (the agent cwd + generated `.mcp.json` / `settings.json`) lives in
`~/.rbridge-testkit/` (override with `RBRIDGE_TESTKIT_HOME`); nothing is written
into the repo.

## Files

| File | Role |
|---|---|
| `tools.py` | The six tool specs — verbatim descriptions + exact input schemas. |
| `ekconv.py` | Field conversions: priority enum↔EK int, dates, alarms, recurrence, reminder↔dict. |
| `ekstore.py` | EventKit-backed list/search/create/update/delete on the real store. |
| `mcp_server.py` | Thin stdio MCP server wiring specs → dispatch. |
| `deny_hook.py` | PreToolUse hook: allow `mcp__reminders__*`, deny the rest. |
| `run.py` | Provision the isolated agent + spawn `claude -p` + parse the stream. |
| `evals.py` | Starter evals (isolation, one-per-item, speakable receipt). |

## Daemon-coupling evals (mutating — run deliberately)

The evals above test the tool surface. To test the bridge's R→B reactions
(capture, close, reopen), drive the agent against a **dedicated throwaway beads
project** — never a live one, since these create/close real beads:

1. `mkdir -p /tmp/rb-test && cd /tmp/rb-test && bd init` (gives it a `.beads/`).
2. Register it so the daemon builds its `_rb_beads_rb-test` list (add the dir to
   the project registry / let `projects.py` discover it), wait one poll.
3. Capture: `run("add a reminder 'Bug: filters reset on tab switch' to my
   rb-test list")` → after ~5s the daemon should `bd create` a bead; assert via
   `bd list --json`.
4. Close: have the agent complete a `<bead-id>:`-prefixed reminder → daemon
   `bd close`.
5. Tear down the project and its list.

## Known divergences from the live surface

- Tools appear to the model as `mcp__reminders__reminder_create_v0` (Claude Code
  namespaces MCP tools); the live phone sees `reminder_create_v0`. The salient
  name and all descriptions match; behaviour is unaffected.
- `alarms` and `recurrence` inputs are accepted and applied best-effort (simple
  absolute/relative alarm, frequency+interval+end recurrence); exotic rrule
  fields are ignored rather than erroring. The bridge itself uses none of these.
- This mirrors the **chat** Claude surface's reminder tools. If your voice flow
  runs a different surface, confirm its tool set matches.
