<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';
  import Wordmark from '$lib/components/Wordmark.svelte';

  const triangle = `
flowchart LR
  classDef human fill:#ffb98a,stroke:#c98c5b,color:#1a1d21
  classDef agent fill:#7aa8ff,stroke:#2563eb,color:#1a1d21
  classDef artifact fill:#f5a623,stroke:#b45309,color:#1a1d21

  U(["👤 user"]):::human
  PA["project agent<br/>(Claude Code session)"]:::agent
  VA["voice agent<br/>(Claude Voice on the phone)"]:::agent
  B[("brief<br/>(saved to disk + Reminders)")]:::artifact

  U -- "types prompts" --> PA
  PA -- "composes" --> B
  B -- "reads" --> VA
  U <-- "talks with<br/>(voice walk)" --> VA
  VA -- "writes responses<br/>(decision: · note: · question: · deferred: · done)" --> B
  B -- "drained by<br/>rbridge mailbox read" --> PA
`;

  const lifecycle = `
stateDiagram-v2
  [*] --> open : /voice-chat-takeout
  open --> brief_pinned : daemon writes header + brief
  brief_pinned --> walking : user starts voice walk
  walking --> draining : user adds responses<br/>(decision/note/question/deferred)
  draining --> walking : more turns
  draining --> closing : user adds 'done' OR<br/>project agent runs `mailbox close`
  closing --> [*] : list deleted · state cleared · mirror removed

  walking --> closing : user deletes the list<br/>(daemon GC next cycle)
`;

  const surface = `
flowchart TB
  classDef daemon fill:#6cd18b,stroke:#15803d,color:#1a1d21
  classDef user fill:#ffb98a,stroke:#c98c5b,color:#1a1d21
  classDef store fill:#f5a623,stroke:#b45309,color:#1a1d21

  subgraph EXCH["Voice: &lt;slug&gt;  (the exchange list)"]
    H["How this list works<br/>(header reminder)"]:::daemon
    BR["Brief for &lt;slug&gt;<br/>(brief reminder)"]:::daemon
    R1["decision: ship the migration"]:::user
    R2["note: redirect path matters"]:::user
    R3["question: shape of the rollback?"]:::user
    R4["deferred: bosdieren slug rename"]:::user
  end

  subgraph DEFAULT["default Reminders list"]
    M["Voice exchange open: &lt;slug&gt;<br/>(silent breadcrumb)"]:::daemon
  end

  subgraph DISK["~/.claude/voice-mailboxes/"]
    S[("&lt;slug&gt;.json<br/>state")]:::store
    B[("&lt;slug&gt;.brief.md<br/>brief text")]:::store
  end
`;
</script>

<h1>Voice mailboxes</h1>
<p class="lead">
  Hand off a Claude Code conversation to the voice agent on the phone,
  walk while talking, get structured responses back. One open exchange =
  one Reminders list = one entry in <code>~/.claude/voice-mailboxes/</code>.
</p>

<h2>Three roles</h2>

<p>The vocabulary matters because the brief addresses one role and refers
to the other two — getting POV wrong makes the brief unreadable to the
voice agent.</p>

<Mermaid code={triangle} caption="The user talks to both agents; the project agent writes for the voice agent; the voice agent talks with the user out loud." />

<table>
  <thead><tr><th>Role</th><th>Surface</th><th>POV in brief</th></tr></thead>
  <tbody>
    <tr>
      <td><strong>user</strong></td>
      <td>Human. Types in the terminal, speaks on the phone.</td>
      <td>Third person ("the user", "they"). Never addressed directly in writing.</td>
    </tr>
    <tr>
      <td><strong>project agent</strong></td>
      <td><Wordmark kind="claude-code" /> session that composes the brief.</td>
      <td>First person ("I").</td>
    </tr>
    <tr>
      <td><strong>voice agent</strong></td>
      <td><Wordmark kind="claude-voice" /> on the phone. Reader of the brief.</td>
      <td>Second person ("you"). The reader.</td>
    </tr>
  </tbody>
</table>

<h2>Lifecycle</h2>

<Mermaid code={lifecycle} caption="One open exchange. Idempotent re-open from the same slug rewrites header + brief but preserves prior responses." />

<h2>What the daemon owns vs the user owns</h2>

<Mermaid code={surface} caption="Five surfaces per exchange. Daemon-owned in green; user-written in orange; state files in amber." />

<h2>Response kinds</h2>

<p>The brief's writeback contract lists five optional title prefixes the
voice agent can use when writing a response. Anything without a prefix is
classified as <code>free</code> on drain.</p>

<table>
  <thead><tr><th>Prefix</th><th>Kind</th><th>Meaning</th></tr></thead>
  <tbody>
    <tr><td><code>decision:</code></td><td><span class="pill ok">decision</span></td><td>User committed to something on the call.</td></tr>
    <tr><td><code>note:</code></td><td><span class="pill accent">note</span></td><td>Context worth keeping; no action implied.</td></tr>
    <tr><td><code>question:</code></td><td><span class="pill warn">question</span></td><td>User wants the project agent to come back with an answer.</td></tr>
    <tr><td><code>deferred:</code></td><td><span class="pill warn">deferred</span></td><td>Talked about, no decision yet — explicit punt to revisit later.</td></tr>
    <tr><td><code>done</code></td><td><span class="pill">done</span></td><td>Closes the exchange. Daemon tears the list down on the next cycle.</td></tr>
    <tr><td>(none)</td><td><span class="pill">free</span></td><td>Plain text. Kept as-is on drain.</td></tr>
  </tbody>
</table>

<div class="callout">
  <strong>Why <code>deferred</code> and not just <code>question</code>?</strong>
  A deferral is a conversational outcome — the user already heard the
  options and chose not to choose yet. Tracking it separately lets the
  project agent re-raise it as a discussion item next session, instead of
  treating it as a fresh unanswered question.
</div>

<h2>CLI surface</h2>

<table>
  <thead><tr><th>Command</th><th>Effect</th></tr></thead>
  <tbody>
    <tr>
      <td><code>rbridge mailbox open --slug X --kind REMINDERS --brief -</code></td>
      <td>Idempotent. Reads brief from stdin, creates / refreshes the exchange list, mirror, state file.</td>
    </tr>
    <tr>
      <td><code>rbridge mailbox read --slug X</code></td>
      <td>JSON dump of responses (header + brief excluded). Warns on stderr if a <code>done</code> reminder is present.</td>
    </tr>
    <tr>
      <td><code>rbridge mailbox close --slug X</code></td>
      <td>Tears down: deletes list, removes mirror, drops state. Returns truthful status (list deleted / was missing / failed).</td>
    </tr>
    <tr>
      <td><code>rbridge mailbox refresh --slug X</code></td>
      <td>Re-up header + brief from on-disk brief, no other changes.</td>
    </tr>
    <tr>
      <td><code>rbridge mailbox list</code></td>
      <td>Enumerate active exchanges.</td>
    </tr>
  </tbody>
</table>

<p>None of these require the daemon to be running — they all hit EventKit
directly. The daemon only adds GC + drift correction on top.</p>

<h2>Discoverability — silent by design</h2>

<p>No alarms, no notifications, no "Today" due dates. The signals an open
exchange leaves are:</p>
<ul>
  <li>The exchange list itself in the sidebar.</li>
  <li>A high-priority breadcrumb reminder <code>Voice exchange open: &lt;slug&gt;</code> in the user's default list.</li>
  <li><code>rbridge mailbox list</code> for the agent itself.</li>
</ul>

<p>This is intentional: agents may open exchanges overnight, during
meetings, or while the user is AFK. Pushing alerts in those scenarios is
worse than silence. The user discovers the exchange the next time they
glance at Reminders.app, which on iOS happens naturally.</p>

<p>Disable the breadcrumb with <code>RBRIDGE_MAILBOX_MIRROR=false</code>.</p>

<h2>Slug rules</h2>

<ul>
  <li>Grammar: <code>[a-z0-9][a-z0-9-]&lcub;0,47&rcub;</code>. Kebab-case, 2-5 words.</li>
  <li>Topic-first, not action-first: <code>wallgen-shipping-decision</code>, not <code>decide-wallgen-shipping</code>.</li>
  <li>Skip filler verbs (<code>figure-out-</code>, <code>talk-about-</code>, <code>discuss-</code>).</li>
  <li>If the conversation has a project name, lead with it (<code>pimpelmees-shopify-cutover</code>).</li>
  <li>Slug collision on <code>open</code> is non-destructive — header + brief are rewritten, prior responses preserved.</li>
</ul>
