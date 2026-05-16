<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';

  const cycle = `
sequenceDiagram
  autonumber
  participant W as watcher.py
  participant D as daemon.sync_once
  participant L as control lists<br/>(Projects/Settings/Readme/Activity)
  participant S as standalone lanes<br/>(Sessions · Voice · Captures)
  participant R as reconcile_project<br/>(per visible project)
  participant BD as bd CLI
  participant EK as EventKit
  participant ST as state.json

  Note over W,D: wake every 5s OR on EKEventStoreChanged
  W->>D: tick
  D->>L: projects_list.sync → hidden set
  D->>L: settings.sync → toggles
  D->>L: readme.sync · activity.sync
  D->>S: captures.poll · sessions.poll · triggers · mailbox.sync
  D->>L: projects_list.apply_hides (delete hidden lists)
  loop for each visible project
    D->>R: reconcile
    R->>BD: bd list --json --all
    BD-->>R: issues[]
    R->>EK: list reminders (project list)
    EK-->>R: reminders[]
    R->>R: capture unprefixed reminders → bd create
    R->>R: diff: adopt · dedup · compose body · detect close/reopen
    R->>EK: batch (creates · updates · deletes)
    R->>BD: bd close / bd reopen (signals)
    R->>ST: persist link map
  end
  D-->>W: done
`;

  const writeback = `
sequenceDiagram
  autonumber
  actor U as user
  participant REM as Reminders.app
  participant W as watcher
  participant D as daemon
  participant BD as bd CLI

  rect rgb(124, 58, 237, 0.08)
    Note over U,REM: Capture (R → B)
    U->>REM: add reminder in Beads: foo<br/>title "filters reset on tab switch"
    REM-->>W: EKEventStoreChanged
    W->>D: wake
    D->>REM: list reminders
    D->>D: detect no 'bd-id:' prefix
    D->>BD: bd create
    BD-->>D: bd-42
    D->>REM: rename to "bd-42: filters reset…"<br/>+ body restructure
  end

  rect rgb(245, 166, 35, 0.08)
    Note over U,REM: Close (R → B)
    U->>REM: check "bd-42"
    REM-->>W: EKEventStoreChanged
    W->>D: wake
    D->>D: link.reminder_completed flip<br/>False → True
    D->>BD: bd close bd-42
  end

  rect rgb(108, 209, 139, 0.08)
    Note over U,REM: Notes edit (R-only)
    U->>REM: edit text inside &lt;bb:notes&gt;
    REM-->>W: EKEventStoreChanged
    W->>D: wake
    D->>REM: list reminders
    D->>D: body.compose preserves &lt;bb:notes&gt;<br/>no bead-side update
  end
`;

  const tamper = `
flowchart LR
  classDef ok fill:#6cd18b,stroke:#15803d,color:#1a1d21
  classDef bad fill:#ff7a85,stroke:#b91c1c,color:#1a1d21
  classDef fix fill:#ffb55b,stroke:#b45309,color:#1a1d21

  A["expected = body.compose(issue, current_notes)"]:::ok
  B{"expected == actual?"}
  C["no change · skip"]:::ok
  D["bb:meta or bb:desc was edited"]:::bad
  E["rewrite from bead state<br/>preserve bb:notes<br/>prepend bb:restored banner"]:::fix
  F["activity.record('restored', …)"]:::fix
  G["next sync: banner drops on clean roundtrip"]:::ok

  A --> B
  B -- yes --> C
  B -- no --> D --> E --> F --> G
`;
</script>

<h1>Sync cycle</h1>
<p class="lead">
  Every 5 seconds (or sooner, on an EventKit change notification),
  <code>daemon.sync_once</code> walks all three lanes in a fixed order.
  Reconcile is idempotent — a quiet cycle should log zero changes.
</p>

<h2>One full cycle</h2>

<Mermaid code={cycle} caption="The control lists + standalone lanes run once; reconcile runs per visible project." />

<p>The order matters. Control lists (Projects, Settings) feed flags into
the per-project reconcile (visibility, <code>show_completed</code>). The
standalone lanes run before reconcile so a long beads pass can't starve
session triggers or voice mailbox drift.</p>

<h2>Reminder → bead signals (the only writes back)</h2>

<p>Three small upstream flows from Reminders.app into beads. Everything
else is one-way (bead → reminder).</p>

<Mermaid code={writeback} caption="Three reverse signals: capture, close, notes-edit. All other reminder edits are clobbered next sync." />

<h2>Tamper handling</h2>

<p>If a user (or a confused agent) edits inside <code>&lt;bb:meta&gt;</code>
or <code>&lt;bb:desc&gt;</code>, the next sync notices on the expected/
actual diff:</p>

<Mermaid code={tamper} caption="Tamper is non-fatal. The body is rewritten from bead state, notes are preserved, a banner records the event, and the banner self-clears on the next clean cycle." />

<h2>Polling vs notifications</h2>

<table>
  <thead><tr><th>Trigger</th><th>Latency</th><th>Notes</th></tr></thead>
  <tbody>
    <tr>
      <td>Interval (default)</td>
      <td>≤ 5s</td>
      <td>launchd plist overrides the in-code 30s default to 5s. Acceptable for a personal control surface.</td>
    </tr>
    <tr>
      <td><code>EKEventStoreChanged</code></td>
      <td>~ 1s</td>
      <td>Fires only for changes made on the host Mac. iCloud sync from iPhone does not surface as this notification — it lands silently in the calendar store and waits for the next interval poll.</td>
    </tr>
    <tr>
      <td>SIGTERM / launchd unload</td>
      <td>—</td>
      <td>Daemon dies between cycles, no cleanup needed. State files are written at the end of each cycle, not mid-batch.</td>
    </tr>
  </tbody>
</table>

<h2>Failure isolation</h2>

<p>Each subsystem in <code>sync_once</code> runs through <code>_safe</code>:
a wrapper that catches exceptions, increments a per-subsystem failure
counter, and triggers the auto-fixer (a self-diagnose <code>claude</code>
session) when the counter crosses <code>RBRIDGE_FIXER_THRESHOLD</code>
(default 5). One broken project's <code>bd list --json</code> never blocks
the rest.</p>

<div class="callout">
  <strong>Cooldown.</strong> Auto-fixer also enforces
  <code>RBRIDGE_FIXER_COOLDOWN_S</code> (default 1h) between
  escalations so a hard-down dependency can't spawn unlimited
  self-debug sessions.
</div>
