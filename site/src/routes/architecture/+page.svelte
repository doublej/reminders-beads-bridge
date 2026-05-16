<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';
  import { base } from '$app/paths';

  const modules = `
flowchart TB
  classDef daemon fill:#eaf5ec,stroke:#5fa872,color:#1a1a1a
  classDef store fill:#fdf3df,stroke:#c08832,color:#1a1a1a
  classDef extern fill:#eef2fb,stroke:#5b7fbf,color:#1a1a1a
  classDef lane fill:#fef3e8,stroke:#c98c5b,color:#1a1a1a

  subgraph entry["entry"]
    CLI["cli.py<br/>rbridge {run,sync,doctor,...}"]
    DAEMON["daemon.py<br/>sync_once · poll loop"]
  end

  subgraph beads["Beads lane"]
    PROJ["projects.py<br/>read kanban registry"]
    PLIST["projects_list.py<br/>Beads: Projects"]
    SETT["settings.py<br/>Beads: Settings"]
    README["readme.py<br/>! Beads: Readme"]
    ACT["activity.py<br/>Beads: Activity"]
    RECON["reconcile_project<br/>per visible project"]
    BODY["body.py<br/>compose / parse XML"]
    BEADS["beads.py<br/>shells out to bd CLI"]
  end

  subgraph sessions["Sessions lane"]
    TRIG["triggers.py<br/>Claude/Codex: Sessions"]
    LAUNCH["launch.py<br/>spawn Ghostty"]
    CAP["captures.py<br/>headless one-shot"]
    SESS["sessions.py<br/>multi-turn chat"]
    FIX["fixer.py<br/>self-diagnose"]
  end

  subgraph voice["Voice lane"]
    MAIL["mailbox.py<br/>Voice: &lt;slug&gt;"]
    MIRROR["mirror.py<br/>default-list breadcrumb"]
  end

  subgraph plumbing["Inert plumbing"]
    API["api.py<br/>beads-kanban HTTP"]
    EVT["events.py<br/>SSE client"]
  end

  subgraph adapters["Adapters"]
    REM["reminders.py<br/>EventKit wrapper"]
    WATCH["watcher.py<br/>EKEventStoreChanged"]
    LINK["link.py + state.py<br/>id ↔ id"]
  end

  subgraph external["External"]
    BDCLI[("bd CLI<br/>+ .beads/*.db")]:::extern
    EKS[("EventKit<br/>+ Reminders.app")]:::store
    DSK[("~/.claude/*.json<br/>state files")]:::store
    GH["Ghostty + claude/codex"]:::extern
  end

  CLI --> DAEMON
  DAEMON --> PROJ
  DAEMON --> PLIST
  DAEMON --> SETT
  DAEMON --> README
  DAEMON --> RECON
  DAEMON --> ACT
  DAEMON --> TRIG
  DAEMON --> CAP
  DAEMON --> SESS
  DAEMON --> MAIL
  RECON --> BODY
  RECON --> BEADS
  RECON --> LINK
  RECON --> REM
  BEADS --> BDCLI
  REM <--> EKS
  WATCH --> DAEMON
  EKS -. notify .-> WATCH
  PLIST --> REM
  SETT --> REM
  README --> REM
  ACT --> REM
  TRIG --> LAUNCH
  LAUNCH --> GH
  CAP --> GH
  SESS --> GH
  FIX --> SESS
  MAIL --> REM
  MAIL --> MIRROR
  MIRROR --> REM
  LINK --> DSK
  CAP --> DSK
  SESS --> DSK
  MAIL --> DSK
  ACT --> DSK
  API -. unused .-> DAEMON
  EVT -. unused .-> DAEMON

  class DAEMON,CLI,RECON,BODY,BEADS,PROJ,PLIST,SETT,README,ACT,TRIG,LAUNCH,CAP,SESS,FIX,MAIL,MIRROR,REM,WATCH,LINK daemon
  class API,EVT lane
`;

  const stateFiles = `
flowchart LR
  classDef store fill:#fdf3df,stroke:#c08832,color:#1a1a1a

  subgraph state["~/.claude/"]
    LINKS[("reminders-bridge-state.json<br/>bead-id ↔ reminder-id")]:::store
    CAPS[("reminders-bridge-captures.json<br/>pid ↔ reminder-id")]:::store
    SESSIONS[("reminders-bridge-sessions.json<br/>chat sessions: claude session-id")]:::store
    ACTIVITY[("reminders-bridge-activity.jsonl<br/>rolling event log")]:::store
    MAILBOXES[("voice-mailboxes/&lt;slug&gt;.json<br/>+ &lt;slug&gt;.brief.md")]:::store
  end

  R1["reconcile_project"] --> LINKS
  R2["captures.poll"] --> CAPS
  R3["sessions.poll"] --> SESSIONS
  R4["activity.record"] --> ACTIVITY
  R5["mailbox.{open,close,sync}"] --> MAILBOXES
`;
</script>

<h1>Architecture</h1>
<p class="lead">
  One Python package, three independent lanes, two persistence surfaces
  (EventKit + JSON state files). Everything funnels through
  <code>daemon.sync_once</code> on a 5-second tick.
</p>

<h2>Module map</h2>

<Mermaid code={modules} caption="The daemon orchestrates all three lanes per cycle. api.py / events.py are plumbing — wired but not called from the cycle yet." />

<h2>Ownership boundaries</h2>

<table>
  <thead><tr><th>Surface</th><th>Owner</th><th>Notes</th></tr></thead>
  <tbody>
    <tr>
      <td><code>Beads: &lt;project&gt;</code> bodies</td>
      <td>Daemon (most) + user (notes)</td>
      <td><code>&lt;bb:meta&gt;</code> + <code>&lt;bb:desc&gt;</code> are daemon-owned. <code>&lt;bb:notes&gt;</code> is user-owned and preserved across syncs.</td>
    </tr>
    <tr>
      <td><code>Beads: Activity</code> · <code>! Beads: Readme</code></td>
      <td>Daemon</td>
      <td>Drift is overwritten next cycle.</td>
    </tr>
    <tr>
      <td><code>Beads: Projects</code> · <code>Beads: Settings</code> rows</td>
      <td>Daemon writes / user toggles</td>
      <td>Body+title overwritten on drift; <em>completion</em> is the only signal the daemon reads back.</td>
    </tr>
    <tr>
      <td><code>Voice: &lt;slug&gt;</code> header + brief</td>
      <td>Daemon</td>
      <td>User edits are clobbered. User responses go in <em>new</em> reminders.</td>
    </tr>
    <tr>
      <td><code>Voice: &lt;slug&gt;</code> responses</td>
      <td>User (or voice agent on behalf of user)</td>
      <td>Drained via <code>rbridge mailbox read</code>.</td>
    </tr>
    <tr>
      <td><code>Claude: Sessions</code> · <code>Codex: Sessions</code></td>
      <td>User (request) / daemon (lifecycle)</td>
      <td>User writes the prompt; daemon marks completed / appends output / appends agent turns.</td>
    </tr>
  </tbody>
</table>

<h2>State files</h2>

<Mermaid code={stateFiles} caption="JSON state lives under ~/.claude/. None of these are checked into git." />

<p>State files solve one problem: EventKit reminder IDs are not stable
across iCloud sync churn, so the daemon needs a side-table linking bead
IDs to reminder IDs. The same pattern applies to in-flight captures, chat
sessions, and voice mailboxes — each is a short-lived contract between
"this process I spawned" and "the reminder that triggered it".</p>

<h2>Why three lanes and not one big sync</h2>

<p>The three lanes (Beads / Sessions / Voice) only share the EventKit
adapter and the activity log. Their data models, lifecycles, and failure
modes are all different — coupling them would force the simpler lanes to
inherit the complexity of the most complex one.</p>

<ul>
  <li><strong>Beads</strong> is field-level reconciliation against an
  external source of truth (the <code>bd</code> CLI). Heavy on diffing,
  light on lifecycle.</li>
  <li><strong>Sessions</strong> is a job runner. Each reminder is a unit
  of work that either kicks off a process (interactive / capture) or
  drives a long-lived conversation (chat). Heavy on process management.</li>
  <li><strong>Voice</strong> is a message bus. The daemon places one
  message (the brief), the human places replies (responses). Heavy on
  format conventions, light on logic.</li>
</ul>

<p>The daemon's job is to call each lane in sequence per cycle and isolate
failures: a panic in <code>sessions.poll</code> never breaks
<code>reconcile_project</code>.</p>

<h2>What's not in the daemon</h2>

<ul>
  <li><strong>HTTP server.</strong> No incoming requests; the CLI is the
  only entry. <code>api.py</code> + <code>events.py</code> exist as an
  outgoing client for beads-kanban but are unused by the daemon today.</li>
  <li><strong>Web UI.</strong> Apple Reminders is the UI.</li>
  <li><strong>Background queue / DB.</strong> JSON files + the EventKit
  store are the only persistence.</li>
  <li><strong>Event channel from beads.</strong> No webhook, no LISTEN/
  NOTIFY. The 5-second poll is the freshness budget.</li>
</ul>

<p>For the per-cycle flow inside <code>sync_once</code>, see
<a href="{base}/sync/">Sync cycle</a>.</p>
