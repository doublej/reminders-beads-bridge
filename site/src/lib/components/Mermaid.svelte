<script lang="ts">
  import { onMount } from 'svelte';

  let { code, caption = '' }: { code: string; caption?: string } = $props();

  let host: HTMLDivElement;
  let figure: HTMLElement;
  let wide = $state(false);
  let id = `m${Math.random().toString(36).slice(2, 9)}`;

  onMount(async () => {
    const { default: mermaid } = await import('mermaid');
    mermaid.initialize({
      startOnLoad: false,
      theme: 'base',
      themeVariables: {
        fontFamily: "'DM Mono', ui-monospace, Menlo, monospace",
        fontSize: '13px',
        background: '#fefefe',
        primaryColor: '#fefefe',
        primaryTextColor: '#2a2a2a',
        primaryBorderColor: '#d0d0d0',
        secondaryColor: '#f8f8f8',
        tertiaryColor: '#fefefe',
        lineColor: '#777',
        textColor: '#555',
        mainBkg: '#fefefe',
        secondBkg: '#f8f8f8',
        clusterBkg: '#f8f8f8',
        clusterBorder: '#e2e2e2',
        edgeLabelBackground: '#fefefe',
        nodeBorder: '#d0d0d0',
        defaultLinkColor: '#777',
        actorBkg: '#fefefe',
        actorBorder: '#d0d0d0',
        actorTextColor: '#2a2a2a',
        actorLineColor: '#777',
        signalColor: '#555',
        signalTextColor: '#2a2a2a',
        labelBoxBkgColor: '#f8f8f8',
        labelBoxBorderColor: '#d0d0d0',
        labelTextColor: '#2a2a2a',
        noteBkgColor: '#f8f8f8',
        noteBorderColor: '#d0d0d0',
        noteTextColor: '#555',
        sequenceNumberColor: '#2266cc'
      },
      flowchart: { htmlLabels: true, curve: 'basis', padding: 12, useMaxWidth: false },
      sequence: { mirrorActors: false, showSequenceNumbers: false, useMaxWidth: false },
      state: { useMaxWidth: false }
    });
    try {
      const { svg } = await mermaid.render(id, code);
      host.innerHTML = svg;
      requestAnimationFrame(() => measure());
    } catch (e) {
      host.innerHTML = `<pre style="background:#fbeaec;color:#a23241;padding:12px;border-radius:6px;white-space:pre-wrap">mermaid error\n${String(e)}</pre>`;
    }
  });

  function measure() {
    const svg = host.querySelector('svg');
    if (!svg || !figure) return;
    const vb = svg.viewBox?.baseVal;
    const natural = (vb && vb.width) || svg.getBoundingClientRect().width || 0;
    // figure is inside main (max 880px). If natural diagram is wider, let it spill.
    const containerWidth = figure.parentElement?.getBoundingClientRect().width ?? 880;
    wide = natural > containerWidth + 8;
    svg.removeAttribute('width');
    svg.removeAttribute('height');
    svg.style.width = wide ? `${natural}px` : 'auto';
    svg.style.maxWidth = wide ? 'none' : '100%';
    svg.style.height = 'auto';
  }
</script>

<figure
  bind:this={figure}
  class="mermaid-figure"
  class:wide
  aria-label={caption || 'diagram'}
>
  <div class="mermaid-scroll">
    <div class="mermaid-host" bind:this={host}></div>
  </div>
  {#if caption}<figcaption>{caption}</figcaption>{/if}
</figure>

<style>
  .mermaid-figure {
    margin: 1.8em 0;
    padding: 20px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
  }
  .mermaid-figure.wide {
    /* break out of main column when the diagram is wider than the container */
    margin-left: calc(-1 * max(0px, (100vw - var(--container-max-width)) / 2));
    margin-right: calc(-1 * max(0px, (100vw - var(--container-max-width)) / 2));
    border-radius: 0;
    border-left: 0;
    border-right: 0;
  }
  .mermaid-scroll {
    overflow-x: auto;
    overflow-y: hidden;
  }
  .mermaid-figure.wide .mermaid-scroll {
    padding: 0 24px;
  }
  .mermaid-host {
    display: inline-block;
    min-width: 100%;
    text-align: center;
  }
  .mermaid-host :global(svg) {
    display: inline-block;
    vertical-align: top;
  }
</style>
