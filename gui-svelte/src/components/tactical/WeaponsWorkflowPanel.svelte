<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedLauncherType } from "../../lib/stores/tacticalUi.js";
  import {
    asRecord,
    extractShipState,
    getCombatState,
    getTargetingSummary,
    toStringValue,
  } from "./tacticalData.js";
  import WeaponMountList from "./WeaponMountList.svelte";
  import LauncherControl from "./LauncherControl.svelte";
  import PdcControl from "./PdcControl.svelte";
  import MunitionProgrammingPanel from "../games/MunitionProgrammingPanel.svelte";

  type WorkflowTab = "mounts" | "launch" | "program" | "pdc";

  let activeTab: WorkflowTab = "mounts";

  $: ship = extractShipState($gameState);
  $: combat = getCombatState(ship);
  $: targeting = getTargetingSummary(ship);
  $: munitionProgram = asRecord(combat.munition_program) ?? {};
  $: hasProgram = Object.keys(munitionProgram).length > 0;
  $: programType = toStringValue(munitionProgram.munition_type);
</script>

<Panel title="Weapons" domain="weapons" priority="primary" className="weapons-workflow-panel">
  <div class="shell">
    <div class="workflow-header">
      <div class="status-card">
        <span>Targeting</span>
        <strong>{targeting.lockState.toUpperCase()}</strong>
      </div>
      <div class="status-card">
        <span>Launcher</span>
        <strong>{$selectedLauncherType.toUpperCase()}</strong>
      </div>
      <div class="status-card" class:armed={hasProgram}>
        <span>Program</span>
        <strong>{hasProgram ? programType.toUpperCase() : "DEFAULT"}</strong>
      </div>
    </div>

    <div class="workflow-tabs">
      <button class:active={activeTab === "mounts"} type="button" on:click={() => (activeTab = "mounts")}>Mounts</button>
      <button class:active={activeTab === "launch"} type="button" on:click={() => (activeTab = "launch")}>Launch</button>
      <button class:active={activeTab === "program"} type="button" on:click={() => (activeTab = "program")}>Program</button>
      <button class:active={activeTab === "pdc"} type="button" on:click={() => (activeTab = "pdc")}>PDC</button>
    </div>

    <div class="workflow-body">
      {#if activeTab === "mounts"}
        <WeaponMountList />
      {:else if activeTab === "launch"}
        <LauncherControl embedded />
      {:else if activeTab === "program"}
        <MunitionProgrammingPanel embedded />
      {:else}
        <PdcControl embedded />
      {/if}
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    gap: var(--space-sm);
    height: 100%;
    padding: var(--space-sm);
  }

  .workflow-header {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .status-card {
    display: grid;
    gap: 4px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
  }

  .status-card.armed {
    border-color: rgba(var(--tier-accent-rgb), 0.35);
    background: rgba(var(--tier-accent-rgb), 0.08);
  }

  .status-card span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .status-card strong {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.05em;
  }

  .workflow-tabs {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 6px;
  }

  .workflow-tabs button.active {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
    color: var(--text-primary);
  }

  .workflow-body {
    min-height: 0;
    overflow: auto;
  }

  @media (max-width: 720px) {
    .workflow-header,
    .workflow-tabs {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
