<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { extractShipState, getLauncherInventory, getRailgunMounts } from "./tacticalData.js";

  $: ship = extractShipState($gameState);
  $: inventory = getLauncherInventory(ship);
  $: railguns = getRailgunMounts(ship);
  $: averageCharge = railguns.length
    ? railguns.reduce((sum, mount) => sum + mount.charge, 0) / railguns.length
    : 0;
</script>

<Panel title="Weapons Status" domain="weapons" priority="secondary" className="weapons-status-panel">
  <div class="shell">
    <div class="stat-grid">
      <div class="card"><span>Railgun mounts</span><strong>{railguns.length}</strong></div>
      <div class="card"><span>Rail charge</span><strong>{Math.round(averageCharge * 100)}%</strong></div>
      <div class="card"><span>Torpedoes</span><strong>{inventory.torpedoes.loaded ?? 0}/{inventory.torpedoes.capacity ?? 0}</strong></div>
      <div class="card"><span>Missiles</span><strong>{inventory.missiles.loaded ?? 0}/{inventory.missiles.capacity ?? 0}</strong></div>
    </div>

    {#if railguns.length > 0}
      <div class="mount-list">
        {#each railguns as mount}
          <div class="mount-row">
            <strong>{mount.id}</strong>
            <span>{Math.round(mount.charge * 100)}% charged</span>
            <span>{mount.ammo} slugs</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</Panel>

<style>
  .shell,
  .mount-list {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .stat-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .card,
  .mount-row {
    display: grid;
    gap: 4px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.025);
  }

  .card span,
  .mount-row span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  strong {
    font-family: var(--font-mono);
  }
</style>
