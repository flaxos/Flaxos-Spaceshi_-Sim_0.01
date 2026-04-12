<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { countRestingCrew, formatPercent, getCrewFatigueState, getOpsShip, readinessClass, toNumber } from "./opsData.js";

  let feedback = "";

  $: ship = getOpsShip($gameState);
  $: fatigue = getCrewFatigueState(ship);
  $: fatiguePercent = clampPercent(toNumber(fatigue.fatigue) * 100);
  $: gLoad = toNumber(fatigue.g_load);
  $: performance = clampPercent(toNumber(fatigue.performance, 1) * 100);
  $: restingCrew = countRestingCrew(ship);
  $: restOrdered = Boolean(fatigue.rest_ordered);

  function clampPercent(value: number): number {
    return Math.max(0, Math.min(100, value));
  }

  async function toggleRest(ordered: boolean) {
    feedback = "";
    try {
      await wsClient.sendShipCommand(ordered ? "cancel_rest" : "crew_rest", {});
      feedback = ordered ? "Rest order cancelled" : "Rest order sent";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Crew rest command failed";
    }
  }
</script>

<Panel title="Crew Fatigue" domain="power" priority="secondary" className="crew-fatigue-display">
  <div class="shell">
    <div class="metric-card">
      <div class="head">
        <span>Fatigue</span>
        <strong class={readinessClass(100 - fatiguePercent)}>{formatPercent(fatiguePercent)}</strong>
      </div>
      <div class="track">
        <div class="fill {readinessClass(100 - fatiguePercent)}" style={`width:${fatiguePercent.toFixed(0)}%;`}></div>
      </div>
    </div>

    <div class="stats-grid">
      <div><span>G-Load</span><strong>{gLoad.toFixed(1)}g</strong></div>
      <div><span>Performance</span><strong>{formatPercent(performance)}</strong></div>
      <div><span>Resting Crew</span><strong>{restingCrew}</strong></div>
      <div><span>Status</span><strong>{String(fatigue.status ?? "nominal").toUpperCase()}</strong></div>
    </div>

    <button type="button" class:active={restOrdered} on:click={() => toggleRest(restOrdered)}>
      {restOrdered ? "CANCEL REST" : "ORDER CREW REST"}
    </button>

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .metric-card,
  .feedback {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .stats-grid {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  span,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .track {
    height: 12px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
  }

  .fill.nominal {
    background: rgba(0, 255, 136, 0.82);
  }

  .fill.warning {
    background: rgba(255, 170, 0, 0.88);
  }

  .fill.critical {
    background: rgba(255, 68, 68, 0.9);
  }

  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  button.active {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .feedback {
    color: var(--status-info);
  }
</style>
