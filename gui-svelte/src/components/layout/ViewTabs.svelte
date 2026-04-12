<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte";

  const dispatch = createEventDispatcher<{ "view-change": { view: string } }>();

  export let activeView = "mission";
  export let allowedViews: string[] | null = null; // null = all allowed

  const VIEWS: { id: string; label: string; key: string }[] = [
    { id: "helm",        label: "HELM",        key: "1" },
    { id: "tactical",    label: "TACTICAL",    key: "2" },
    { id: "engineering", label: "ENGINEERING", key: "3" },
    { id: "ops",         label: "OPS",         key: "4" },
    { id: "science",     label: "SCIENCE",     key: "5" },
    { id: "comms",       label: "COMMS",       key: "6" },
    { id: "fleet",       label: "FLEET",       key: "7" },
    { id: "mission",     label: "MISSION",     key: "8" },
    { id: "editor",      label: "EDITOR",      key: "9" },
  ];

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
    // Ignore if focus is in an input
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    const idx = parseInt(e.key, 10);
    if (idx >= 1 && idx <= VIEWS.length) {
      const view = VIEWS[idx - 1];
      if (isAllowed(view.id)) selectView(view.id);
    }
  }

  onMount(() => document.addEventListener("keydown", onKeydown));
  onDestroy(() => document.removeEventListener("keydown", onKeydown));
</script>

<div class="view-tabs" role="tablist" aria-label="Station views">
  {#each VIEWS as v}
    {@const allowed = isAllowed(v.id)}
    <button
      class="tab-btn"
      class:active={activeView === v.id}
      class:disabled={!allowed}
      role="tab"
      aria-selected={activeView === v.id}
      aria-disabled={!allowed}
      tabindex={!allowed ? -1 : 0}
      title="{v.label} [{v.key}]{!allowed ? ' — not available at this station' : ''}"
      on:click={() => selectView(v.id)}
    >
      <span class="tab-key">{v.key}</span>
      <span class="tab-label">{v.label}</span>
    </button>
  {/each}
</div>

<style>
  .view-tabs {
    display: flex;
    align-items: stretch;
    gap: 2px;
    padding: 0 var(--space-xs);
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
    height: 36px;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .view-tabs::-webkit-scrollbar { display: none; }

  .tab-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 0 10px;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    letter-spacing: 0.5px;
    cursor: pointer;
    white-space: nowrap;
    transition: color var(--transition-fast), border-color var(--transition-fast);
    min-height: unset;
  }

  .tab-btn:hover:not(.disabled):not(.active) {
    color: var(--text-primary);
    background: var(--bg-hover);
  }

  .tab-btn.active {
    color: var(--tier-accent, var(--hud-primary));
    border-bottom-color: var(--tier-accent, var(--hud-primary));
    background: rgba(var(--tier-accent-rgb, 68, 136, 255), 0.05);
  }

  .tab-btn.disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .tab-key {
    font-size: 0.6rem;
    color: var(--text-dim);
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 2px;
    padding: 0 3px;
    min-width: 14px;
    text-align: center;
    font-family: var(--font-mono);
  }

  .tab-btn.active .tab-key {
    color: var(--tier-accent, var(--hud-primary));
    border-color: var(--tier-accent, var(--hud-primary));
  }

  .tab-label {
    font-size: 0.7rem;
  }

  @media (max-width: 600px) {
    .tab-label { display: none; }
    .tab-key { display: block; }
  }
</style>
