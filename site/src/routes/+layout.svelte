<script lang="ts">
  import '../app.css';
  import { page } from '$app/state';
  import { base } from '$app/paths';

  let { children } = $props();

  const nav = [
    { href: '/', label: 'Overview' },
    { href: '/install', label: 'Install' },
    { href: '/architecture', label: 'Architecture' },
    { href: '/sync', label: 'Sync cycle' },
    { href: '/voice', label: 'Voice mailboxes' },
    { href: '/sessions', label: 'Sessions' },
    { href: '/scenarios', label: 'Scenarios' }
  ];

  function active(href: string) {
    const cur = page.url.pathname;
    if (href === '/') return cur === base + '/' || cur === base || cur === '/';
    return cur === base + href || cur.startsWith(base + href + '/');
  }
</script>

<div class="shell">
  <header class="topbar">
    <a class="brand" href="{base}/">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <path d="M7 8h10M7 12h6M7 16h8" />
      </svg>
      <span>reminders-bridge</span>
    </a>
    <nav>
      {#each nav as item}
        <a class:active={active(item.href)} href="{base}{item.href}">{item.label}</a>
      {/each}
    </nav>
    <a class="repo" href="https://github.com/doublej/reminders-beads-bridge" target="_blank" rel="noopener">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.8 10.9.6.1.8-.2.8-.6v-2.2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2.9-.3 2-.4 3-.4s2.1.1 3 .4c2.3-1.5 3.3-1.2 3.3-1.2.6 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.5-1.5 7.8-5.8 7.8-10.9C23.5 5.7 18.3.5 12 .5z"/></svg>
      doublej/reminders-beads-bridge
    </a>
  </header>

  <main>
    {@render children()}
  </main>

  <footer>
    <span>Apple Reminders ↔ Beads ↔ Claude Code / Claude Voice.</span>
    <span class="dim">macOS daemon · MIT</span>
  </footer>
</div>

<style>
  .shell {
    min-height: 100vh;
    display: grid;
    grid-template-rows: auto 1fr auto;
  }

  .topbar {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 1.5rem;
    padding: 0.9rem 1.5rem;
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--bg) 90%, transparent);
    backdrop-filter: blur(8px);
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .brand {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--mono);
    font-weight: 700;
    color: var(--text);
    border-bottom: 0;
    font-size: 0.95rem;
  }
  .brand svg { color: var(--accent); }

  nav {
    display: flex;
    gap: 0.2rem;
    flex-wrap: wrap;
    justify-content: center;
  }
  nav a {
    color: var(--text-dim);
    padding: 0.35em 0.7em;
    border-radius: 6px;
    border-bottom: 0;
    font-size: 0.92rem;
    transition: background 120ms ease, color 120ms ease;
  }
  nav a:hover { color: var(--text); background: var(--surface); }
  nav a.active { color: var(--text); background: var(--surface-2); }

  .repo {
    display: inline-flex;
    align-items: center;
    gap: 0.4em;
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 0.82rem;
    border-bottom: 0;
  }
  .repo:hover { color: var(--text); }

  main {
    max-width: 880px;
    width: 100%;
    margin: 0 auto;
    padding: 2.5rem 1.5rem 4rem;
  }

  footer {
    border-top: 1px solid var(--border);
    padding: 1.2rem 1.5rem;
    display: flex;
    justify-content: space-between;
    color: var(--text-dim);
    font-size: 0.85rem;
    font-family: var(--mono);
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .dim { opacity: 0.7; }

  @media (max-width: 760px) {
    .topbar { grid-template-columns: 1fr; gap: 0.6rem; }
    .repo { display: none; }
    nav { justify-content: flex-start; }
  }
</style>
