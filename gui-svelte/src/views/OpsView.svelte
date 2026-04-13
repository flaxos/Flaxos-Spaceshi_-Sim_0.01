<script lang="ts">
  import { tier } from "../lib/stores/tier.js";
  import { wsClient } from "../lib/ws/wsClient.js";
  import { proposals, autoSystems } from "../lib/stores/proposals.js";

  import ShipStatus from "../components/ops/ShipStatus.svelte";
  import OpsControlPanel from "../components/ops/OpsControlPanel.svelte";
  import PowerProfileSelector from "../components/ops/PowerProfileSelector.svelte";
  import CrewPanel from "../components/ops/CrewPanel.svelte";
  import CrewRosterPanel from "../components/ops/CrewRosterPanel.svelte";
  import CrewFatigueDisplay from "../components/ops/CrewFatigueDisplay.svelte";
  import BoardingPanel from "../components/ops/BoardingPanel.svelte";
  import DroneControlPanel from "../components/ops/DroneControlPanel.svelte";

  import SubsystemStatus from "../components/engineering/SubsystemStatus.svelte";
  import DamageControlGame from "../components/games/DamageControlGame.svelte";
  import ProposalQueue from "../components/shared/ProposalQueue.svelte";

  $: manualTier = $tier === "manual";
  $: rawTier = $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  async function toggleAutoOps() {
    await wsClient.sendShipCommand(
      $autoSystems.ops.enabled ? "disable_auto_ops" : "enable_auto_ops",
      {}
    );
  }

  async function setOpsMode(mode: string) {
    await wsClient.sendShipCommand("set_ops_mode", { mode });
  }
</script>

<div class="ops-root" class:arcade={arcadeTier} class:manual={manualTier} class:cpu={cpuAssistTier}>
  <section class="group damage">
    <div class="group-title">Damage Control</div>
    <ShipStatus />
    <SubsystemStatus />
    {#if arcadeTier}
      <DamageControlGame />
    {/if}
    <OpsControlPanel />
    {#if cpuAssistTier}
      <div class="cpu-ops-panel">
        <button
          class="auto-toggle"
          class:active={$autoSystems.ops.enabled}
          type="button"
          on:click={toggleAutoOps}
        >
          AUTO-OPS: {$autoSystems.ops.enabled ? "ENABLED" : "DISABLED"}
        </button>
        <div class="mode-row">
          {#each ["auto", "manual"] as m}
            <button
              class:selected={$autoSystems.ops.mode === m}
              type="button"
              on:click={() => setOpsMode(m)}
            >
              {m.toUpperCase()}
            </button>
          {/each}
        </div>
        <ProposalQueue proposals={$proposals.ops} station="ops" />
      </div>
    {/if}
  </section>

  <section class="group power">
    <div class="group-title">Power</div>
    <PowerProfileSelector />
  </section>

  <section class="group crew">
    <div class="group-title">Crew</div>
    <CrewFatigueDisplay />
    <CrewPanel />
    {#if manualTier || rawTier}
      <CrewRosterPanel />
    {/if}
  </section>

  <section class="group boarding">
    <div class="group-title">Boarding</div>
    <BoardingPanel />
  </section>

  <section class="group drones">
    <div class="group-title">Drones</div>
    <DroneControlPanel />
  </section>
</div>

<style>
  .ops-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: minmax(320px, 1.2fr) minmax(260px, 0.85fr) minmax(300px, 1.05fr) minmax(260px, 0.9fr) minmax(260px, 0.9fr);
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
  }

  .ops-root.arcade {
    grid-template-columns: minmax(340px, 1.3fr) minmax(240px, 0.8fr) minmax(280px, 1fr) minmax(250px, 0.85fr) minmax(250px, 0.85fr);
  }

  .ops-root.cpu {
    grid-template-columns: minmax(330px, 1.2fr) minmax(250px, 0.85fr) minmax(300px, 1fr) minmax(250px, 0.85fr) minmax(250px, 0.85fr);
  }

  .group {
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    padding-right: 2px;
  }

  .group-title {
    position: sticky;
    top: 0;
    z-index: 2;
    padding: 6px 10px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.12), transparent 60%), var(--bg-panel);
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-secondary);
  }

  .cpu-ops-panel {
    display: grid;
    gap: var(--space-sm);
  }

  .auto-toggle {
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }

  .auto-toggle.active {
    border-color: rgba(var(--tier-accent-rgb), 0.6);
    background: rgba(var(--tier-accent-rgb), 0.12);
    color: var(--text-primary);
  }

  .mode-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-sm);
  }

  .mode-row button {
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    color: var(--text-secondary);
    transition: background 0.1s, border-color 0.1s, color 0.1s;
  }

  .mode-row button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
    color: var(--text-primary);
  }

  @media (max-width: 1500px) {
    .ops-root,
    .ops-root.arcade,
    .ops-root.cpu {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      grid-auto-rows: minmax(0, 1fr);
    }
  }

  @media (max-width: 1080px) {
    .ops-root,
    .ops-root.arcade,
    .ops-root.cpu {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      height: auto;
      overflow: auto;
    }

    .group {
      overflow: visible;
    }
  }

  @media (max-width: 760px) {
    .ops-root,
    .ops-root.arcade,
    .ops-root.cpu {
      grid-template-columns: 1fr;
    }
  }
</style>
