<script lang="ts">
  export let title = "";
  export let priority: "primary" | "secondary" | "tertiary" = "secondary";
  export let domain: "nav" | "sensor" | "weapons" | "power" | "comms" | "helm" | "" = "";
  export let collapsible = true;
  export let disabled = false;
  export let disabledReason = "";
  export let className = "";

  let collapsed = false;
  let el: HTMLElement;

  function toggle() {
    if (collapsible) collapsed = !collapsed;
  }

  const DOMAIN_COLORS: Record<string, string> = {
    nav:     "var(--domain-nav)",
    sensor:  "var(--domain-sensor)",
    weapons: "var(--domain-weapons)",
    power:   "var(--domain-power)",
    comms:   "var(--domain-comms)",
    helm:    "var(--domain-helm)",
  };

  $: accentColor = domain ? (DOMAIN_COLORS[domain] ?? "var(--border-default)") : "var(--border-default)";
</script>

<div
  bind:this={el}
  class="panel panel-priority-{priority} {className}"
  class:collapsed
  class:disabled
  style="--panel-accent: {accentColor}"
  data-priority={priority}
  data-domain={domain || undefined}
>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="panel-header" on:click={toggle} role={collapsible ? "button" : undefined} tabindex={collapsible ? 0 : undefined} on:keydown={(e) => e.key === "Enter" && toggle()}>
    <span class="panel-title">{title}</span>
    {#if collapsible}
      <span class="panel-toggle" aria-hidden="true">{collapsed ? "▸" : "▾"}</span>
    {/if}
  </div>

  {#if !collapsed}
    <div class="panel-body">
      <slot />
      {#if disabled}
        <div class="disabled-overlay" title={disabledReason}>
          {#if disabledReason}
            <span class="disabled-reason">{disabledReason}</span>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    background: var(--bg-panel);
    border: 1px solid var(--border-default);
    border-left: 3px solid var(--panel-accent);
    border-radius: var(--radius-sm);
    overflow: hidden;
    min-width: 0;
    position: relative;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.36);
  }

  .panel::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--panel-accent);
    opacity: 0.45;
    pointer-events: none;
    z-index: 1;
  }

  .panel-priority-primary {
    background: var(--bg-raised);
    border-color: var(--border-active);
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.52);
  }

  .panel-priority-tertiary {
    background: color-mix(in srgb, var(--bg-panel) 82%, var(--bg-void));
  }

  .panel.disabled::after {
    content: "";
    position: absolute;
    inset: 0;
    background:
      linear-gradient(180deg, rgba(0, 0, 0, 0.08), rgba(0, 0, 0, 0.24)),
      rgba(10, 10, 15, 0.28);
    pointer-events: none;
  }

  .panel.disabled {
    opacity: 0.65;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 28px;
    padding: 6px 10px 5px;
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.03) 0%, rgba(255, 255, 255, 0.008) 100%),
      var(--bg-glass);
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
    user-select: none;
    gap: 8px;
    position: relative;
    z-index: 2;
  }

  .panel-header[role="button"] {
    cursor: pointer;
  }

  .panel-header[role="button"]:hover {
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.012) 100%),
      var(--bg-hover);
  }

  .panel-title {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: color-mix(in srgb, var(--panel-accent) 78%, var(--text-secondary));
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .panel-priority-primary .panel-title {
    color: color-mix(in srgb, var(--panel-accent) 55%, var(--text-bright));
  }

  .panel-toggle {
    font-size: 0.62rem;
    color: var(--text-dim);
    transition: transform var(--transition-fast);
  }

  .panel.collapsed .panel-toggle {
    transform: rotate(-90deg);
  }

  .panel-body {
    flex: 1;
    overflow: auto;
    position: relative;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.008), transparent 18%);
  }

  .disabled-overlay {
    position: absolute;
    inset: 0;
    background: rgba(10, 10, 15, 0.64);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: not-allowed;
    z-index: 3;
  }

  .disabled-reason {
    font-size: var(--font-size-xs);
    color: var(--text-dim);
    font-family: var(--font-mono);
    text-align: center;
    padding: var(--space-sm);
  }

  .panel.collapsed {
    flex: none;
  }
</style>
