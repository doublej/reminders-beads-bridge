<script lang="ts">
  import { onMount } from 'svelte';

  let { code, caption = '' }: { code: string; caption?: string } = $props();

  let host: HTMLDivElement;
  let id = `m${Math.random().toString(36).slice(2, 9)}`;

  onMount(async () => {
    const { default: mermaid } = await import('mermaid');
    mermaid.initialize({
      startOnLoad: false,
      theme: 'base',
      themeVariables: {
        fontFamily: "'DM Mono', ui-monospace, Menlo, monospace",
        fontSize: '13px',
        background: '#ffffff',
        primaryColor: '#ffffff',
        primaryTextColor: '#1a1a1a',
        primaryBorderColor: '#d0d0d0',
        secondaryColor: '#f5f5f5',
        tertiaryColor: '#fafafa',
        lineColor: '#606060',
        textColor: '#404040',
        mainBkg: '#ffffff',
        secondBkg: '#f5f5f5',
        clusterBkg: '#fafafa',
        clusterBorder: '#e0e0e0',
        edgeLabelBackground: '#ffffff',
        nodeBorder: '#d0d0d0',
        defaultLinkColor: '#606060',
        actorBkg: '#ffffff',
        actorBorder: '#d0d0d0',
        actorTextColor: '#1a1a1a',
        actorLineColor: '#606060',
        signalColor: '#404040',
        signalTextColor: '#1a1a1a',
        labelBoxBkgColor: '#fafafa',
        labelBoxBorderColor: '#d0d0d0',
        labelTextColor: '#1a1a1a',
        noteBkgColor: '#f5f5f5',
        noteBorderColor: '#d0d0d0',
        noteTextColor: '#404040',
        sequenceNumberColor: '#1a1a1a'
      },
      flowchart: { htmlLabels: true, curve: 'basis', padding: 12 },
      sequence: { mirrorActors: false, showSequenceNumbers: false, useMaxWidth: true }
    });
    try {
      const { svg } = await mermaid.render(id, code);
      host.innerHTML = svg;
    } catch (e) {
      host.innerHTML = `<pre style="color:#b91c1c">mermaid error\n${String(e)}</pre>`;
    }
  });
</script>

<figure class="mermaid-figure">
  <div class="mermaid-host" bind:this={host}></div>
  {#if caption}<figcaption>{caption}</figcaption>{/if}
</figure>

<style>
  .mermaid-figure {
    margin: 1.8em 0;
    padding: 24px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow-x: auto;
  }
  .mermaid-host :global(svg) {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
  }
</style>
