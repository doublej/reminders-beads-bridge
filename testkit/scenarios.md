# Voice scenarios — JJ on his phone, away from the computer

Realistic things JJ says to the voice agent (Claude inside Apple Reminders on
the phone) when he can't open the laptop. Each is a test seed for the replica:
feed **JJ says** to `run.py` and judge the agent's tool calls + spoken utterance.

Utterances follow the `docs/AGENT.md` contract: no preamble, one sentence,
the action *is* the receipt. Remember the words are **spoken aloud**, so short
and free of identifiers beats complete.

Tags: `[read]` safe to auto-eval · `[write]` mutates Reminders (use a throwaway
target + teardown) · `[bridge]` also mutates beads/daemon state (run against a
throwaway `bd init` project only) · `[risky]` real side effect (session/restart)
— don't auto-run against live data.

---

## Capture before he forgets

### 1. Log a bug he just thought of `[write] [bridge]`
He's walking the dog and remembers a regression.
- **JJ says:** "Add a ticket to pcvr-quest-streamer — controllers drift after the headset sleeps."
- **Agent does:** creates a reminder in `_rb_beads_pcvr-quest-streamer` with no `<bead-id>:` prefix (daemon mints the bead within ~5s).
- **Good utterance:** "added — daemon assigns the id shortly."

### 2. Dump three quick todos `[write]`
Standing in line, rattles off a personal list.
- **JJ says:** "Remind me to renew the domain, pay the NAS invoice, and email the accountant."
- **Agent does:** one `reminder_create_v0` with **three separate reminders** (one-per-item), default list.
- **Good utterance:** "added all three."
- **Watch for:** packing them into one bulleted note = fail.

---

## Triage & status (hands-free glance)

### 3. What's on my plate? `[read]`
Between meetings, wants the shape of the day.
- **JJ says:** "What's open across my projects?"
- **Agent does:** `reminder_search_v0` over `_rb_beads_*` lists, incomplete only.
- **Good utterance:** "3 open in pcvr: controller drift, sleep wake crash, csv export."

### 4. Is anything blocked? `[read]`
- **JJ says:** "Anything stuck or blocked right now?"
- **Agent does:** search, filter on `<bb:meta>` status = blocked.
- **Good utterance:** "one — bd-22, blocked on the codec bump."

### 5. Morning rundown `[read]`
Coffee, no laptop.
- **JJ says:** "Give me a rundown of everything."
- **Agent does:** reads across `_rb_beads_*`; optionally the dashboard URL in `_rb_dashboard` if it can fetch.
- **Good utterance:** two lines max, per project counts.

---

## Nudge work along

### 6. Close a finished ticket `[write] [bridge]`
Fixed it on his phone via a session and wants it closed.
- **JJ says:** "Close the controller drift one."
- **Agent does:** resolves the title, sets `completionDate` on that reminder → daemon `bd close`.
- **Good utterance:** "closed bd-31."
- **Watch for:** closing the wrong one when titles are similar — it should confirm if ambiguous.

### 7. Add context to a ticket `[write]`
Remembers a detail about a bug.
- **JJ says:** "On the csv export bug, note that it only breaks with commas in the title."
- **Agent does:** read-modify-write **only** inside `<bb:notes>`, preserving `<bb:meta>`/`<bb:desc>`.
- **Good utterance:** "noted."
- **Watch for:** clobbering `<bb:meta>` → tamper cycle = fail.

### 8. Reprioritize `[write]`
- **JJ says:** "Bump the sleep-wake crash to high priority."
- **Agent does:** `reminder_update_v0` priority → high.
- **Good utterance:** "bumped to high."

### 9. Hand a ticket to a coding agent `[write] [bridge]`
Wants Claude to start while he's out.
- **JJ says:** "Have Claude start on the csv export ticket."
- **Agent does:** adds `!agent` on its own line inside that ticket's `<bb:notes>` (daemon rewrites to `<bb:agent queued=…/>`).
- **Good utterance:** "queued a coding session on bd-31."

---

## Live sessions & tabs

### 10. What's Claude doing right now? `[read]`
A session is running in a Ghostty tab at home.
- **JJ says:** "What's Claude working on?"
- **Agent does:** reads `_rb_claude_tabs` body (transcript tail, read-only).
- **Good utterance:** "mid-refactor on reminders-bridge — running the eval suite."

### 11. Steer the running session `[risky]`
Wants to add an instruction to the live tab.
- **JJ says:** "Tell that Claude tab to also run mypy before it finishes."
- **Agent does:** read-modify-write the tab body, add the line under `send:`, and set `completed: true` in the **same** `reminder_update_v0` (completion is the send trigger).
- **Good utterance:** "sent."
- **Watch for:** staging text without completing, or completing then writing = unsent draft = fail.

### 12. Fire off a quick headless task `[risky]`
- **JJ says:** "Ask Claude to summarize what changed in reminders-bridge today."
- **Agent does:** creates a reminder in `_rb_claude_sessions` with a `capture: true` body header.
- **Good utterance:** "queued — I'll have the summary in the list."

---

## Voice exchanges (an open review on the phone)

### 13. Record a decision `[write]`
The pimpelmees glossary review is open; he settles a naming question.
- **JJ says:** "For the glossary review, decision: we call it 'wallpaper' everywhere, not 'wall decoration'."
- **Agent does:** adds a reminder to `_rb_voice_pimpelmees-glossary-review` prefixed `decision:`.
- **Good utterance:** "logged the decision."

### 14. Pull a file into the exchange `[write]`
Wants to check the current glossary during the review.
- **JJ says:** "Show me the glossary file for that review."
- **Agent does:** adds a `fetch: <exact path>` reminder using the path **from the brief's file map** — never a path it heard spoken (transcription mangles paths); falls back to `grep: <token>` for a fuzzy reference.
- **Good utterance:** "pulling it in now."

### 15. Park something `[write]`
- **JJ says:** "For the escalation message, deferred: we'll word it after the call with Alex."
- **Agent does:** adds a `deferred:` reminder to `_rb_voice_wabi-alex-escalation-message`.
- **Good utterance:** "parked it."

### 16. Wrap the exchange `[write]`
- **JJ says:** "I'm done with the glossary review."
- **Agent does:** adds a `done` reminder → daemon closes the exchange next cycle.
- **Good utterance:** "closing it out."

---

## Controls & housekeeping

### 17. Turn on the dashboard, get the link `[write]`
Wants the at-a-glance view on his phone browser.
- **JJ says:** "Turn on the dashboard and give me the link."
- **Agent does:** checks `Dashboard server` toggle in `_rb_settings`; then reads the fresh URL from `_rb_dashboard` (reopen for a new token).
- **Good utterance:** "on — link's in the dashboard reminder."

### 18. Restart a stuck bridge `[risky]`
- **JJ says:** "The bridge seems frozen, restart it."
- **Agent does:** completes the `Restart bridge` action reminder in `_rb_settings` (`os.execv`; it un-completes itself).
- **Good utterance:** "restarting."

### 19. Mute a project `[write]` (destructive — confirm first)
Too much noise from one project today.
- **JJ says:** "Hide the pimpelmees project from my context."
- **Agent does:** **confirms first** (hiding deletes that project's `<bb:notes>`), then checks its row in `_rb_beads_projects`.
- **Good utterance:** "that wipes the project's notes — hide it? (bead state is safe)"

---

## How to run these

```bash
# a single scenario, voice-parity mode (reads the live !_rb_readme first)
uv run --extra testkit python testkit/run.py --directive "What's open across my projects?"

# the executable subset as pass/fail checks (Sonnet, parity mode by default)
uv run --extra testkit python testkit/evals.py            # all
uv run --extra testkit python testkit/evals.py close      # one
```

`evals.py` already encodes the runnable `[read]`/`[write]` scenarios below and
verifies each by reading the store back. `[bridge]` needs a throwaway `bd init`
project + teardown; `[risky]` ones (sessions/restart/live tabs) should be
dry-run or pointed at a scratch target, never live. Agent model is Sonnet
(`RBRIDGE_AGENT_MODEL`); parity mode is on unless `RBRIDGE_DIRECTIVE=0`.
