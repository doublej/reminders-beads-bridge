<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';
  import Wordmark from '$lib/components/Wordmark.svelte';

  const scenario1 = `
sequenceDiagram
  autonumber
  actor U as user (iPhone, on the train)
  participant IOS as Reminders (iOS)
  participant ICLOUD as iCloud
  participant REM as Reminders (Mac)
  participant D as rbridge daemon
  participant BD as bd CLI

  U->>IOS: open "Beads: wallgen"
  U->>IOS: add reminder<br/>"filters reset on tab switch"
  IOS->>ICLOUD: sync (background)
  Note over D: 5s tick (interval — iCloud doesn't fire EKEventStoreChanged)
  ICLOUD->>REM: deliver new reminder
  D->>REM: list reminders
  D->>D: detect title without bd-id prefix
  D->>BD: bd create
  BD-->>D: bd-87
  D->>REM: rename to "bd-87: filters reset…"<br/>+ structure body with bb:meta/desc/notes
  REM->>ICLOUD: sync rename
  ICLOUD->>IOS: deliver renamed reminder
  U->>IOS: glance later → sees "bd-87: …" with priority + status
`;

  const scenario2 = `
sequenceDiagram
  autonumber
  actor U as user
  participant CC as Claude Code<br/>(project agent)
  participant SK as /voice-chat-takeout
  participant RB as rbridge
  participant REM as Reminders.app
  participant CV as Claude Voice<br/>(voice agent)

  U->>CC: "let's walk through the migration call"
  CC->>SK: invoke skill
  SK->>SK: pre-flight: Read files, grep symbols,<br/>git log, capture error strings
  SK->>SK: compose brief (POV: voice agent = you)
  SK->>RB: rbridge mailbox open --slug wallgen-migration --kind REMINDERS
  RB->>REM: create Voice: wallgen-migration<br/>+ header + brief
  RB->>REM: drop "Voice exchange open: wallgen-migration"<br/>into default list
  RB-->>CC: list name + read command

  Note over U,CV: user goes for a walk
  U->>CV: opens Claude Voice
  CV->>REM: read brief reminder
  CV->>U: "Here's where we landed on the wallgen migration…"
  U->>CV: "we should defer the bosdieren rename"
  CV->>REM: add reminder "deferred: bosdieren slug rename"
  U->>CV: "ship the rest as is"
  CV->>REM: add reminder "decision: ship migration phase one"
  U->>CV: that's it for now
  CV->>REM: add reminder "done"

  Note over U,CC: user returns to keyboard
  RB->>REM: detect 'done' next cycle<br/>→ close exchange (delete list + mirror + state)
  U->>CC: "what did I commit to?"
  CC->>RB: rbridge mailbox read --slug wallgen-migration
  Note over CC,RB: read fails — list already torn down<br/>(user would run earlier next time)
  CC->>U: pulls activity log fallback
`;

  const scenario3 = `
sequenceDiagram
  autonumber
  actor U as user (anywhere, iPhone)
  participant IOS as Reminders (iOS)
  participant REM as Reminders (Mac)
  participant D as rbridge.sessions.poll
  participant CL as claude -p (subprocess)

  U->>IOS: add reminder in "Claude: Sessions"<br/>title: "Summarize my open bugs"
  Note right of U: body:<br/>cwd: ~/Documents/development/python/wallgen<br/>chat: true<br/><br/>you:<br/>list open beads, group by file
  IOS->>REM: sync
  D->>REM: scan for pending 'you:' blocks
  D->>D: detect chat-mode reminder<br/>no session id yet
  D->>CL: claude -p --output-format json (with prompt)
  CL-->>D: events array<br/>(result: "bd-12, bd-18, bd-22…")
  D->>REM: append claude (ts): block<br/>+ session: &lt;uuid&gt; header
  Note over REM: reminder still unchecked

  REM->>IOS: sync back
  U->>IOS: read reply, append:<br/>you:<br/>group by author too
  IOS->>REM: sync
  D->>REM: detect new 'you:' after last 'claude (…):' block
  D->>CL: claude -p --resume &lt;uuid&gt;
  CL-->>D: next reply
  D->>REM: append claude (ts): block
  U->>IOS: read · check reminder → close
`;
</script>

<h1>Scenarios</h1>
<p class="lead">
  Three end-to-end walkthroughs — one per lane. Each shows the boundary
  between user-on-device, daemon, and external agent so you can spot
  where your own use case fits.
</p>

<h2>1 · Capture a bug from the iPhone</h2>

<p>The user is on the train. They notice a bug in the wallgen UI. Instead
of opening a laptop, they open Reminders, type a title, hit save. Five
seconds after the Mac comes online, the bead exists.</p>

<Mermaid code={scenario1} caption="iOS capture flow. EKEventStoreChanged does not fire for iCloud changes, so the latency is bounded by the 5s interval, not the iCloud sync itself." />

<h3>What's interesting</h3>
<ul>
  <li>The user never touched a terminal, never named the bead, never set
  a priority. The daemon defaults to <code>p2</code> on capture.</li>
  <li>The reminder gets renamed in place — iCloud carries the rename
  back to the phone so the user sees the assigned ID next time they look.</li>
  <li>If the train trip is offline-only, the reminder still gets added
  locally; iCloud holds it until reconnect. Capture is essentially
  asynchronous.</li>
</ul>

<h2>2 · Voice walk with the voice agent</h2>

<p>The user is mid-conversation with <Wordmark kind="claude-code" /> about
a migration. They want to keep thinking but stop staring at a screen.
They invoke <code>/voice-chat-takeout</code>; the project agent composes
a brief with everything that's on the table; the voice agent reads it on
the phone and pushes back.</p>

<Mermaid code={scenario2} caption="One voice exchange end-to-end. The 'done' reminder is the canonical close signal — it tears the list down on the next daemon cycle." />

<h3>What's interesting</h3>
<ul>
  <li>The skill's pre-flight (step 1) is what makes the difference between
  a substantive brief and an agenda summary. Anything proper-noun-grade
  gets backed by a tool call before it lands in the brief.</li>
  <li>The voice agent has no idea about the wider project context — only
  what's in the brief. POV in the brief therefore has to address it
  directly ("you", as in the voice agent), with the user as third party.</li>
  <li>The user closing with "done" is the cleanest path. Adding
  <code>done</code> as a reminder is the same as running
  <code>rbridge mailbox close</code> — both fire on the next 5s cycle.</li>
</ul>

<h2>3 · Multi-turn chat from Reminders.app</h2>

<p>The user wants a quick summary of open bugs. No need to open a
terminal — they file a chat-mode reminder, the daemon runs
<code>claude -p</code> in the background, the reply lands in the body. A
follow-up question is just another <code>you:</code> block in the same
reminder.</p>

<Mermaid code={scenario3} caption="Multi-turn chat. Session id persists in the reminder body, so close + reopen + new 'you:' block resumes the same conversation." />

<h3>What's interesting</h3>
<ul>
  <li>The reminder stays unchecked across turns. Checking it just makes
  the daemon skip it; the session JSONL persists under
  <code>~/.claude/projects/</code> and a new <code>you:</code> block on a
  rechecked reminder resumes the same session.</li>
  <li>Output formatting is whatever Claude returns in the
  <code>result</code> event. For predictable structure, prompt for it
  explicitly ("reply in a markdown table").</li>
  <li>This is the lane that crosses lines least — it has no beads
  coupling and no voice coupling. It's just "remote Claude with the
  reminder as terminal."</li>
</ul>

<h2>Pattern recap</h2>

<p>Across all three scenarios, the same shape repeats:</p>

<ol>
  <li>User puts intent into Reminders (a title, a brief, a prompt).</li>
  <li>Daemon notices on the next cycle (event or interval).</li>
  <li>Daemon takes the action with the right backend (bd / claude / mailbox CLI).</li>
  <li>Result lands back in Reminders — either as a renamed/restructured
  reminder, an appended body, or a brand-new list.</li>
</ol>

<p>The user never needs to open the daemon's logs or run
<code>rbridge</code> commands directly. Everything is round-trippable
through the same surface.</p>
