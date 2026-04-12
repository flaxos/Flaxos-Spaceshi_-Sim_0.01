<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    asRecord,
    extractShipState,
    formatDistance,
    formatDuration,
    getLockedTargetId,
    getTargetingSummary,
    toNumber,
    toStringValue,
  } from "./tacticalData.js";

  const stages = ["Acquisition", "Weapons Lock", "Solution", "Ready to Fire"];

  let solution: Record<string, unknown> = {};
  let pollHandle: number | null = null;

  $: ship = extractShipState($gameState);
  $: targeting = getTargetingSummary(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: targetId = $selectedTacticalTargetId || lockedTargetId;
  $: solutionQuality = Math.max(targeting.lockQuality, toNumber(solution.lock_quality, 0));
  $: progressWidth = `${Math.round(solutionQuality * 100)}%`;

  onMount(() => {
    void refreshSolution();
    pollHandle = window.setInterval(() => void refreshSolution(), 2500);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refreshSolution() {
    if (!targetId) {
      solution = {};
      return;
    }

    try {
      const response = await wsClient.sendShipCommand("get_target_solution", {});
      solution = asRecord(response) ?? {};
    } catch {
      solution = {};
    }
  }

  async function designateTarget() {
    if (!targetId) return;
    await wsClient.sendShipCommand("designate_target", { contact_id: targetId });
    await refreshSolution();
  }

  async function unlockTarget() {
    await wsClient.sendShipCommand("unlock_target", {});
    solution = {};
  }
</script>

<Panel title="Targeting Display" domain="weapons" priority={targeting.lockState === "locked" ? "primary" : "secondary"} className="targeting-display-panel">
  <div class="shell">
    <div class="header">
      <div>
        <div class="label">Target</div>
        <strong>{targetId || "NO TARGET"}</strong>
      </div>
      <div class="badge">{Math.round(solutionQuality * 100)}%</div>
    </div>

    <div class="pipeline">
      {#each stages as stage, index}
        <div class="stage" class:active={index < targeting.stage} class:current={index === Math.max(0, targeting.stage - 1)}>
          <span>{stage}</span>
        </div>
      {/each}
    </div>

    <div class="confidence-track">
      <div class="confidence-fill" style={`width: ${progressWidth};`}></div>
    </div>

    <div class="metrics">
      <div class="metric"><span>Lock state</span><strong>{targeting.lockState.toUpperCase()}</strong></div>
      <div class="metric"><span>Range</span><strong>{formatDistance(toNumber(solution.range, NaN))}</strong></div>
      <div class="metric"><span>ETA</span><strong>{formatDuration(toNumber(solution.time_to_cpa, toNumber(solution.time_of_flight, NaN)))}</strong></div>
      <div class="metric"><span>Subsystem</span><strong>{toStringValue(solution.target_subsystem, targeting.subsystem).toUpperCase()}</strong></div>
    </div>

    <div class="actions">
      <button disabled={!targetId} on:click={designateTarget}>DESIGNATE</button>
      <button disabled={!lockedTargetId} on:click={unlockTarget}>UNLOCK</button>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .header,
  .actions {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .label,
  .metric span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong,
  .badge {
    font-family: var(--font-mono);
  }

  .badge {
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid rgba(var(--tier-accent-rgb), 0.4);
  }

  .pipeline {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 6px;
  }

  .stage {
    padding: 8px;
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid var(--border-subtle);
  }

  .stage.active {
    border-color: rgba(var(--tier-accent-rgb), 0.35);
    background: rgba(var(--tier-accent-rgb), 0.1);
  }

  .stage.current {
    box-shadow: inset 0 0 0 1px rgba(var(--tier-accent-rgb), 0.35);
  }

  .stage span {
    font-size: 0.72rem;
  }

  .confidence-track {
    height: 10px;
    border-radius: 999px;
    background: var(--bg-input);
    overflow: hidden;
  }

  .confidence-fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.3), var(--tier-accent));
  }

  .metrics {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .metric {
    display: grid;
    gap: 4px;
    padding: 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
  }
</style>
