<script lang="ts">
  import { tier } from "../lib/stores/tier.js";
  import FlightDataPanel from "../components/helm/FlightDataPanel.svelte";
  import FlightComputerPanel from "../components/helm/FlightComputerPanel.svelte";
  import ManualFlightPanel from "../components/helm/ManualFlightPanel.svelte";
  import RcsControls from "../components/helm/RcsControls.svelte";
  import HelmNavMap from "../components/helm/HelmNavMap.svelte";
  import HelmNavigationPanel from "../components/helm/HelmNavigationPanel.svelte";
  import HelmSupportDrawer from "../components/helm/HelmSupportDrawer.svelte";
  import SensorContacts from "../components/tactical/SensorContacts.svelte";
  import SubsystemStatus from "../components/engineering/SubsystemStatus.svelte";
  import HelmBalanceGame from "../components/games/HelmBalanceGame.svelte";

  // Tier drives which center-cell workflow the pilot uses:
  //   manual/raw   → direct throttle + RCS controls (stacked)
  //   arcade       → helm balance mini-game
  //   cpu-assist   → flight computer program selector
  // All other cells stay the same — information density doesn't change by tier.
  $: manualLike = $tier === "manual" || $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssist = $tier === "cpu-assist";
</script>

<div class="helm-root">
  <div class="cell left-top"><FlightDataPanel /></div>
  <div class="cell left-bottom"><SensorContacts /></div>

  <div class="cell center">
    {#if manualLike}
      <div class="stack">
        <ManualFlightPanel />
        <RcsControls />
      </div>
    {:else if arcadeTier}
      <HelmBalanceGame />
    {:else if cpuAssist}
      <FlightComputerPanel />
    {/if}
  </div>
  <div class="cell nav"><HelmNavMap /></div>

  <div class="cell right-top"><SubsystemStatus /></div>
  <div class="cell right-bottom"><HelmNavigationPanel /></div>

  <div class="cell support"><HelmSupportDrawer /></div>
</div>

<style>
  .helm-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: 210px minmax(0, 1fr) 220px;
    grid-template-rows: minmax(0, 1fr) minmax(220px, 0.78fr) auto;
    grid-template-areas:
      "left-top center right-top"
      "left-bottom nav right-bottom"
      "support support support";
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
  }

  .cell {
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .left-top { grid-area: left-top; }
  .left-bottom { grid-area: left-bottom; }
  .center { grid-area: center; }
  .nav { grid-area: nav; }
  .right-top { grid-area: right-top; }
  .right-bottom { grid-area: right-bottom; }
  .support { grid-area: support; overflow: visible; }

  /* manual/raw: stack ManualFlightPanel + RcsControls in the center cell. */
  .stack {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    min-height: 0;
    overflow: auto;
  }

  @media (max-width: 1180px) {
    .helm-root {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      grid-template-rows: minmax(0, 1fr) minmax(260px, auto) auto auto;
      grid-template-areas:
        "left-top right-top"
        "center center"
        "nav nav"
        "left-bottom right-bottom"
        "support support";
      overflow: auto;
    }
  }

  @media (max-width: 780px) {
    .helm-root {
      grid-template-columns: 1fr;
      grid-template-areas:
        "left-top"
        "center"
        "nav"
        "right-top"
        "left-bottom"
        "right-bottom"
        "support";
    }
  }
</style>
