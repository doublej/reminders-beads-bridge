<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';
  import Wordmark from '$lib/components/Wordmark.svelte';
  import { base } from '$app/paths';

  const overview = `
flowchart LR
  classDef human fill:#fef3e8,stroke:#c98c5b,color:#1a1a1a
  classDef agent fill:#eef2fb,stroke:#5b7fbf,color:#1a1a1a
  classDef store fill:#fdf3df,stroke:#c08832,color:#1a1a1a
  classDef daemon fill:#eaf5ec,stroke:#5fa872,color:#1a1a1a

  USER(["👤 user"]):::human
  CC["Claude Code<br/>(project agent)"]:::agent
  CV["Claude Voice<br/>(voice agent)"]:::agent
  REM[("Apple Reminders<br/>(macOS + iOS)")]:::store
  BD[("bd CLI + .beads/*.db<br/>source of truth")]:::store
  RB["rbridge daemon<br/>(launchd · 5s poll)"]:::daemon

  USER -- "edits reminders" --> REM
  USER -- "voice walk" --> CV
  USER -- "types in terminal" --> CC

  CC -- "opens voice mailbox" --> RB
  CC -- "writes / closes beads" --> BD

  RB <--> REM
  RB <--> BD
  RB -. "writes brief" .-> REM
  CV -. "reads brief from list" .-> REM
  CV -. "writes responses to list" .-> REM
  CC -. "drains responses" .-> RB
`;
</script>

<h1>reminders-bridge</h1>
<p class="lead">
  A macOS daemon that turns Apple Reminders into a control surface for
  <Wordmark kind="beads" /> issue tracking,
  <Wordmark kind="claude-code" /> sessions, and voice exchanges with
  <Wordmark kind="claude-voice" />.
</p>

<div class="grid grid-3">
  <div class="card">
    <h3>1 · Beads sync</h3>
    <p>One Reminders list per beads project, one reminder per issue. Edit
    notes from your phone, check it to close, add a reminder to file a bug.</p>
    <p><a href="{base}/sync/">Sync cycle →</a></p>
  </div>
  <div class="card">
    <h3>2 · Sessions</h3>
    <p>Two dedicated lists fire <code>claude</code> / <code>codex</code>
    sessions: open a terminal, capture a one-shot reply, or hold a
    multi-turn chat — all from Reminders.app.</p>
    <p><a href="{base}/sessions/">Session modes →</a></p>
  </div>
  <div class="card">
    <h3>3 · Voice mailboxes</h3>
    <p>The project agent composes a brief, the daemon drops it into a
    <code>Voice: &lt;slug&gt;</code> list, the user walks with the voice
    agent, responses come back as reminders.</p>
    <p><a href="{base}/voice/">Voice flow →</a></p>
  </div>
</div>

<h2>The shape of the system</h2>

<Mermaid code={overview} caption="Three lanes converge on Apple Reminders. The daemon brokers everything." />

<p>Each lane is independent: you can use beads sync without sessions, sessions
without voice, voice without either. The common substrate is a Reminders
list with conventions on titles, body markup, and completion state.</p>

<h2>Why Reminders.app at all?</h2>

<p>Three properties no other UI gives you for free on Apple devices:</p>
<ul>
  <li><strong>Always there.</strong> Pre-installed on every Mac, iPhone,
  iPad. No login, no app to launch, no battery cost beyond what's already
  running.</li>
  <li><strong>iCloud-synced.</strong> Edits propagate cross-device with
  zero infrastructure. Add a bead from your phone in airplane mode — it
  lands when you reconnect.</li>
  <li><strong>Scriptable.</strong> EventKit on macOS gives a stable
  Python/PyObjC binding. Reminders are objects with titles, bodies,
  priorities, completion flags, and a <code>changed</code> notification.</li>
</ul>

<p>The cost: no real-time push channel from the daemon to iOS (the
EventKit notification only fires in-process on the host Mac). Hence the
5-second poll. For a personal control surface that's well under the
"feels instant" threshold.</p>

<h2>What's next</h2>

<div class="grid grid-2">
  <div class="card">
    <h3>Get it running</h3>
    <p>Clean-machine install for macOS: prerequisites, clone, doctor,
    launchd. About 10 minutes.</p>
    <p><a href="{base}/install/">Install →</a></p>
  </div>
  <div class="card">
    <h3>Understand the daemon</h3>
    <p>Module map, ownership boundaries, what the sync cycle does every
    5 seconds.</p>
    <p><a href="{base}/architecture/">Architecture →</a></p>
  </div>
  <div class="card">
    <h3>See it in action</h3>
    <p>Three end-to-end scenarios: capture from iPhone, voice walk, chat
    session.</p>
    <p><a href="{base}/scenarios/">Scenarios →</a></p>
  </div>
</div>
