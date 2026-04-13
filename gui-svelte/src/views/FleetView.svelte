<script lang="ts">
  import { tier } from "../lib/stores/tier.js";
  import { wsClient } from "../lib/ws/wsClient.js";
  import { proposals, autoSystems } from "../lib/stores/proposals.js";

  import FleetTacticalDisplay from "../components/fleet/FleetTacticalDisplay.svelte";
  import FleetRoster from "../components/fleet/FleetRoster.svelte";
  import FormationControl from "../components/fleet/FormationControl.svelte";
  import FleetOrders from "../components/fleet/FleetOrders.svelte";
  import FleetFireControl from "../components/fleet/FleetFireControl.svelte";
  import SharedContacts from "../components/fleet/SharedContacts.svelte";
  import FleetFormationGame from "../components/games/FleetFormationGame.svelte";
  import ProposalQueue from "../components/shared/ProposalQueue.svelte";

  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  async function toggleAutoFleet() {
    await wsClient.sendShipCommand(
      $autoSystems.fleet.enabled ? "disable_auto_fleet" : "enable_auto_fleet",
      {}
    );
  }
</script>

<div class="fleet-root" class:arcade={arcadeTier} class:cpu={cpuAssistTier}>
  <section class="group tactical">
    <div class="group-title">Tactical</div>
    <FleetTacticalDisplay />
    <FleetRoster />
  </section>

  <section class="group formation">
    <div class="group-title">Formation</div>
    <FormationControl />
    {#if arcadeTier}
      <FleetFormationGame />
    {/if}
  </section>

  <section class="group orders">
    <div class="group-title">Orders</div>
    <FleetOrders />
    <SharedContacts />
    {#if cpuAssistTier}
      <div class="cpu-fleet-panel">
        <button
          class="auto-toggle"
          class:active={$autoSystems.fleet.enabled}
          type="button"
          on:click={toggleAutoFleet}
        >
          AUTO-FLEET: {$autoSystems.fleet.enabled ? "ENABLED" : "DISABLED"}
        </button>
        <ProposalQueue proposals={$proposals.fleet} station="fleet" />
      </div>
    {/if}
  </section>

  <section class="group fire">
    <div class="group-title">Fire Control</div>
    <FleetFireControl />
  </section>
</div>

<style>
  .fleet-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: minmax(360px, 1.3fr) minmax(280px, 0.95fr) minmax(320px, 1fr) minmax(260px, 0.85fr);
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
  }

  .fleet-root.cpu {
    grid-template-columns: minmax(340px, 1.2fr) minmax(260px, 0.9fr) minmax(340px, 1.1fr) minmax(250px, 0.85fr);
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

  .cpu-fleet-panel {
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

  @media (max-width: 1320px) {
    .fleet-root,
    .fleet-root.cpu {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-auto-rows: minmax(0, 1fr);
    }
  }

  @media (max-width: 820px) {
    .fleet-root,
    .fleet-root.cpu {
      grid-template-columns: 1fr;
      height: auto;
      overflow: auto;
    }

    .group {
      overflow: visible;
    }
  }
</style>
