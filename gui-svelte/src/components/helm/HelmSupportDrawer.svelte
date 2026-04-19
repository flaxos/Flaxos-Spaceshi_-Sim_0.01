<script lang="ts">
  import { tier } from "../../lib/stores/tier.js";

  import HelmNavigationPanel from "./HelmNavigationPanel.svelte";
  import ManualFlightPanel from "./ManualFlightPanel.svelte";
  import ShipOrientationDisplay from "./ShipOrientationDisplay.svelte";
  import RcsControls from "./RcsControls.svelte";
  import RcsThrusterDisplay from "./RcsThrusterDisplay.svelte";
  import HelmQueuePanel from "./HelmQueuePanel.svelte";
  import DockingPanel from "./DockingPanel.svelte";
  import ManeuverPlanner from "./ManeuverPlanner.svelte";
  import AutopilotStatus from "./AutopilotStatus.svelte";
  import HelmBalanceGame from "../games/HelmBalanceGame.svelte";

  type DrawerTab = "nav" | "manual" | "systems" | "arcade" | null;

  let activeTab: DrawerTab = null;

  $: arcadeTier = $tier === "arcade";

  function toggle(tab: Exclude<DrawerTab, null>) {
    activeTab = activeTab === tab ? null : tab;
  }
</script>

<div class="support-drawer">
  <div class="toolbar">
    <button class:active={activeTab === "nav"} type="button" on:click={() => toggle("nav")}>Nav Tools</button>
    <button class:active={activeTab === "manual"} type="button" on:click={() => toggle("manual")}>Manual</button>
    <button class:active={activeTab === "systems"} type="button" on:click={() => toggle("systems")}>Systems</button>
    {#if arcadeTier}
      <button class:active={activeTab === "arcade"} type="button" on:click={() => toggle("arcade")}>Arcade</button>
    {/if}
  </div>

  {#if activeTab !== null}
    <div class="drawer-body">
      {#if activeTab === "nav"}
        <HelmNavigationPanel />
        <DockingPanel />
      {:else if activeTab === "manual"}
        <ManualFlightPanel />
        <RcsControls />
        <ManeuverPlanner />
      {:else if activeTab === "systems"}
        <AutopilotStatus />
        <HelmQueuePanel />
        <ShipOrientationDisplay />
        <RcsThrusterDisplay />
      {:else if activeTab === "arcade"}
        <HelmBalanceGame />
      {/if}
    </div>
  {/if}
</div>

<style>
  .support-drawer {
    display: grid;
    gap: var(--space-xs);
  }

  .toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding-top: var(--space-xs);
    border-top: 1px solid var(--bd-subtle);
  }

  .toolbar button.active {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
    color: var(--text-primary);
  }

  .drawer-body {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: var(--space-xs);
    overflow: auto;
    max-height: 360px;
    padding-bottom: var(--space-xs);
  }
</style>
