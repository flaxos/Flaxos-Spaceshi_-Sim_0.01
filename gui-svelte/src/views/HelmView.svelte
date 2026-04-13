<script lang="ts">
  import { tier } from "../lib/stores/tier.js";

  import HelmWorkflowStrip from "../components/helm/HelmWorkflowStrip.svelte";
  import HelmNavMap from "../components/helm/HelmNavMap.svelte";
  import FlightDataPanel from "../components/helm/FlightDataPanel.svelte";
  import AutopilotStatus from "../components/helm/AutopilotStatus.svelte";
  import FlightComputerPanel from "../components/helm/FlightComputerPanel.svelte";
  import ManualFlightPanel from "../components/helm/ManualFlightPanel.svelte";
  import RcsControls from "../components/helm/RcsControls.svelte";
  import RcsThrusterDisplay from "../components/helm/RcsThrusterDisplay.svelte";
  import HelmQueuePanel from "../components/helm/HelmQueuePanel.svelte";
  import DockingPanel from "../components/helm/DockingPanel.svelte";
  import ManeuverPlanner from "../components/helm/ManeuverPlanner.svelte";
  import HelmBalanceGame from "../components/games/HelmBalanceGame.svelte";
  import SensorContacts from "../components/tactical/SensorContacts.svelte";

  $: manualTier = $tier === "manual";
  $: rawTier = $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";
</script>

<div class="helm-root" class:manual={manualTier} class:arcade={arcadeTier} class:cpu={cpuAssistTier}>
  <div class="workflow-slot">
    <HelmWorkflowStrip />
  </div>

  <section class="column awareness">
    <div class="column-title">Awareness</div>
    <HelmNavMap />
    <FlightDataPanel />
    <SensorContacts />
    {#if arcadeTier}
      <HelmBalanceGame />
    {/if}
    <RcsThrusterDisplay />
    {#if rawTier}
      <ManeuverPlanner />
    {/if}
  </section>

  <section class="column command">
    <div class="column-title">Command</div>

    {#if manualTier}
      <div class="prominent">
        <ManualFlightPanel />
      </div>
      <ManeuverPlanner />
    {:else if arcadeTier}
      <div class="prominent">
        <FlightComputerPanel />
      </div>
      <ManualFlightPanel />
      <RcsControls />
    {:else if cpuAssistTier}
      <FlightComputerPanel />
    {:else}
      <FlightComputerPanel />
      <ManualFlightPanel />
      <RcsControls />
      <ManeuverPlanner />
    {/if}
  </section>

  <section class="column status">
    <div class="column-title">Status</div>

    {#if cpuAssistTier}
      <div class="prominent">
        <AutopilotStatus />
      </div>
    {:else}
      <AutopilotStatus />
    {/if}

    <HelmQueuePanel />
    <DockingPanel />
  </section>
</div>

<style>
  .helm-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: minmax(270px, 0.9fr) minmax(340px, 1.2fr) minmax(270px, 0.95fr);
    grid-template-rows: auto minmax(0, 1fr);
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
  }

  .helm-root.manual {
    grid-template-columns: minmax(250px, 0.8fr) minmax(420px, 1.45fr) minmax(250px, 0.85fr);
  }

  .helm-root.cpu {
    grid-template-columns: minmax(260px, 0.9fr) minmax(320px, 1fr) minmax(340px, 1.2fr);
  }

  .workflow-slot {
    grid-column: 1 / -1;
    min-width: 0;
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

  .prominent {
    flex: 1 0 auto;
  }

  .prominent :global(.panel) {
    height: 100%;
  }

  @media (max-width: 1180px) {
    .helm-root,
    .helm-root.manual,
    .helm-root.cpu {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-template-rows: auto auto minmax(0, 1fr);
    }

    .awareness {
      grid-column: 1;
    }

    .command {
      grid-column: 2;
    }

    .status {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: 780px) {
    .helm-root,
    .helm-root.manual,
    .helm-root.cpu {
      grid-template-columns: 1fr;
      grid-template-rows: auto;
      overflow: auto;
    }

    .column {
      overflow: visible;
    }
  }
</style>
