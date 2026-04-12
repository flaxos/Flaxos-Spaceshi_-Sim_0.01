<script lang="ts">
  import { tier, type Tier } from "../../lib/stores/tier.js";
  import { onMount, onDestroy } from "svelte";

  const TIERS: { id: Tier; label: string }[] = [
    { id: "manual",     label: "MANUAL" },
    { id: "raw",        label: "RAW" },
    { id: "arcade",     label: "ARCADE" },
    { id: "cpu-assist", label: "CPU ASSIST" },
  ];

  function select(t: Tier) {
    tier.set(t);
  }

  // Listen for tutorial-tier-request events (mirrors original TierSelector)
  function onTutorialTier(e: Event) {
    const t = (e as CustomEvent<{ tier: Tier }>).detail?.tier;
    if (t) tier.set(t);
  }

  onMount(() => document.addEventListener("tutorial-tier-request", onTutorialTier));
  onDestroy(() => document.removeEventListener("tutorial-tier-request", onTutorialTier));
</script>

<div class="tier-group" role="group" aria-label="Control tier">
  {#each TIERS as t}
    <button
      class="tier-btn"
      class:active={$tier === t.id}
      data-tier={t.id}
      aria-pressed={$tier === t.id}
      title="{t.label} control tier"
      on:click={() => select(t.id)}
    >{t.label}</button>
  {/each}
</div>

<style>
  .tier-group {
    display: flex;
    gap: 1px;
    background: var(--border-default);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    overflow: hidden;
    user-select: none;
  }

  .tier-btn {
    padding: 5px 12px;
    background: var(--bg-panel);
    border: none;
    border-radius: 0;
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    cursor: pointer;
    position: relative;
    transition: background var(--transition-fast), color var(--transition-fast);
    min-height: unset;
  }

  .tier-btn:hover:not(.active) {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  /* MANUAL: amber */
  .tier-btn[data-tier="manual"].active {
    background: rgba(255, 136, 0, 0.08);
    color: #ff8800;
    box-shadow: inset 0 0 12px rgba(255, 136, 0, 0.1);
  }

  /* RAW: green */
  .tier-btn[data-tier="raw"].active {
    background: rgba(0, 255, 136, 0.08);
    color: var(--status-nominal);
    box-shadow: inset 0 0 12px rgba(0, 255, 136, 0.1);
  }

  /* ARCADE: blue */
  .tier-btn[data-tier="arcade"].active {
    background: rgba(74, 158, 255, 0.1);
    color: var(--hud-primary);
    box-shadow: inset 0 0 12px rgba(74, 158, 255, 0.12);
  }

  /* CPU ASSIST: white/purple */
  .tier-btn[data-tier="cpu-assist"].active {
    background: rgba(192, 160, 255, 0.08);
    color: #c0a0ff;
  }

  /* Active indicator bar */
  .tier-btn.active::after {
    content: "";
    position: absolute;
    bottom: 0;
    left: 20%;
    right: 20%;
    height: 2px;
    border-radius: 1px;
  }

  .tier-btn[data-tier="manual"].active::after { background: #ff8800; box-shadow: 0 0 4px #ff8800; }
  .tier-btn[data-tier="raw"].active::after     { background: var(--status-nominal); box-shadow: 0 0 4px var(--status-nominal); }
  .tier-btn[data-tier="arcade"].active::after  { background: var(--hud-primary); box-shadow: 0 0 4px var(--hud-primary); }
  .tier-btn[data-tier="cpu-assist"].active::after { background: #c0a0ff; }
</style>
