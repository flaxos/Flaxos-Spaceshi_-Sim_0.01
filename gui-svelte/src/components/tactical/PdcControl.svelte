<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import { extractShipState, getCombatState, getThreatList, toStringValue } from "./tacticalData.js";

  const modes = [
    { label: "AUTO", value: "auto" },
    { label: "MANUAL", value: "manual" },
    { label: "PRIORITY", value: "priority" },
    { label: "HOLD", value: "hold_fire" },
  ];

  $: ship = extractShipState($gameState);
  $: combat = getCombatState(ship);
  $: threats = getThreatList(ship);
  $: mode = toStringValue(combat.pdc_mode, "auto");
  $: priorityTarget = $selectedTacticalTargetId;

  async function setMode(next: string) {
    await wsClient.sendShipCommand("set_pdc_mode", { mode: next });
  }

  async function applyPriority(event: Event) {
    const targetId = (event.currentTarget as HTMLSelectElement).value;
    if (!targetId) return;
    await wsClient.sendShipCommand("set_pdc_priority", {
      torpedo_ids: [targetId],
      target_id: targetId,
    });
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
      <span>Priority target</span>
      <select value={priorityTarget} on:change={applyPriority}>
        <option value="">Select track</option>
        {#each threats as threat}
          <option value={threat.id}>{threat.id} · {threat.classification}</option>
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
    grid-template-columns: repeat(4, minmax(0, 1fr));
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
