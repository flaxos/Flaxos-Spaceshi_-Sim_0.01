<script lang="ts">
  import { tier } from "../lib/stores/tier.js";

  import FleetTacticalDisplay from "../components/fleet/FleetTacticalDisplay.svelte";
  import FleetRoster from "../components/fleet/FleetRoster.svelte";
  import FormationControl from "../components/fleet/FormationControl.svelte";
  import FleetOrders from "../components/fleet/FleetOrders.svelte";
  import FleetFireControl from "../components/fleet/FleetFireControl.svelte";
  import SharedContacts from "../components/fleet/SharedContacts.svelte";
  import FleetFormationGame from "../components/games/FleetFormationGame.svelte";

  $: arcadeTier = $tier === "arcade";
</script>

<div class="fleet-root" class:arcade={arcadeTier}>
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

  @media (max-width: 1320px) {
    .fleet-root {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-auto-rows: minmax(0, 1fr);
    }
  }

  @media (max-width: 820px) {
    .fleet-root {
      grid-template-columns: 1fr;
      height: auto;
      overflow: auto;
    }

    .group {
      overflow: visible;
    }
  }
</style>
