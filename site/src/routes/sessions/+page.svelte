<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';
  import Wordmark from '$lib/components/Wordmark.svelte';

  const modes = `
flowchart TB
  classDef user fill:#ffb98a,stroke:#c98c5b,color:#1a1d21
  classDef daemon fill:#6cd18b,stroke:#15803d,color:#1a1d21
  classDef agent fill:#7aa8ff,stroke:#2563eb,color:#1a1d21
  classDef artifact fill:#f5a623,stroke:#b45309,color:#1a1d21

  USER(["👤 user"]):::user
  L["Claude: Sessions<br/>(or Codex: Sessions)"]:::daemon
  USER -- "add unchecked<br/>reminder" --> L
  L --> D{daemon parses<br/>body headers}

  D -- "no headers" --> INT["Interactive mode"]:::agent
  D -- "capture: true" --> CAP["Capture mode"]:::agent
  D -- "chat: true" --> CHAT["Chat mode"]:::agent
  D -- "chat + fixer: true" --> FIX["Fixer mode"]:::agent

  INT --> GH["spawn Ghostty<br/>run claude/codex"]:::artifact
  GH -- "mark reminder<br/>completed" --> L
  CAP --> SUB["claude -p / codex exec<br/>(subprocess, stdout → tmpfile)"]:::artifact
  SUB -- "append output to body<br/>mark completed" --> L
  CHAT --> JSON["claude -p --output-format json<br/>--resume &lt;session&gt;"]:::artifact
  JSON -- "append claude (ts): block<br/>stay unchecked" --> L
  FIX --> PRELOAD["preload: daemon log +<br/>state + arch rules"]:::artifact
  PRELOAD --> JSON
`;

  const chatTurn = `
sequenceDiagram
  autonumber
  actor U as user
  participant L as Claude: Sessions
  participant D as sessions.poll
  participant CL as claude -p
  participant FS as ~/.claude/projects/

  U->>L: append 'you:' block
  Note over L: reminder stays unchecked
  D->>L: scan for pending turns
  D->>D: detect new 'you:' after last 'claude (…):'
  D->>CL: spawn with --resume &lt;session&gt;
  CL->>FS: append to session JSONL
  CL-->>D: stdout (json events array)
  D->>D: find 'result' event
  D->>L: append 'claude (ts):' block<br/>write 'session:' header
  Note over L: reminder still unchecked,<br/>ready for next 'you:' turn
`;
</script>

<h1>Sessions</h1>
<p class="lead">
  Two Reminders lists (<code>Claude: Sessions</code>,
  <code>Codex: Sessions</code>) where each unchecked reminder is a session
  request. Four modes share the same surface; body headers pick which one
  runs.
</p>

<h2>Four modes</h2>

<Mermaid code={modes} caption="The reminder is the request. Body headers route it to one of four execution paths." />

<table>
  <thead>
    <tr><th>Mode</th><th>Trigger</th><th>Reminder ends as</th><th>Use case</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Interactive</strong></td>
      <td>(no header)</td>
      <td>Completed — work continues in Ghostty.</td>
      <td>Hand off a task to a real terminal session you'll attend to.</td>
    </tr>
    <tr>
      <td><strong>Capture</strong></td>
      <td><code>capture: true</code></td>
      <td>Completed — output appended to body.</td>
      <td>Headless one-shot. "What does this module do?" → answer back inside the reminder.</td>
    </tr>
    <tr>
      <td><strong>Chat</strong></td>
      <td><code>chat: true</code></td>
      <td>Unchecked across turns — checked to close.</td>
      <td>Multi-turn conversation driven entirely from Reminders.app. Each <code>you:</code> block is a new turn; <code>claude (ts):</code> blocks are replies.</td>
    </tr>
    <tr>
      <td><strong>Fixer</strong></td>
      <td><code>chat: true</code> + <code>fixer: true</code></td>
      <td>Same as chat.</td>
      <td>Self-diagnose the bridge. First turn pre-loads daemon log + state files + architecture rules so <Wordmark kind="claude-code" /> has context to repair or explain.</td>
    </tr>
  </tbody>
</table>

<h2>Common headers</h2>

<pre><code>cwd: ~/Documents/development/python/foo   # working directory (~ allowed). Default: $HOME.
capture: true                              # opt into Capture mode
chat: true                                 # opt into Chat mode
fixer: true                                # together with chat:true → Fixer mode
session: &lt;uuid&gt;                            # daemon writes this after the first chat turn</code></pre>

<p>Title + any non-header body becomes the prompt for interactive and
capture. For chat, the prompt is whatever comes after a <code>you:</code>
block.</p>

<h2>How chat mode advances</h2>

<Mermaid code={chatTurn} caption="One chat turn. The session id persists in the reminder body — close + reopen + new `you:` block resumes the same conversation." />

<h2>Auto-escalation to Fixer</h2>

<p>If any subsystem in <code>sync_once</code> fails
<code>RBRIDGE_FIXER_THRESHOLD</code> times in a row (default 5), the daemon
writes its own fixer reminder titled <code>rbridge auto-fixer</code> into
the Claude sessions list. The body has the error trail and the rule that
turns it into a Fixer-mode chat. Cooldown
<code>RBRIDGE_FIXER_COOLDOWN_S</code> (default 1h) prevents loops.</p>

<div class="callout warn">
  <strong>Fixer is not a panacea.</strong> Auto-escalation only catches
  errors that throw all the way out of a subsystem. Silent drift
  (reminders disappearing, wrong field synced) won't trigger it — that's
  what <code>rbridge lint</code> is for.
</div>

<h2>Common configuration</h2>

<table>
  <thead><tr><th>Env var</th><th>Default</th><th>Purpose</th></tr></thead>
  <tbody>
    <tr><td><code>RBRIDGE_CLAUDE_LIST</code> / <code>RBRIDGE_CODEX_LIST</code></td><td><code>Claude: Sessions</code> / <code>Codex: Sessions</code></td><td>Rename the trigger lists.</td></tr>
    <tr><td><code>RBRIDGE_CLAUDE_BIN</code> / <code>RBRIDGE_CODEX_BIN</code></td><td>(auto-discovered)</td><td>Explicit binary path. Useful when multiple Claude installs coexist.</td></tr>
    <tr><td><code>RBRIDGE_GHOSTTY_APP</code></td><td><code>/Applications/Ghostty.app</code></td><td>Terminal bundle for interactive mode.</td></tr>
    <tr><td><code>RBRIDGE_CLAUDE_FLAGS</code></td><td>(empty)</td><td>Extra flags appended to <code>claude -p</code> in chat / capture / fixer (e.g. <code>--dangerously-skip-permissions</code>).</td></tr>
    <tr><td><code>RBRIDGE_CAPTURE_TIMEOUT_S</code></td><td><code>1800</code></td><td>Hard kill for capture subprocesses.</td></tr>
    <tr><td><code>RBRIDGE_SESSIONS_TIMEOUT_S</code></td><td><code>900</code></td><td>Hard kill per chat turn.</td></tr>
  </tbody>
</table>

<h2>Why two lists and not one?</h2>

<p>So that the same machine can run both engines in parallel without title
collisions. Capture-mode output is appended to the reminder body either
way; the engine choice changes only which binary spawns. If you only use
one, set the unused list env var to a name you'll never touch (e.g.
<code>Codex: Sessions (unused)</code>) and the daemon will create it
empty and stop scanning it once it's known.</p>
