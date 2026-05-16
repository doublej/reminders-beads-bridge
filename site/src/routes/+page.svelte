<script lang="ts">
  import Mermaid from '$lib/components/Mermaid.svelte';
  import Terminal from '$lib/components/Terminal.svelte';
  import { base } from '$app/paths';

  // Overview diagram — three lanes, iCloud bridging iOS ↔ macOS,
  // Claude iOS as a peer agent talking to local EventKit on the phone.
  const overview = `
flowchart LR
  classDef human fill:#fef3e8,stroke:#c98c5b,color:#2a2a2a
  classDef agent fill:#edf2fa,stroke:#2266cc,color:#2a2a2a
  classDef store fill:#fdf3df,stroke:#c08832,color:#2a2a2a
  classDef daemon fill:#eaf5ec,stroke:#5fa872,color:#2a2a2a
  classDef cloud fill:#f0f0f0,stroke:#888,color:#2a2a2a

  USER(["👤 user"]):::human
  CC["Claude Code<br/>(project agent)"]:::agent
  CV["Claude Voice<br/>(voice agent)"]:::agent
  CIOS["Claude iOS<br/>(reminder_*_v0 tools)"]:::agent
  IOS[("Reminders.app<br/>(iOS · EventKit)")]:::store
  MAC[("Reminders.app<br/>(macOS · EventKit)")]:::store
  ICLOUD{{"iCloud<br/>reminders sync"}}:::cloud
  BD[("bd CLI<br/>+ .beads/*.db")]:::store
  RB["rbridge daemon<br/>(launchd · 5s poll)"]:::daemon

  USER -- "talks to" --> CV
  USER -- "types in terminal" --> CC
  USER -- "taps" --> IOS

  CIOS -- "reminder_search_v0 /<br/>reminder_create_v0 /<br/>reminder_update_v0" --> IOS

  IOS <-. "background sync" .-> ICLOUD
  ICLOUD <-. "background sync" .-> MAC

  CC -- "opens voice mailbox" --> RB
  CC -- "writes / closes beads" --> BD

  RB <--> MAC
  RB <--> BD

  CV -. "reads brief reminder" .-> IOS
  CV -. "writes response reminders" .-> IOS
`;
</script>

<section class="hero">
  <figure class="hero-figure">
    <img
      src="{base}/hero.png"
      alt="Reminders.app rendered as an industrial control panel — lists shown as LCD-style displays, daemon switches and gauges around the edges, with HOST UNDER FULL CONTROL displayed in the central readout."
      width="1500"
      height="934"
      loading="eager"
      fetchpriority="high"
    />
  </figure>
  <span class="badge">macOS daemon · v0.1</span>
  <h1>rbridge</h1>
  <p class="tagline">Apple Reminders as a control surface.</p>
  <p class="description">
    One daemon that turns Reminders.app into a workspace for
    Beads issues, Claude Code / Codex sessions, and voice exchanges
    with Claude Voice. Same surface, three lanes, zero new UI to learn.
  </p>
  <div class="hero-actions">
    <Terminal title="install">
<span class="comment"># clone + install + launch</span>
<span class="prompt">$</span> git clone git@github.com:doublej/reminders-beads-bridge.git
<span class="prompt">$</span> <span class="hl">cd</span> reminders-beads-bridge <span class="flag">&amp;&amp;</span> uv sync
<span class="prompt">$</span> uv run rbridge doctor   <span class="comment"># verify permissions</span>
<span class="prompt">$</span> uv run rbridge run      <span class="comment"># or load the launchd plist</span>
    </Terminal>
  </div>
  <div class="hero-links">
    <a class="hero-link" href="{base}/install/">→ Full install guide</a>
    <a class="hero-link" href="{base}/scenarios/">See it in action</a>
  </div>
</section>

<section class="three-lanes">
  <h2>Three lanes, one surface</h2>
  <p class="section-subtitle">Each lane is independent. Use any without the others.</p>
  <div class="grid grid-3">
    <div class="card">
      <span class="icon-tile" aria-hidden="true">⇄</span>
      <h3>Beads sync</h3>
      <p>
        One Reminders list per beads project, one reminder per issue.
        Edit notes on your phone, check it to close, add a reminder
        to file a bug.
      </p>
      <p><a href="{base}/sync/">Sync cycle →</a></p>
    </div>
    <div class="card">
      <span class="icon-tile" aria-hidden="true">▸</span>
      <h3>Sessions</h3>
      <p>
        Two reminders lists fire <code>claude</code> / <code>codex</code>
        sessions: interactive Ghostty, headless capture, or multi-turn
        chat right inside the reminder body.
      </p>
      <p><a href="{base}/sessions/">Session modes →</a></p>
    </div>
    <div class="card">
      <span class="icon-tile" aria-hidden="true">★</span>
      <h3>Voice mailboxes</h3>
      <p>
        The project agent composes a brief, the daemon drops it in
        <code>Voice: &lt;slug&gt;</code>, the user walks with the voice
        agent, responses come back as reminders.
      </p>
      <p><a href="{base}/voice/">Voice flow →</a></p>
    </div>
  </div>
</section>

<section>
  <h2>The shape of the system</h2>
  <p>
    Three roles, two devices, one iCloud-synced calendar store. The
    daemon brokers everything on the Mac side; on iOS,
    <strong>Claude iOS</strong> drives Reminders directly through native
    <code>reminder_*_v0</code> tools.
  </p>

  <Mermaid
    code={overview}
    caption="iCloud bridges the iOS and macOS calendar stores; rbridge sees both via EventKit on the Mac."
  />

  <p>
    The dashed lines are asynchronous — iCloud delivers reminders at its
    own pace (seconds to minutes depending on network). The daemon's
    5-second poll is what bounds visible latency on the Mac side.
  </p>
</section>

<section>
  <h2>Why Reminders.app</h2>
  <p>Three properties no other UI gives you for free on Apple devices:</p>
  <div class="grid grid-3">
    <div class="card">
      <span class="icon-tile" aria-hidden="true">∞</span>
      <h3>Always there</h3>
      <p>
        Pre-installed on every Mac, iPhone, iPad. No login, no app to
        launch, no battery cost beyond what's already running.
      </p>
    </div>
    <div class="card">
      <span class="icon-tile" aria-hidden="true">☁︎</span>
      <h3>iCloud-synced</h3>
      <p>
        Edits propagate cross-device with zero infrastructure. Add a
        bead from your phone in airplane mode — it lands when you
        reconnect.
      </p>
    </div>
    <div class="card">
      <span class="icon-tile" aria-hidden="true">⌨</span>
      <h3>Scriptable</h3>
      <p>
        EventKit on macOS gives a stable Python / PyObjC binding.
        Reminders are objects with titles, bodies, priorities,
        completion flags, and a <code>changed</code> notification.
      </p>
    </div>
  </div>
  <p>
    The cost: no real-time push channel from the daemon to iOS — the
    in-process <code>EKEventStoreChanged</code> notification only fires
    for local edits on the host Mac. Hence the 5-second poll. For a
    personal control surface, that's well under the "feels instant"
    threshold.
  </p>
</section>

<section>
  <h2>Where to go next</h2>
  <div class="grid grid-3">
    <div class="card">
      <span class="icon-tile" aria-hidden="true">1</span>
      <h3>Get it running</h3>
      <p>
        Clean-macOS install: prerequisites, clone, doctor, launchd.
        About 10 minutes.
      </p>
      <p><a href="{base}/install/">Install →</a></p>
    </div>
    <div class="card">
      <span class="icon-tile" aria-hidden="true">2</span>
      <h3>Read the daemon</h3>
      <p>
        Module map, ownership boundaries, what the sync cycle does
        every 5 seconds.
      </p>
      <p><a href="{base}/architecture/">Architecture →</a></p>
    </div>
    <div class="card">
      <span class="icon-tile" aria-hidden="true">3</span>
      <h3>See it in action</h3>
      <p>
        Three end-to-end scenarios — capture from iPhone, voice walk,
        chat session.
      </p>
      <p><a href="{base}/scenarios/">Scenarios →</a></p>
    </div>
  </div>
</section>

<style>
  .hero {
    padding: 30px 0 30px;
    text-align: center;
  }
  .hero-figure {
    margin: 0 0 32px;
    /* spill to the full container width on wider screens */
    margin-left: calc(-1 * var(--container-padding));
    margin-right: calc(-1 * var(--container-padding));
  }
  .hero-figure img {
    width: 100%;
    height: auto;
    display: block;
    border-radius: 12px;
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.15);
  }
  .hero h1 { font-size: 4.5rem; }
  .tagline {
    font-size: 1.4rem;
    font-weight: 500;
    color: var(--text-primary);
    margin-bottom: 12px;
  }
  .description {
    font-size: 1.1rem;
    color: var(--text-secondary);
    max-width: 620px;
    margin: 0 auto 32px;
  }
  .hero-actions {
    display: flex;
    justify-content: center;
    margin-bottom: 18px;
  }
  .hero-actions > :global(*) {
    max-width: 640px;
    width: 100%;
    text-align: left;
  }
  .hero-links {
    display: flex;
    justify-content: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .hero-link {
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.9rem;
    padding: 8px 18px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg-secondary);
    transition: border-color 0.2s, color 0.2s;
  }
  .hero-link:hover {
    border-color: var(--text-tertiary);
    color: var(--text-primary);
    opacity: 1;
  }

  section { padding: 28px 0; }
  .three-lanes h2,
  section h2 { font-size: 1.8rem; }
  .section-subtitle {
    color: var(--text-secondary);
    margin-bottom: 24px;
  }

  @media (max-width: 700px) {
    .hero { padding: 40px 0 20px; }
    .hero h1 { font-size: 3rem; }
    .tagline { font-size: 1.1rem; }
  }
</style>
