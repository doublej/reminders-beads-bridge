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
    { href: '/sync', label: 'Sync' },
    { href: '/voice', label: 'Voice' },
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

<nav class="topnav">
  <div class="nav-inner">
    <a class="wordmark" href="{base}/">rbridge</a>
    <div class="nav-links">
      {#each nav as item}
        <a class:active={active(item.href)} href="{base}{item.href}">{item.label}</a>
      {/each}
    </div>
    <a
      class="gh"
      href="https://github.com/doublej/reminders-beads-bridge"
      target="_blank"
      rel="noopener"
      aria-label="GitHub repository"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.8 10.9.6.1.8-.2.8-.6v-2.2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2.9-.3 2-.4 3-.4s2.1.1 3 .4c2.3-1.5 3.3-1.2 3.3-1.2.6 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.5-1.5 7.8-5.8 7.8-10.9C23.5 5.7 18.3.5 12 .5z"/></svg>
    </a>
  </div>
</nav>

<main>
  {@render children()}
</main>

<footer>
  <div class="footer-inner">
    <span>Apple Reminders ↔ Beads ↔ Claude Code · Claude Voice.</span>
    <span class="dim"><a href="https://github.com/doublej/reminders-beads-bridge">github</a> · macOS daemon · MIT</span>
  </div>
</footer>

<style>
  .topnav {
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(248, 248, 248, 0.85);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
  }
  .nav-inner {
    max-width: var(--container-max-width);
    margin: 0 auto;
    padding: 0 var(--container-padding);
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    gap: 16px;
  }

  .wordmark {
    font-family: var(--font-mono);
    font-size: 1.3rem;
    font-weight: 500;
    color: var(--text-primary);
    text-decoration: none;
    letter-spacing: -0.02em;
    flex-shrink: 0;
  }

  .nav-links {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
    justify-content: center;
    flex: 1;
  }
  .nav-links a {
    font-family: var(--font-sans);
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-secondary);
    text-decoration: none;
    padding: 6px 12px;
    border-radius: 6px;
    transition: color 0.15s, background 0.15s;
  }
  .nav-links a:hover { color: var(--text-primary); background: rgba(0, 0, 0, 0.04); }
  .nav-links a.active { color: var(--text-primary); }

  .gh {
    color: var(--text-tertiary);
    display: inline-flex;
    align-items: center;
    text-decoration: none;
    flex-shrink: 0;
  }
  .gh:hover { color: var(--text-primary); opacity: 1; }

  main {
    max-width: var(--container-max-width);
    margin: 0 auto;
    padding: 0 var(--container-padding) 80px;
  }

  footer {
    border-top: 1px solid var(--border);
    padding: 28px 0;
    color: var(--text-tertiary);
    font-size: 0.85rem;
    background: var(--bg-secondary);
  }
  .footer-inner {
    max-width: var(--container-max-width);
    margin: 0 auto;
    padding: 0 var(--container-padding);
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.6rem;
    font-family: var(--font-mono);
  }
  .dim a { color: var(--text-secondary); }
  .dim a:hover { color: var(--text-primary); }

  @media (max-width: 760px) {
    .nav-inner { flex-wrap: wrap; height: auto; padding-top: 10px; padding-bottom: 10px; }
    .nav-links { order: 3; width: 100%; justify-content: flex-start; gap: 2px; }
  }
</style>
