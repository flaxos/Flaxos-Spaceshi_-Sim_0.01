<script lang="ts">
  import { tier } from "../lib/stores/tier.js";
  import { wsClient } from "../lib/ws/wsClient.js";
  import { proposals, autoSystems } from "../lib/stores/proposals.js";

  import ThermalDisplay from "../components/engineering/ThermalDisplay.svelte";
  import EngineeringControlPanel from "../components/engineering/EngineeringControlPanel.svelte";
  import SubsystemStatus from "../components/engineering/SubsystemStatus.svelte";
  import PowerDrawDisplay from "../components/engineering/PowerDrawDisplay.svelte";
  import PowerAllocationPanel from "../components/engineering/PowerAllocationPanel.svelte";
  import SystemToggles from "../components/engineering/SystemToggles.svelte";

  import EventLog from "../components/shared/EventLog.svelte";
  import ProposalQueue from "../components/shared/ProposalQueue.svelte";
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

  async function toggleAutoEngineering() {
    await wsClient.sendShipCommand(
      $autoSystems.engineering.enabled ? "disable_auto_engineering" : "enable_auto_engineering",
      {}
    );
  }
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

  {#if cpuAssistTier}
    <section class="column cpu-proposals">
      <div class="column-title">Auto-Engineering</div>
      <button
        class="auto-toggle"
        class:active={$autoSystems.engineering.enabled}
        type="button"
        on:click={toggleAutoEngineering}
      >
        AUTO-ENG: {$autoSystems.engineering.enabled ? "ENABLED" : "DISABLED"}
      </button>
      <ProposalQueue proposals={$proposals.engineering} station="engineering" />
    </section>
  {:else}
    <section class="column monitoring">
      <div class="column-title">Monitoring</div>
      <EventLog title="Engineering Log" domain="power" filter={ENGINEERING_EVENT_FILTER} priority="secondary" />
    </section>
  {/if}
</div>

<style>
  .engineering-root {
    --column-min: 20rem;
    width: 100%;
    min-height: 100%;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--column-min)), 1fr));
    gap: var(--space-xs);
    padding: var(--space-xs);
    align-content: start;
    overflow: visible;
  }

  .engineering-root.arcade {
    --column-min: 18rem;
  }

  .engineering-root.cpu {
    --column-min: 19rem;
  }

  .engineering-root.manual {
    --column-min: 21rem;
  }

  .column {
    min-height: 0;
    min-width: 0;
    overflow: visible;
    align-self: start;
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
  }

  .column.thermal {
    grid-column: span 2;
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

  @media (max-width: 1500px) {
    .engineering-root,
    .engineering-root.arcade,
    .engineering-root.cpu,
    .engineering-root.manual {
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 19rem), 1fr));
    }

    .column.thermal {
      grid-column: span 1;
    }
  }

  @media (max-width: 760px) {
    .engineering-root,
    .engineering-root.arcade,
    .engineering-root.cpu,
    .engineering-root.manual {
      grid-template-columns: 1fr;
    }
  }
</style>
