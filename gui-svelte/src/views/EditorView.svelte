<script lang="ts">
  import ShipEditor from "../components/editor/ShipEditor.svelte";
  import ScenarioEditor from "../components/editor/ScenarioEditor.svelte";

  let activeTab: "ships" | "scenarios" = "ships";
</script>

<div class="editor-root">
  <div class="editor-tab-bar">
    <button
      class="editor-tab"
      class:active={activeTab === "ships"}
      type="button"
      on:click={() => (activeTab = "ships")}
    >
      SHIPS
    </button>
    <button
      class="editor-tab"
      class:active={activeTab === "scenarios"}
      type="button"
      on:click={() => (activeTab = "scenarios")}
    >
      SCENARIOS
    </button>
  </div>

  <div class="editor-content">
    {#if activeTab === "ships"}
      <ShipEditor />
    {:else}
      <ScenarioEditor />
    {/if}
  </div>
</div>

<style>
  .editor-root {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    overflow: hidden;
  }

  .editor-tab-bar {
    flex-shrink: 0;
    display: flex;
    align-items: stretch;
    gap: 2px;
    padding: 0 var(--space-xs);
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border-default);
    height: 36px;
  }

  .editor-tab {
    display: flex;
    align-items: center;
    padding: 0 14px;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    cursor: pointer;
    transition: color 0.12s, border-color 0.12s;
  }

  .editor-tab:hover:not(.active) {
    color: var(--text-secondary);
    background: var(--bg-hover);
  }

  .editor-tab.active {
    color: var(--tier-accent, var(--hud-primary));
    border-bottom-color: var(--tier-accent, var(--hud-primary));
  }

  .editor-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
</style>
