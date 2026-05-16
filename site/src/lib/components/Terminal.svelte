<script lang="ts">
  let {
    children,
    title = '',
    variant = 'dark'
  }: { children: any; title?: string; variant?: 'dark' | 'green' } = $props();
</script>

<div class="terminal {variant}">
  <div class="terminal-header">
    <span class="dot red" aria-hidden="true"></span>
    <span class="dot yellow" aria-hidden="true"></span>
    <span class="dot green" aria-hidden="true"></span>
    {#if title}<span class="terminal-title">{title}</span>{/if}
  </div>
  <div class="terminal-body">
    {@render children()}
  </div>
</div>

<style>
  .terminal {
    border-radius: 10px;
    overflow: hidden;
    margin: 0 0 1.4rem;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.12);
    position: relative;
  }
  .terminal.dark { background: var(--bg-code); }
  .terminal.green { background: #0a0a0a; }

  .terminal-header {
    padding: 10px 14px;
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .terminal.dark .terminal-header { background: var(--bg-code-header); }
  .terminal.green .terminal-header { background: #111; }

  .dot {
    width: 11px;
    height: 11px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
  }
  .dot.red { background: #e06058; }
  .dot.yellow { background: #dba730; }
  .dot.green { background: #5cb870; }

  .terminal-title {
    margin-left: 12px;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    color: #888;
    letter-spacing: 0.02em;
  }

  .terminal-body {
    padding: 18px 22px;
    font-family: var(--font-mono);
    font-size: 0.85rem;
    line-height: 1.65;
    overflow-x: auto;
    white-space: pre;
  }
  .terminal.dark .terminal-body { color: #cfcfcf; }
  .terminal.green .terminal-body { color: #3f3; }

  .terminal-body :global(.prompt) { color: #5cb870; margin-right: 8px; }
  .terminal-body :global(.comment) { color: #6a6a6a; }
  .terminal-body :global(.flag) { color: #c98c5b; }
  .terminal-body :global(.str) { color: #c9b568; }
  .terminal-body :global(.dim) { color: #707070; }
  .terminal-body :global(.ok) { color: #5cb870; }
  .terminal-body :global(.bad) { color: #e06058; }
  .terminal-body :global(.hl) { color: var(--text-code); font-weight: 500; }
</style>
