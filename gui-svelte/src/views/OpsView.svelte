<script lang="ts">
  import { tier } from "../lib/stores/tier.js";

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

  $: manualTier = $tier === "manual";
  $: rawTier = $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";
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
