<script lang="ts">
  import { tier } from "../lib/stores/tier.js";
  import { wsClient } from "../lib/ws/wsClient.js";
  import { proposals, autoSystems } from "../lib/stores/proposals.js";

  import CommsControlPanel from "../components/comms/CommsControlPanel.svelte";
  import CommsChoicePanel from "../components/comms/CommsChoicePanel.svelte";
  import StationChat from "../components/comms/StationChat.svelte";
  import HailFrequencyGame from "../components/games/HailFrequencyGame.svelte";
  import SensorContacts from "../components/tactical/SensorContacts.svelte";
  import ProposalQueue from "../components/shared/ProposalQueue.svelte";

  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  async function toggleAutoComms() {
    await wsClient.sendShipCommand(
      $autoSystems.comms.enabled ? "disable_auto_comms" : "enable_auto_comms",
      {}
    );
  }
</script>

<div class="comms-root" class:arcade={arcadeTier} class:cpu={cpuAssistTier}>
  <section class="group radio">
    <div class="group-title">Radio</div>
    <CommsControlPanel />
    {#if arcadeTier}
      <HailFrequencyGame />
    {/if}
    {#if cpuAssistTier}
      <div class="cpu-comms-panel">
        <button
          class="auto-toggle"
          class:active={$autoSystems.comms.enabled}
          type="button"
          on:click={toggleAutoComms}
        >
          AUTO-COMMS: {$autoSystems.comms.enabled ? "ENABLED" : "DISABLED"}
        </button>
        <ProposalQueue proposals={$proposals.comms} station="comms" />
      </div>
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

  .cpu-comms-panel {
    display: grid;
    gap: var(--space-sm);
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
