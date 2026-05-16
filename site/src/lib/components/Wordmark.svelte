<script lang="ts">
  type Kind = 'claude-code' | 'claude-voice' | 'reminders' | 'beads' | 'rbridge';
  let { kind, size = 18 }: { kind: Kind; size?: number } = $props();

  const presets: Record<Kind, { label: string; icon: string }> = {
    'claude-code': {
      label: 'Claude Code',
      icon: 'M4 4h16v3H4zM4 9h10v3H4zM4 14h16v3H4zM4 19h7v2H4z'
    },
    'claude-voice': {
      label: 'Claude Voice',
      icon: 'M12 2a3 3 0 0 1 3 3v6a3 3 0 1 1-6 0V5a3 3 0 0 1 3-3zm-7 9a7 7 0 0 0 14 0M12 18v3'
    },
    'reminders': {
      label: 'Reminders',
      icon: 'M6 3h12v18l-6-3-6 3zM9 8h6M9 12h6'
    },
    'beads': {
      label: 'Beads',
      icon: 'M5 12a3 3 0 1 1 6 0M11 12h2M13 12a3 3 0 1 1 6 0'
    },
    'rbridge': {
      label: 'rbridge',
      icon: 'M3 12c0-3 3-5 6-5h6c3 0 6 2 6 5s-3 5-6 5H9'
    }
  };

  let label = $derived(presets[kind].label);
  let icon = $derived(presets[kind].icon);
</script>

<span class="wm" style="--wm-size: {size}px">
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d={icon} />
  </svg>
  <span class="wm-label">{label}</span>
</span>

<style>
  .wm {
    display: inline-flex;
    align-items: center;
    gap: 0.35em;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: calc(var(--wm-size) * 0.78);
    font-weight: 500;
    white-space: nowrap;
    line-height: 1;
    vertical-align: -0.18em;
  }
  .wm svg { flex-shrink: 0; opacity: 0.85; }
  .wm-label { letter-spacing: -0.01em; }
</style>
