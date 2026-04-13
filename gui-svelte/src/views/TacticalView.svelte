<script lang="ts">
  import { tier } from "../lib/stores/tier.js";

  import SensorContacts from "../components/tactical/SensorContacts.svelte";
  import TacticalMap from "../components/tactical/TacticalMap.svelte";
  import TargetingDisplay from "../components/tactical/TargetingDisplay.svelte";
  import FiringSolutionDisplay from "../components/tactical/FiringSolutionDisplay.svelte";
  import SubsystemSelector from "../components/tactical/SubsystemSelector.svelte";
  import ThreatBoard from "../components/tactical/ThreatBoard.svelte";
  import WeaponsStatus from "../components/tactical/WeaponsStatus.svelte";
  import FireAuthorization from "../components/tactical/FireAuthorization.svelte";
  import RailgunControl from "../components/tactical/RailgunControl.svelte";
  import PdcControl from "../components/tactical/PdcControl.svelte";
  import LauncherControl from "../components/tactical/LauncherControl.svelte";
  import EcmControlPanel from "../components/tactical/EcmControlPanel.svelte";
  import EccmControlPanel from "../components/tactical/EccmControlPanel.svelte";
  import MultiTrackPanel from "../components/tactical/MultiTrackPanel.svelte";
  import CombatLog from "../components/tactical/CombatLog.svelte";
  import TargetAssessment from "../components/tactical/TargetAssessment.svelte";

  import SensorSweepGame from "../components/games/SensorSweepGame.svelte";
  import TargetingLockGame from "../components/games/TargetingLockGame.svelte";
  import WeaponsChargeGame from "../components/games/WeaponsChargeGame.svelte";
  import PdcThreatGame from "../components/games/PdcThreatGame.svelte";
  import EcmFrequencyGame from "../components/games/EcmFrequencyGame.svelte";
  import MunitionConfigGame from "../components/games/MunitionConfigGame.svelte";
  import MunitionProgrammingPanel from "../components/games/MunitionProgrammingPanel.svelte";

  $: manualTier = $tier === "manual";
  $: rawTier = $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";
</script>

<div class="tactical-root" class:arcade={arcadeTier} class:manual={manualTier} class:cpu={cpuAssistTier}>
  <section class="group detect">
    <div class="group-title">Detect</div>
    <TacticalMap />
    <SensorContacts />
    {#if arcadeTier}
      <SensorSweepGame />
    {/if}
  </section>

  <section class="group decide">
    <div class="group-title">Decide</div>
    <TargetingDisplay />
    <FiringSolutionDisplay />
    <SubsystemSelector />
    <MultiTrackPanel />
    {#if arcadeTier}
      <TargetingLockGame />
    {/if}
  </section>

  <section class="group destroy">
    <div class="group-title">Destroy</div>
    <FireAuthorization />
    {#if arcadeTier}
      <WeaponsChargeGame />
      <MunitionConfigGame />
      <PdcThreatGame />
    {:else if cpuAssistTier}
      <!-- CPU-ASSIST: proposal-based fire handled by FireAuthorization above -->
    {:else}
      <RailgunControl />
      <PdcControl />
      <LauncherControl />
      {#if manualTier}
        <MunitionProgrammingPanel />
      {/if}
    {/if}
  </section>

  <section class="group awareness">
    <div class="group-title">Awareness</div>
    <ThreatBoard />
    <WeaponsStatus />
    <TargetAssessment />
    <EcmControlPanel />
    <EccmControlPanel />
    {#if arcadeTier}
      <EcmFrequencyGame />
    {/if}
  </section>

  <section class="group aftermath">
    <div class="group-title">After-Action</div>
    <CombatLog />
    {#if cpuAssistTier}
      <SensorContacts passive />
    {/if}
  </section>
</div>

<style>
  .tactical-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: minmax(320px, 1.25fr) minmax(260px, 0.95fr) minmax(280px, 1fr) minmax(250px, 0.9fr) minmax(260px, 0.95fr);
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
  }

  .tactical-root.arcade {
    grid-template-columns: minmax(300px, 1.15fr) minmax(250px, 0.9fr) minmax(300px, 1.05fr) minmax(240px, 0.85fr) minmax(240px, 0.85fr);
  }

  .tactical-root.cpu {
    grid-template-columns: minmax(300px, 1.1fr) minmax(280px, 0.95fr) minmax(320px, 1.1fr) minmax(260px, 0.9fr) minmax(260px, 0.9fr);
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
    .tactical-root,
    .tactical-root.arcade,
    .tactical-root.cpu {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      grid-auto-rows: minmax(0, 1fr);
    }
  }

  @media (max-width: 1080px) {
    .tactical-root,
    .tactical-root.arcade,
    .tactical-root.cpu {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      height: auto;
      overflow: auto;
    }

    .group {
      overflow: visible;
    }
  }

  @media (max-width: 760px) {
    .tactical-root,
    .tactical-root.arcade,
    .tactical-root.cpu {
      grid-template-columns: 1fr;
    }
  }
</style>
