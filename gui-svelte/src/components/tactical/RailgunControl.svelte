<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import { extractShipState, getLockedTargetId, getRailgunMounts } from "./tacticalData.js";
  import { fireRailgun } from "./tacticalActions.js";

  $: ship = extractShipState($gameState);
  $: mounts = getRailgunMounts(ship);
  $: targetId = $selectedTacticalTargetId || getLockedTargetId(ship);
  $: arcadeTier = $tier === "arcade";

  let firing = new Set<string>();

  async function fireMount(mountId: string) {
    if (firing.has(mountId)) return;
    firing = new Set(firing).add(mountId);
    try {
      await fireRailgun({ mountId, targetId: targetId || undefined });
    } finally {
      firing = new Set(firing);
      firing.delete(mountId);
      firing = firing;
    }
  }

  function fireTitle(mount: ReturnType<typeof getRailgunMounts>[number]): string {
    if (mount.ammo <= 0) return "No ammunition";
    if (!mount.ready) {
      const pct = Math.round(mount.charge * 100);
      return pct < 100 ? `Charging (${pct}%)` : "Not ready";
    }
    if (!targetId) return "No target selected";
    return "Fire railgun";
  }
</script>

<Panel title="Railgun Control" domain="weapons" priority="secondary" className="railgun-control-panel">
  <div class="shell">
    {#if mounts.length === 0}
      <div class="empty">No railgun mounts installed.</div>
    {:else}
      {#each mounts as mount}
        <div class="mount-row">
          <div class="meta">
            <strong>{mount.id}</strong>
            <span>
              {mount.ammo} slugs ·
              {#if mount.ready}
                READY
              {:else}
                {mount.status.toUpperCase()} {mount.charge < 1 ? `${Math.round(mount.charge * 100)}%` : ""}
              {/if}
            </span>
          </div>
          <div class="track">
            <div class="fill" class:arcade={arcadeTier} style={`width: ${Math.round(mount.charge * 100)}%;`}></div>
          </div>
          <button
            disabled={!mount.ready || mount.ammo <= 0 || firing.has(mount.id)}
            title={fireTitle(mount)}
            on:click={() => fireMount(mount.id)}
          >{firing.has(mount.id) ? "…" : "FIRE"}</button>
        </div>
      {/each}
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .mount-row {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
  }

  .meta {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .meta span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .track {
    height: 10px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.25), var(--tier-accent));
  }

  .fill.arcade {
    animation: pulse 1.2s ease-in-out infinite;
  }

  strong {
    font-family: var(--font-mono);
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.75; }
    50% { opacity: 1; }
  }
</style>
