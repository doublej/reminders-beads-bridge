<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';
  import { base } from '$app/paths';

  const installFlow = `
flowchart TD
  classDef step fill:#7aa8ff,stroke:#2563eb,color:#1a1d21
  classDef verify fill:#6cd18b,stroke:#15803d,color:#1a1d21
  classDef gate fill:#ffb55b,stroke:#b45309,color:#1a1d21

  A["1 · Prereqs<br/>uv · bd · git · Reminders.app"]:::step
  B["2 · Clone repo"]:::step
  C["3 · uv sync"]:::step
  D["4 · uv run rbridge doctor"]:::verify
  E{"Doctor green?"}:::gate
  F["5 · Grant Reminders +<br/>Automation permissions"]:::step
  G["6 · uv run rbridge sync<br/>(one-shot reconcile)"]:::verify
  H["7 · Install launchd plist"]:::step
  I["8 · tail logs · verify cycle"]:::verify
  J[("running 24/7")]

  A --> B --> C --> D --> E
  E -- no --> F --> D
  E -- yes --> G --> H --> I --> J
`;
</script>

<h1>Install</h1>
<p class="lead">
  Clean-macOS install for other devs. Assumes you have admin on the machine
  and command-line comfort. About 10 minutes end-to-end, most of which is
  granting permissions.
</p>

<Mermaid code={installFlow} caption="Install flow — verification gates in green, decision in orange." />

<h2>1 · Prerequisites</h2>

<p>Four things have to be on the machine before anything else:</p>

<table>
  <thead><tr><th>Tool</th><th>Why</th><th>Install</th></tr></thead>
  <tbody>
    <tr>
      <td><code>uv</code></td>
      <td>Python package manager. Drives <code>rbridge</code> + venv.</td>
      <td><code>brew install uv</code></td>
    </tr>
    <tr>
      <td><code>bd</code> (beads)</td>
      <td>Issue tracker — source of truth for the Beads lane.</td>
      <td>See <a href="https://github.com/doublej/beads-kanban" target="_blank" rel="noopener">beads-kanban</a> for the install path.</td>
    </tr>
    <tr>
      <td><code>git</code></td>
      <td>Clone this repo.</td>
      <td>Bundled with Xcode CLT: <code>xcode-select --install</code></td>
    </tr>
    <tr>
      <td>Reminders.app</td>
      <td>The control surface. Pre-installed on macOS.</td>
      <td>Already there. Just open it once so iCloud registers the calendar store.</td>
    </tr>
  </tbody>
</table>

<div class="callout">
  <strong>Voice and Sessions lanes are independent.</strong> If you only
  want voice mailboxes or session triggers, you can skip <code>bd</code> —
  the daemon does not require any beads project to be registered. Doctor
  will flag it but won't refuse to run.
</div>

<h2>2 · Clone</h2>

<pre><code>cd ~/Documents/development      # or anywhere; this is a personal location
git clone git@github.com:doublej/reminders-beads-bridge.git
cd reminders-beads-bridge</code></pre>

<h2>3 · Install Python deps</h2>

<pre><code>uv sync</code></pre>

<p>This creates <code>.venv/</code> and installs the two PyObjC frameworks
(<code>EventKit</code>, <code>Cocoa</code>) plus dev tools. Takes ~30s on
a warm cache.</p>

<h2>4 · Run doctor</h2>

<pre><code>uv run rbridge doctor</code></pre>

<p>Three things get checked:</p>
<ul>
  <li><strong><code>bd</code> on PATH</strong> — fails with a path hint if
  not. Skip-able if you don't use the beads lane.</li>
  <li><strong>Reminders permission</strong> — fails the first time. macOS
  will pop a permission dialog the moment EventKit asks for the store.
  Grant it; doctor turns green on the next run.</li>
  <li><strong>Registry reachable</strong> — checks
  <code>~/.beads-kanban-projects.json</code>. Missing is fine; it just
  means no projects to sync yet.</li>
</ul>

<h2>5 · Grant permissions</h2>

<p>If doctor flagged Reminders permission, the dialog has already fired
once. macOS sometimes loses the request — open it manually:</p>

<pre><code>open "x-apple.systempreferences:com.apple.preference.security?Privacy_Reminders"</code></pre>

<p>Find <strong>uv</strong> (or your shell process) in the list and toggle
it on. Also check <strong>Privacy &amp; Security → Automation</strong> →
your terminal app should have a checkbox for <strong>Reminders</strong>.</p>

<div class="callout warn">
  <strong>If doctor still fails after granting permission</strong>, the
  cached approval might be stale. Toggle the permission off then on again,
  or run <code>tccutil reset Reminders</code> and re-run doctor — macOS
  will re-prompt cleanly.
</div>

<h2>6 · One-shot sync</h2>

<pre><code>uv run rbridge sync</code></pre>

<p>Prints the number of visible projects reconciled. If you have a
<code>~/.beads-kanban-projects.json</code>, you should see new
<code>Beads: &lt;project&gt;</code> lists appear in Reminders.app within a
second. If you don't have one yet, this just creates the four control
lists (<code>! Beads: Readme</code>, <code>Beads: Projects</code>,
<code>Beads: Settings</code>, <code>Beads: Activity</code>) and exits clean.</p>

<h2>7 · Install the launchd agent</h2>

<p>The repo ships a plist template under <code>launchd/</code>. Two paths
inside it are absolute — you need to adjust them to your machine before
loading.</p>

<pre><code># Copy + edit
cp launchd/com.jurrejan.reminders-bridge.plist ~/Library/LaunchAgents/com.&lt;you&gt;.reminders-bridge.plist
$EDITOR ~/Library/LaunchAgents/com.&lt;you&gt;.reminders-bridge.plist</code></pre>

<p>Replace inside the copied plist:</p>
<ul>
  <li><code>/Users/jurrejan</code> → your <code>$HOME</code>.</li>
  <li><code>/Users/jurrejan/Documents/development/python/reminders-bridge</code>
  → wherever you cloned the repo.</li>
  <li><code>com.jurrejan.reminders-bridge</code> →
  <code>com.&lt;you&gt;.reminders-bridge</code> in the <code>Label</code> key
  (must match the plist filename).</li>
  <li><code>/opt/homebrew/bin/uv</code> → output of <code>which uv</code> on
  your machine (Intel Macs and non-Homebrew uv installs differ).</li>
</ul>

<p>Then load:</p>

<pre><code>launchctl load ~/Library/LaunchAgents/com.&lt;you&gt;.reminders-bridge.plist</code></pre>

<h2>8 · Verify</h2>

<pre><code>tail -f ~/Library/Logs/reminders-bridge.log</code></pre>

<p>You should see a sync cycle line every 5 seconds. Open Reminders.app —
the <code>! Beads: Readme</code> list sorts to the top.</p>

<h2>Updating</h2>

<pre><code>cd ~/Documents/development/reminders-beads-bridge
git pull
uv sync
launchctl unload ~/Library/LaunchAgents/com.&lt;you&gt;.reminders-bridge.plist
launchctl load   ~/Library/LaunchAgents/com.&lt;you&gt;.reminders-bridge.plist</code></pre>

<h2>Uninstalling</h2>

<pre><code>launchctl unload ~/Library/LaunchAgents/com.&lt;you&gt;.reminders-bridge.plist
rm ~/Library/LaunchAgents/com.&lt;you&gt;.reminders-bridge.plist
rm -rf ~/.claude/reminders-bridge-state.json \
       ~/.claude/reminders-bridge-sessions.json \
       ~/.claude/reminders-bridge-captures.json \
       ~/.claude/voice-mailboxes/
# Lists in Reminders.app stay — delete them by hand if you want them gone.</code></pre>

<h2>Optional: install <code>rbridge</code> as a global CLI</h2>

<p>If you want to invoke <code>rbridge</code> from anywhere (handy for
<code>rbridge mailbox open</code> from inside a Claude Code session in a
different repo):</p>

<pre><code>uv tool install /Users/&lt;you&gt;/Documents/development/reminders-beads-bridge</code></pre>

<p>Re-run with <code>--force --reinstall</code> after pulling updates.</p>

<h2>Troubleshooting</h2>

<table>
  <thead><tr><th>Symptom</th><th>Fix</th></tr></thead>
  <tbody>
    <tr>
      <td>Doctor fails with "Reminders permission denied" repeatedly.</td>
      <td><code>tccutil reset Reminders</code>, re-run doctor, accept the dialog.</td>
    </tr>
    <tr>
      <td>launchd loads but log is empty.</td>
      <td>Check <code>launchctl print gui/$(id -u)/com.&lt;you&gt;.reminders-bridge</code> for last exit status. The PATH or HOME env var in the plist is the usual culprit.</td>
    </tr>
    <tr>
      <td>Reminders appear briefly then disappear.</td>
      <td>iCloud is fighting the daemon. Make sure the calendar source is "On My Mac" (or iCloud, consistently) — mixed sources cause delete/recreate cycles. Settings → Reminders.app → Default List.</td>
    </tr>
    <tr>
      <td><code>bd: command not found</code></td>
      <td>Beads not on PATH. If you don't need beads sync, ignore — voice and sessions still work.</td>
    </tr>
  </tbody>
</table>

<p>Once it's running, head to <a href="{base}/voice/">voice mailboxes</a>
or <a href="{base}/sessions/">sessions</a> for the lanes that don't need
any beads setup.</p>
