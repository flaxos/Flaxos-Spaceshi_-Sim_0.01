<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import {
    extractShipState,
    formatDistance,
    getCombatState,
    getIncomingMunitions,
    toStringValue,
  } from "./tacticalData.js";
  import { setPdcMode, setPdcPriority } from "./tacticalActions.js";

  const modes = [
    { label: "AUTO", value: "auto" },
    { label: "MANUAL", value: "manual" },
    { label: "NETWORK", value: "network" },
    { label: "PRIORITY", value: "priority" },
    { label: "HOLD", value: "hold_fire" },
  ];

  $: ship = extractShipState($gameState);
  $: combat = getCombatState(ship);
  $: incomingMunitions = getIncomingMunitions($gameState, ship);
  $: mode = toStringValue(combat.pdc_mode, "auto");
  $: priorityTarget = Array.isArray(combat.pdc_priority_targets)
    ? toStringValue(combat.pdc_priority_targets[0])
    : "";

  async function setMode(next: string) {
    await setPdcMode(next);
  }

  async function applyPriority(event: Event) {
    const targetId = (event.currentTarget as HTMLSelectElement).value;
    if (!targetId) return;
    await setPdcPriority([targetId]);
  }
</script>

<Panel title="PDC Control" domain="weapons" priority="secondary" className="pdc-control-panel">
  <div class="shell">
    <div class="mode-grid">
      {#each modes as item}
        <button class:selected={mode === item.value} type="button" on:click={() => setMode(item.value)}>{item.label}</button>
      {/each}
    </div>

    <label>
      <span>Priority munition</span>
      <select value={priorityTarget} on:change={applyPriority}>
        <option value="">Select incoming threat</option>
        {#each incomingMunitions as munition}
          <option value={munition.id}>
            {munition.id} · {munition.munitionType.toUpperCase()} · {formatDistance(munition.distance)}
          </option>
        {/each}
      </select>
    </label>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .mode-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 6px;
  }

  .mode-grid button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  label {
    display: grid;
    gap: 6px;
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
</style>
