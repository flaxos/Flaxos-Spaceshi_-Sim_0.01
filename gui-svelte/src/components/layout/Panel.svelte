<script lang="ts">
  import { onMount } from "svelte";

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
  }

  .panel.disabled {
    opacity: 0.65;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 5px 10px;
    background: var(--bg-glass);
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
    user-select: none;
  }

  .panel-header[role="button"] {
    cursor: pointer;
  }

  .panel-header[role="button"]:hover {
    background: var(--bg-hover);
  }

  .panel-title {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-secondary);
  }

  .panel-priority-primary .panel-title {
    color: var(--text-primary);
  }

  .panel-toggle {
    font-size: 0.65rem;
    color: var(--text-dim);
    transition: transform var(--transition-fast);
  }

  .panel-body {
    flex: 1;
    overflow: auto;
    position: relative;
  }

  .disabled-overlay {
    position: absolute;
    inset: 0;
    background: rgba(10, 10, 15, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: not-allowed;
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
