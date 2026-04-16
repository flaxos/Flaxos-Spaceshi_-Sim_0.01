<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import { extractShipState, formatDistance, getThreatList } from "./tacticalData.js";
  import { lockTarget } from "./tacticalActions.js";

  $: ship = extractShipState($gameState);
  $: threats = getThreatList(ship).slice(0, 8);

  let locking: string | null = null;

  async function lockThreat(contactId: string) {
    if (locking) return;
    locking = contactId;
    try {
      selectedTacticalTargetId.set(contactId);
      await lockTarget(contactId);
    } finally {
      locking = null;
    }
  }
</script>

<Panel title="Threat Board" domain="weapons" priority="secondary" className="threat-board-panel">
  <div class="shell">
    {#if threats.length === 0}
      <div class="empty">No active threats detected.</div>
    {:else}
      {#each threats as threat, index}
        <button
          class="threat-row {threat.threatLevel}"
          class:selected={threat.id === $selectedTacticalTargetId}
          class:locking={locking === threat.id}
          disabled={locking != null}
          title="Lock {threat.id} as primary target"
          type="button"
          on:click={() => lockThreat(threat.id)}
        >
          <span class="index">{index + 1}</span>
          <div class="body">
            <strong>{threat.id}</strong>
            <span>{threat.classification || "Unknown"} · {formatDistance(threat.distance)}</span>
          </div>
          <span class="score" title="Composite threat score (0–100): range, closure rate, classification">{Math.round(threat.threatScore * 100)}</span>
        </button>
      {/each}
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-xs);
    padding: var(--space-sm);
  }

  .threat-row {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr) auto;
    gap: var(--space-sm);
    align-items: center;
    padding: 10px;
    text-align: left;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.02);
  }

  .threat-row.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
  }

  .threat-row.locking {
    opacity: 0.6;
  }

  .threat-row.red { border-color: rgba(255, 68, 68, 0.45); }
  .threat-row.orange { border-color: rgba(255, 157, 71, 0.45); }
  .threat-row.yellow { border-color: rgba(255, 216, 77, 0.35); }
  .threat-row.green { border-color: rgba(0, 255, 136, 0.28); }

  .index,
  .score,
  .empty,
  .body span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .index,
  .score,
  strong {
    font-family: var(--font-mono);
  }

  .body {
    display: grid;
    gap: 4px;
  }
</style>
