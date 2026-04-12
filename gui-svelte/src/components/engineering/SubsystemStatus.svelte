<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { getEngineeringShip, getSubsystemRows } from "./engineeringData.js";

  $: ship = getEngineeringShip($gameState);
  $: rows = getSubsystemRows(ship);
  $: showExact = $tier === "raw" || $tier === "manual";

  function healthClass(percent: number): string {
    if (percent < 35) return "critical";
    if (percent < 60) return "warning";
    return "nominal";
  }
</script>

<Panel title="Subsystem Status" domain="power" priority={$tier === "raw" ? "primary" : "secondary"} className="subsystem-status-panel">
  <div class="stack">
    {#each rows as row}
      <div class="system-card">
        <div class="head">
          <strong>{row.label}</strong>
          <span class={healthClass(row.healthPercent)}>{row.status.toUpperCase()}</span>
        </div>
        <div class="track">
          <div class="fill {healthClass(row.healthPercent)}" style={`width:${row.healthPercent.toFixed(0)}%;`}></div>
        </div>
        <div class="meta">
          {#if showExact}
            <span>Health {row.healthPercent.toFixed(1)}%</span>
            <span>Damage {row.damagePercent.toFixed(1)}%</span>
          {:else}
            <span>{healthClass(row.healthPercent).toUpperCase()}</span>
            <span>{row.repairStatus.toUpperCase()}</span>
          {/if}
        </div>
        {#if showExact}
          <div class="detail">
            <span>Heat {row.heatPercent.toFixed(0)}%</span>
            <span>Repair {row.repairStatus.toUpperCase()}</span>
          </div>
        {/if}
      </div>
    {/each}
  </div>
</Panel>

<style>
  .stack {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .system-card {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .meta,
  .detail {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .meta,
  .detail,
  .head span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .track {
    height: 10px;
    border-radius: 999px;
    overflow: hidden;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
  }

  .nominal,
  .fill.nominal {
    color: var(--status-nominal);
    background: rgba(0, 255, 136, 0.82);
  }

  .warning,
  .fill.warning {
    color: var(--status-warning);
    background: rgba(255, 170, 0, 0.88);
  }

  .critical,
  .fill.critical {
    color: var(--status-critical);
    background: rgba(255, 68, 68, 0.9);
  }
</style>
