<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { base } from '$app/paths';
  import { obliterate } from '$lib/vendor/orphan-obliterator/index.js';

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

  onMount(() => {
    const orphans = obliterate('main p, main li, main h2, main h3');
    return () => orphans.destroy();
  });
</script>

<div class="shell">
  <header class="topbar">
    <div class="topbar-inner container">
      <a class="brand" href="{base}/">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="3" />
          <path d="M7 8h10M7 12h6M7 16h8" />
        </svg>
        <span>reminders-bridge</span>
      </a>
      <nav aria-label="Primary">
        {#each nav as item}
          <a class:active={active(item.href)} href="{base}{item.href}">{item.label}</a>
        {/each}
      </nav>
      <a
        class="repo"
        href="https://github.com/doublej/reminders-beads-bridge"
        target="_blank"
        rel="noopener"
        aria-label="GitHub repository"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.8 10.9.6.1.8-.2.8-.6v-2.2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2.9-.3 2-.4 3-.4s2.1.1 3 .4c2.3-1.5 3.3-1.2 3.3-1.2.6 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.5-1.5 7.8-5.8 7.8-10.9C23.5 5.7 18.3.5 12 .5z"/></svg>
      </a>
    </div>
  </header>

  <main class="container">
    {@render children()}
  </main>

  <footer>
    <div class="container footer-inner">
      <span>Apple Reminders ↔ Beads ↔ Claude Code / Claude Voice.</span>
      <span class="dim">macOS daemon · MIT</span>
    </div>
  </footer>
</div>

<style>
  .shell {
    min-height: 100vh;
    display: grid;
    grid-template-rows: auto 1fr auto;
  }

  .container {
    max-width: var(--container-max-width);
    margin: 0 auto;
    padding: 0 var(--container-padding);
    width: 100%;
  }

  .topbar {
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 10;
  }
  .topbar-inner {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding-top: 14px;
    padding-bottom: 14px;
  }

  .brand {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-family: var(--font-mono);
    font-weight: 500;
    color: var(--text-primary);
    font-size: 0.95rem;
    text-decoration: none;
    flex-shrink: 0;
  }
  .brand svg { color: var(--text-primary); }

  nav {
    display: flex;
    gap: 0.1rem;
    flex-wrap: wrap;
    flex: 1;
    justify-content: center;
  }
  nav a {
    color: var(--text-tertiary);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 0.95rem;
    text-decoration: none;
    transition: background 0.15s, color 0.15s;
  }
  nav a:hover { color: var(--text-primary); background: var(--bg-tertiary); }
  nav a.active { color: var(--text-primary); background: var(--bg-tertiary); }

  .repo {
    color: var(--text-tertiary);
    display: inline-flex;
    align-items: center;
    text-decoration: none;
    flex-shrink: 0;
  }
  .repo:hover { color: var(--text-primary); }

  main {
    padding-top: 48px;
    padding-bottom: 80px;
    max-width: 880px;
  }

  footer {
    border-top: 1px solid var(--border);
    padding: 32px 0;
    color: var(--text-tertiary);
    font-size: 0.9rem;
  }
  .footer-inner {
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.6rem;
    font-family: var(--font-mono);
  }
  .dim { opacity: 0.7; }

  @media (max-width: 760px) {
    .topbar-inner { flex-direction: column; align-items: flex-start; gap: 0.6rem; }
    nav { justify-content: flex-start; }
    .repo { align-self: flex-end; margin-top: -32px; }
  }
</style>
