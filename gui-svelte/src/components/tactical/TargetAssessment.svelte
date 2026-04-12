<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { extractShipState, getLockedTargetId, getAssessmentSummary, asRecord } from "./tacticalData.js";

  let assessment: Record<string, unknown> | null = null;
  let pollHandle: number | null = null;

  $: ship = extractShipState($gameState);
  $: lockedTargetId = getLockedTargetId(ship);
  $: summary = getAssessmentSummary(assessment);

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 3000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    if (!lockedTargetId) {
      assessment = null;
      return;
    }
    try {
      assessment = asRecord(await wsClient.sendShipCommand("assess_damage", {}));
    } catch {
      assessment = null;
    }
  }
</script>

<Panel title="Target Assessment" domain="sensor" priority="secondary" className="target-assessment-panel">
  <div class="shell">
    <div class="hull-bar">
      <span>Estimated hull</span>
      <strong>{Math.round(summary.hull * 100)}%</strong>
    </div>
    <div class="track"><div class="fill" style={`width: ${Math.round(summary.hull * 100)}%;`}></div></div>

    <div class="subsystems">
      {#if summary.subsystems.length === 0}
        <div class="empty">No target damage estimate available.</div>
      {:else}
        {#each summary.subsystems as subsystem}
          <div class="subsystem-row">
            <strong>{String(subsystem.name).toUpperCase()}</strong>
            <span>{subsystem.health != null && Number(subsystem.health) >= 0 ? `${Math.round(Number(subsystem.health) * 100)}%` : "--"}</span>
            <span>{String(subsystem.status ?? "unknown").toUpperCase()}</span>
          </div>
        {/each}
      {/if}
    </div>
  </div>
</Panel>

<style>
  .shell,
  .subsystems {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .hull-bar,
  .subsystem-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: var(--space-sm);
    align-items: center;
  }

  .hull-bar {
    grid-template-columns: minmax(0, 1fr) auto;
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

  span,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  strong {
    font-family: var(--font-mono);
  }
</style>
