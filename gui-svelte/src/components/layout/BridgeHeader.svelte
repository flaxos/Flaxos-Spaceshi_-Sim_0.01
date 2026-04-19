<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import ConnectionStatus from "./ConnectionStatus.svelte";
  import StationSelector from "./StationSelector.svelte";
  import TierSelector from "./TierSelector.svelte";

  const dispatch = createEventDispatcher<{
    "view-change": { view: string };
    "station-claimed": { station: string };
    "station-released": { station: string };
  }>();

  export let activeView = "mission";
  export let allowedViews: string[] | null = null;

  const VIEWS: Array<{
    id: string;
    label: string;
    key: string;
    domain: "nav" | "helm" | "weapons" | "power" | "sensor" | "comms" | "ops" | "fleet";
  }> = [
    { id: "mission", label: "MISSION", key: "0", domain: "nav" },
    { id: "helm", label: "HELM", key: "1", domain: "helm" },
    { id: "tactical", label: "TACTICAL", key: "2", domain: "weapons" },
    { id: "engineering", label: "ENGINEERING", key: "3", domain: "power" },
    { id: "ops", label: "OPS", key: "4", domain: "ops" },
    { id: "science", label: "SCIENCE", key: "5", domain: "sensor" },
    { id: "comms", label: "COMMS", key: "6", domain: "comms" },
    { id: "fleet", label: "FLEET", key: "7", domain: "fleet" },
  ];

  const DOMAIN_VAR: Record<string, string> = {
    nav: "var(--domain-nav)",
    helm: "var(--domain-helm)",
    weapons: "var(--domain-weapons)",
    power: "var(--domain-power)",
    sensor: "var(--domain-sensor)",
    comms: "var(--domain-comms)",
    ops: "var(--domain-ops)",
    fleet: "var(--domain-fleet)",
  };

  function isAllowed(viewId: string): boolean {
    if (!allowedViews) return true;
    return allowedViews.includes(viewId);
  }

  function selectView(viewId: string) {
    if (!isAllowed(viewId)) return;
    activeView = viewId;
    dispatch("view-change", { view: viewId });
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;

    const target = e.target as HTMLElement | null;
    if (!target) return;
    const tag = target.tagName;
    if (
      tag === "INPUT"
      || tag === "TEXTAREA"
      || tag === "SELECT"
      || target.isContentEditable
      || target.closest("[contenteditable='true'], [role='textbox']")
    ) {
      return;
    }

    if (e.key === "0") {
      e.preventDefault();
      selectView("mission");
      return;
    }

    const idx = parseInt(e.key, 10);
    if (idx >= 1 && idx <= 7) {
      const view = VIEWS.find((entry) => entry.key === e.key);
      if (view && isAllowed(view.id)) {
        e.preventDefault();
        selectView(view.id);
      }
    }
  }
</script>

<svelte:window on:keydown={onKeydown} />

<div class="bridge-header">
  <div class="bridge-header__left">
    <ConnectionStatus />
  </div>

  <div class="bridge-header__nav" role="tablist" aria-label="Bridge stations and mission views">
    {#each VIEWS as view}
      {@const allowed = isAllowed(view.id)}
      <button
        class="nav-tab"
        class:active={activeView === view.id}
        class:disabled={!allowed}
        style="--tab-accent: {DOMAIN_VAR[view.domain]}"
        role="tab"
        aria-selected={activeView === view.id}
        aria-disabled={!allowed}
        tabindex={!allowed ? -1 : 0}
        title="{view.label} [{view.key}]{!allowed ? ' — unavailable at this station' : ''}"
        on:click={() => selectView(view.id)}
      >
        <span class="nav-tab__key">{view.key}</span>
        <span class="nav-tab__label">{view.label}</span>
      </button>
    {/each}
  </div>

  <div class="bridge-header__right">
    <StationSelector
      on:station-claimed={(event) => dispatch("station-claimed", event.detail)}
      on:station-released={(event) => dispatch("station-released", event.detail)}
    />
    <TierSelector />
  </div>
</div>

<style>
  .bridge-header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 8px;
    min-height: 36px;
    padding: 0 6px;
    background: var(--bg-raised);
    border-bottom: 1px solid var(--bd-default);
    position: relative;
    z-index: 100;
  }

  .bridge-header__left,
  .bridge-header__right {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .bridge-header__nav {
    display: flex;
    align-items: stretch;
    gap: 2px;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .bridge-header__nav::-webkit-scrollbar {
    display: none;
  }

  .nav-tab {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
    transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
  }

  .nav-tab:hover:not(.disabled):not(.active) {
    color: var(--tx-primary);
    background: rgba(255, 255, 255, 0.03);
  }

  .nav-tab.active {
    color: var(--tx-bright);
    border-bottom-color: var(--tier-accent);
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--tab-accent) 16%, transparent), transparent 80%),
      rgba(255, 255, 255, 0.02);
  }

  .nav-tab.disabled {
    opacity: 0.32;
    cursor: not-allowed;
  }

  .nav-tab__key {
    min-width: 15px;
    padding: 0 3px;
    border: 1px solid var(--bd-subtle);
    border-radius: 2px;
    background: var(--bg-input);
    color: var(--tx-dim);
    font-size: 0.58rem;
    text-align: center;
  }

  .nav-tab.active .nav-tab__key {
    color: var(--tab-accent);
    border-color: color-mix(in srgb, var(--tab-accent) 55%, var(--bd-active));
  }

  .nav-tab__label {
    line-height: 1;
  }

  @media (max-width: 980px) {
    .bridge-header {
      grid-template-columns: minmax(0, 1fr);
      gap: 6px;
      padding: 6px;
    }

    .bridge-header__left,
    .bridge-header__right {
      justify-content: space-between;
    }
  }

  @media (max-width: 640px) {
    .nav-tab__label {
      display: none;
    }

    .nav-tab {
      padding: 0 8px;
    }
  }
</style>
