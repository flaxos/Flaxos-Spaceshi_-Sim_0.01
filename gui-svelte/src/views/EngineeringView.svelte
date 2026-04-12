<script lang="ts">
  import { tier } from "../lib/stores/tier.js";

  import ThermalDisplay from "../components/engineering/ThermalDisplay.svelte";
  import EngineeringControlPanel from "../components/engineering/EngineeringControlPanel.svelte";
  import SubsystemStatus from "../components/engineering/SubsystemStatus.svelte";
  import PowerDrawDisplay from "../components/engineering/PowerDrawDisplay.svelte";
  import PowerAllocationPanel from "../components/engineering/PowerAllocationPanel.svelte";
  import SystemToggles from "../components/engineering/SystemToggles.svelte";

  import EventLog from "../components/shared/EventLog.svelte";
  import ReactorBalanceGame from "../components/games/ReactorBalanceGame.svelte";
  import RadiatorDeployGame from "../components/games/RadiatorDeployGame.svelte";

  $: manualTier = $tier === "manual";
  $: rawTier = $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  const ENGINEERING_EVENT_FILTER = [
    "reactor",
    "drive",
    "radiator",
    "vent",
    "thermal",
    "power",
    "subsystem",
    "repair",
    "cascade",
    "engineering_proposal",
  ];
</script>

<div class="engineering-root" class:arcade={arcadeTier} class:manual={manualTier} class:cpu={cpuAssistTier}>
  <section class="column thermal">
    <div class="column-title">Thermal &amp; Drive</div>
    <ThermalDisplay />
    {#if arcadeTier}
      <ReactorBalanceGame />
      <RadiatorDeployGame />
    {/if}
    <EngineeringControlPanel />
  </section>

  <section class="column power">
    <div class="column-title">Power</div>
    <PowerDrawDisplay />
    <PowerAllocationPanel />
  </section>

  <section class="column systems">
    <div class="column-title">Systems</div>
    <SubsystemStatus />
    <SystemToggles />
  </section>

  <section class="column monitoring">
    <div class="column-title">Monitoring</div>
    <EventLog title="Engineering Log" domain="power" filter={ENGINEERING_EVENT_FILTER} priority={cpuAssistTier ? "primary" : "secondary"} />
  </section>
</div>

<style>
  .engineering-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: minmax(340px, 1.2fr) minmax(290px, 1fr) minmax(280px, 0.95fr) minmax(280px, 0.95fr);
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
  }

  .engineering-root.arcade {
    grid-template-columns: minmax(360px, 1.35fr) minmax(260px, 0.9fr) minmax(250px, 0.85fr) minmax(250px, 0.85fr);
  }

  .engineering-root.cpu {
    grid-template-columns: minmax(360px, 1.25fr) minmax(280px, 0.95fr) minmax(260px, 0.9fr) minmax(280px, 0.95fr);
  }

  .engineering-root.manual {
    grid-template-columns: minmax(360px, 1.25fr) minmax(320px, 1fr) minmax(280px, 0.95fr) minmax(280px, 0.95fr);
  }

  .column {
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    padding-right: 2px;
  }

  .column-title {
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

  @media (max-width: 1420px) {
    .engineering-root,
    .engineering-root.arcade,
    .engineering-root.cpu,
    .engineering-root.manual {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-auto-rows: minmax(0, 1fr);
    }
  }

  @media (max-width: 860px) {
    .engineering-root,
    .engineering-root.arcade,
    .engineering-root.cpu,
    .engineering-root.manual {
      grid-template-columns: 1fr;
      height: auto;
      overflow: auto;
    }

    .column {
      overflow: visible;
    }
  }
</style>
