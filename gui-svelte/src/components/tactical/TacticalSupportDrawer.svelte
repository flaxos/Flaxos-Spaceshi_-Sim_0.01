<script lang="ts">
  import { tier } from "../../lib/stores/tier.js";

  import FiringSolutionDisplay from "./FiringSolutionDisplay.svelte";
  import SubsystemSelector from "./SubsystemSelector.svelte";
  import ThreatBoard from "./ThreatBoard.svelte";
  import FireAuthorization from "./FireAuthorization.svelte";
  import EcmControlPanel from "./EcmControlPanel.svelte";
  import EccmControlPanel from "./EccmControlPanel.svelte";
  import MultiTrackPanel from "./MultiTrackPanel.svelte";
  import TargetAssessment from "./TargetAssessment.svelte";

  import SensorSweepGame from "../games/SensorSweepGame.svelte";
  import TargetingLockGame from "../games/TargetingLockGame.svelte";
  import WeaponsChargeGame from "../games/WeaponsChargeGame.svelte";
  import PdcThreatGame from "../games/PdcThreatGame.svelte";
  import EcmFrequencyGame from "../games/EcmFrequencyGame.svelte";
  import MunitionConfigGame from "../games/MunitionConfigGame.svelte";

  type DrawerTab = "analysis" | "control" | "ew" | "arcade" | null;

  let activeTab: DrawerTab = null;
  let openedArcadeTools = false;

  $: arcadeTier = $tier === "arcade";
  $: if (arcadeTier && !openedArcadeTools) {
    activeTab = "arcade";
    openedArcadeTools = true;
  }

  function toggle(tab: Exclude<DrawerTab, null>) {
    activeTab = activeTab === tab ? null : tab;
  }
</script>

<div class="support-drawer" class:open={activeTab !== null}>
  <div class="toolbar">
    <button class:active={activeTab === "analysis"} type="button" on:click={() => toggle("analysis")}>Analysis</button>
    <button class:active={activeTab === "control"} type="button" on:click={() => toggle("control")}>Control</button>
    <button class:active={activeTab === "ew"} type="button" on:click={() => toggle("ew")}>EW</button>
    {#if arcadeTier}
      <button class:active={activeTab === "arcade"} type="button" on:click={() => toggle("arcade")}>Arcade</button>
    {/if}
  </div>

  {#if activeTab !== null}
    <div class="drawer-body">
      {#if activeTab === "analysis"}
        <ThreatBoard />
        <TargetAssessment />
        <FiringSolutionDisplay />
        <SubsystemSelector />
      {:else if activeTab === "control"}
        <FireAuthorization />
        <MultiTrackPanel />
      {:else if activeTab === "ew"}
        <EcmControlPanel />
        <EccmControlPanel />
      {:else if activeTab === "arcade"}
        <SensorSweepGame />
        <TargetingLockGame />
        <WeaponsChargeGame />
        <PdcThreatGame />
        <EcmFrequencyGame />
        <MunitionConfigGame />
      {/if}
    </div>
  {/if}
</div>

<style>
  .support-drawer {
    display: grid;
    gap: var(--space-xs);
    min-height: 34px;
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
