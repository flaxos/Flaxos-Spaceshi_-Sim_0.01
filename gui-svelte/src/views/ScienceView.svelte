<script lang="ts">
  import { tier } from "../lib/stores/tier.js";

  import SensorContacts from "../components/tactical/SensorContacts.svelte";
  import ScienceSensorMap from "../components/science/ScienceSensorMap.svelte";
  import ScienceAnalysisPanel from "../components/science/ScienceAnalysisPanel.svelte";
  import SensorAnalysisManual from "../components/science/SensorAnalysisManual.svelte";
  import SpectralAnalysisGame from "../components/games/SpectralAnalysisGame.svelte";
  import MassEstimationGame from "../components/games/MassEstimationGame.svelte";

  $: manualTier = $tier === "manual";
  $: rawTier = $tier === "raw";
  $: arcadeTier = $tier === "arcade";
</script>

<div class="science-root" class:arcade={arcadeTier}>
  <section class="group sensors">
    <div class="group-title">Sensors</div>
    <ScienceSensorMap />
    <SensorContacts passive />
    {#if manualTier || rawTier}
      <SensorAnalysisManual />
    {:else if arcadeTier}
      <SpectralAnalysisGame />
      <MassEstimationGame />
    {/if}
  </section>

  <section class="group analysis">
    <div class="group-title">Analysis</div>
    <ScienceAnalysisPanel />
    {#if arcadeTier}
      <SpectralAnalysisGame />
      <MassEstimationGame />
    {/if}
  </section>
</div>

<style>
  .science-root {
    width: 100%;
    min-height: 100%;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 26rem), 1fr));
    gap: var(--space-xs);
    padding: var(--space-xs);
    align-content: start;
    overflow: visible;
  }

  .science-root.arcade {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 24rem), 1fr));
  }

  .group {
    min-height: 0;
    min-width: 0;
    overflow: visible;
    align-self: start;
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
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

  @media (max-width: 1180px) {
    .science-root {
      grid-template-columns: 1fr;
    }
  }
</style>
