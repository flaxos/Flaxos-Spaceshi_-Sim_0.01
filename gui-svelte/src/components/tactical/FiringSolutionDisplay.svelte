<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    asRecord,
    extractShipState,
    getBestWeaponSolution,
    getSolutionFactors,
    getTargetingSummary,
    toNumber,
  } from "./tacticalData.js";

  let liveSolution: Record<string, unknown> = {};
  let pollHandle: number | null = null;

  $: ship = extractShipState($gameState);
  $: targeting = getTargetingSummary(ship);
  $: fallbackSolution = getBestWeaponSolution(ship);
  $: solution = Object.keys(liveSolution).length ? liveSolution : fallbackSolution;
  $: factors = getSolutionFactors(asRecord(solution) ?? {});
  $: overall = toNumber(solution.confidence, targeting.lockQuality);
  $: overallClass = overall >= 0.75 ? "good" : overall >= 0.45 ? "warn" : "bad";
  $: arcadeTier = $tier === "arcade";

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 2500);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    if (!targeting.lockedTarget) {
      liveSolution = {};
      return;
    }
    try {
      liveSolution = asRecord(await wsClient.sendShipCommand("get_target_solution", {})) ?? {};
    } catch {
      liveSolution = {};
    }
  }
</script>

<Panel title="Firing Solution" domain="weapons" priority={overall >= 0.7 ? "primary" : "secondary"} className="firing-solution-panel">
  <div class="shell">
    <div class="overall">
      <span>Overall confidence</span>
      <strong class={overallClass}>{Math.round(overall * 100)}%</strong>
    </div>

    <div class="track">
      <div class="fill {overallClass}" style={`width: ${Math.round(overall * 100)}%;`}></div>
    </div>

    {#if !arcadeTier}
      <div class="factor-list">
        {#each factors as factor}
          <div class="factor-row">
            <span>{factor.label}</span>
            <div class="factor-track"><div class="factor-fill" style={`width: ${Math.round(factor.value * 100)}%;`}></div></div>
            <strong>{Math.round(factor.value * 100)}%</strong>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</Panel>

<style>
  .shell,
  .factor-list {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .overall,
  .factor-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(70px, auto);
    gap: var(--space-sm);
    align-items: center;
  }

  .factor-row {
    grid-template-columns: 90px minmax(0, 1fr) 52px;
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  strong {
    font-family: var(--font-mono);
    text-align: right;
  }

  .track,
  .factor-track {
    height: 10px;
    border-radius: 999px;
    overflow: hidden;
    background: var(--bg-input);
  }

  .fill,
  .factor-fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.25), var(--tier-accent));
  }

  .good { color: var(--status-nominal); }
  .warn { color: #ffd84d; }
  .bad { color: var(--status-critical); }

  .fill.good { background: rgba(0, 255, 136, 0.85); }
  .fill.warn { background: rgba(255, 216, 77, 0.85); }
  .fill.bad { background: rgba(255, 68, 68, 0.85); }
</style>
