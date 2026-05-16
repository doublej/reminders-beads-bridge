<script lang="ts">
  import { onMount } from 'svelte';

  let { code, caption = '' }: { code: string; caption?: string } = $props();

  let host: HTMLDivElement;
  let id = `m${Math.random().toString(36).slice(2, 9)}`;

  onMount(async () => {
    const { default: mermaid } = await import('mermaid');
    const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    mermaid.initialize({
      startOnLoad: false,
      theme: dark ? 'dark' : 'neutral',
      themeVariables: {
        fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
        fontSize: '14px',
        primaryColor: dark ? '#1c2027' : '#ffffff',
        primaryTextColor: dark ? '#e6e8eb' : '#1a1d21',
        primaryBorderColor: dark ? '#2a2f38' : '#d9dde3',
        lineColor: dark ? '#98a0aa' : '#5b626c'
      },
      flowchart: { htmlLabels: true, curve: 'basis' },
      sequence: { mirrorActors: false, showSequenceNumbers: false }
    });
    try {
      const { svg } = await mermaid.render(id, code);
      host.innerHTML = svg;
    } catch (e) {
      host.innerHTML = `<pre style="color: var(--bad)">mermaid error\n${String(e)}</pre>`;
    }
  });
</script>

<figure class="mermaid-figure">
  <div class="mermaid-host" bind:this={host}></div>
  {#if caption}<figcaption>{caption}</figcaption>{/if}
</figure>

<style>
  .mermaid-figure {
    margin: 1.5em 0;
    padding: 1.2rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow-x: auto;
  }
  .mermaid-host :global(svg) {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
  }
</style>
