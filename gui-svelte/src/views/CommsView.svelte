<script lang="ts">
  import { tier } from "../lib/stores/tier.js";

  import CommsControlPanel from "../components/comms/CommsControlPanel.svelte";
  import CommsChoicePanel from "../components/comms/CommsChoicePanel.svelte";
  import StationChat from "../components/comms/StationChat.svelte";
  import HailFrequencyGame from "../components/games/HailFrequencyGame.svelte";
  import SensorContacts from "../components/tactical/SensorContacts.svelte";

  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";
</script>

<div class="comms-root" class:arcade={arcadeTier} class:cpu={cpuAssistTier}>
  <section class="group radio">
    <div class="group-title">Radio</div>
    <CommsControlPanel />
    {#if arcadeTier}
      <HailFrequencyGame />
    {/if}
  </section>

  <section class="group incoming">
    <div class="group-title">Incoming</div>
    <CommsChoicePanel />
  </section>

  <section class="group situation">
    <div class="group-title">Situation</div>
    <StationChat />
    <SensorContacts passive />
  </section>
</div>

<style>
  .comms-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: minmax(340px, 1.15fr) minmax(320px, 1fr) minmax(340px, 1.05fr);
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
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

  @media (max-width: 1180px) {
    .comms-root {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-auto-rows: minmax(0, 1fr);
    }
  }

  @media (max-width: 760px) {
    .comms-root {
      grid-template-columns: 1fr;
      height: auto;
      overflow: auto;
    }

    .group {
      overflow: visible;
    }
  }
</style>
