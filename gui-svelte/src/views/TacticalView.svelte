<script lang="ts">
  import { tier } from "../lib/stores/tier.js";
  import SensorContacts from "../components/tactical/SensorContacts.svelte";
  import TacticalMap from "../components/tactical/TacticalMap.svelte";
  import TargetingDisplay from "../components/tactical/TargetingDisplay.svelte";
  import CombatLog from "../components/tactical/CombatLog.svelte";
  import WeaponsHardpointsDisplay from "../components/tactical/WeaponsHardpointsDisplay.svelte";
  import WeaponsWorkflowPanel from "../components/tactical/WeaponsWorkflowPanel.svelte";
  import TacticalSupportDrawer from "../components/tactical/TacticalSupportDrawer.svelte";
  import FireAuthorization from "../components/tactical/FireAuthorization.svelte";
  import FiringSolutionDisplay from "../components/tactical/FiringSolutionDisplay.svelte";
  import ThreatBoard from "../components/tactical/ThreatBoard.svelte";
  import ArcadeTacticalPanel from "../components/tactical/ArcadeTacticalPanel.svelte";

  // Tier drives interaction model, not information density.
  //   manual/raw   → direct hardpoint controls + full sensor table
  //   arcade       → mini-game style combat station + threat board
  //   cpu-assist   → one-click fire authorization + firing solution telemetry
  $: manualLike = $tier === "manual" || $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssist = $tier === "cpu-assist";
</script>

<div class="tactical-root">
  <div class="cell contacts">
    {#if arcadeTier}
      <ThreatBoard />
    {:else}
      <SensorContacts />
    {/if}
  </div>
  <div class="cell map"><TacticalMap /></div>
  <div class="cell targeting"><TargetingDisplay /></div>

  <div class="cell ship-status">
    {#if manualLike}
      <WeaponsHardpointsDisplay title="Ship Status" />
    {:else if arcadeTier}
      <FiringSolutionDisplay />
    {:else if cpuAssist}
      <FiringSolutionDisplay />
    {/if}
  </div>
  <div class="cell combat-log"><CombatLog /></div>
  <div class="cell weapons">
    {#if manualLike}
      <WeaponsWorkflowPanel />
    {:else if arcadeTier}
      <ArcadeTacticalPanel />
    {:else if cpuAssist}
      <FireAuthorization />
    {/if}
  </div>

  <div class="cell support"><TacticalSupportDrawer /></div>
</div>

<style>
  .tactical-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr) 280px;
    grid-template-rows: minmax(0, 1.65fr) minmax(250px, 0.95fr) auto;
    grid-template-areas:
      "contacts map targeting"
      "ship-status combat-log weapons"
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

  .contacts { grid-area: contacts; }
  .map { grid-area: map; }
  .targeting { grid-area: targeting; }
  .ship-status { grid-area: ship-status; }
  .combat-log { grid-area: combat-log; }
  .weapons { grid-area: weapons; }
  .support { grid-area: support; overflow: visible; }

  @media (max-width: 1280px) {
    .tactical-root {
      grid-template-columns: 210px minmax(0, 1fr) 260px;
    }
  }

  @media (max-width: 980px) {
    .tactical-root {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      grid-template-rows: minmax(320px, 1.4fr) auto auto auto auto;
      grid-template-areas:
        "map map"
        "contacts targeting"
        "ship-status weapons"
        "combat-log combat-log"
        "support support";
      height: auto;
      overflow: auto;
    }
  }

  @media (max-width: 720px) {
    .tactical-root {
      grid-template-columns: 1fr;
      grid-template-areas:
        "map"
        "contacts"
        "targeting"
        "ship-status"
        "weapons"
        "combat-log"
        "support";
    }
  }
</style>
