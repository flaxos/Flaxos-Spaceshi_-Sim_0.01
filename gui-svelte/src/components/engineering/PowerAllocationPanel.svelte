<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { describeCommandFailure, isCommandRejected } from "../../lib/ws/commandResponse.js";
  import {
    POWER_CATEGORY_ORDER,
    POWER_CATEGORY_TO_BUS,
    asRecord,
    formatKw,
    getDrawProfileBuses,
    getEngineeringShip,
    getPowerCategoryWeights,
    translateCategoryWeightsToBusAllocation,
    toNumber,
    type PowerCategory,
  } from "./engineeringData.js";

  let profile: Record<string, unknown> | null = null;
  let pollHandle: number | null = null;
  let dragging: PowerCategory | null = null;
  let dirty = false;
  let feedback = "";
  let weights: Record<PowerCategory, number> = {
    propulsion: 0.25,
    weapons: 0.15,
    sensors: 0.15,
    comms: 0.05,
    life_support: 0.05,
  };

  $: ship = getEngineeringShip($gameState);
  $: sourceWeights = getPowerCategoryWeights(ship);
  $: buses = getDrawProfileBuses(asRecord(profile));
  $: cpuAssistTier = $tier === "cpu-assist";
  $: if (!dirty && dragging == null) weights = { ...sourceWeights };

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 3000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    if (cpuAssistTier || document.hidden) return;
    try {
      const response = await wsClient.sendShipCommand("get_draw_profile", {});
      const record = asRecord(response);
      profile = (asRecord(record?.data) ?? record) as Record<string, unknown>;
    } catch {
      // best effort
    }
  }

  function setDraft(category: PowerCategory, value: number) {
    dirty = true;
    weights = {
      ...weights,
      [category]: Math.max(0, Math.min(1, value / 100)),
    };
  }

  async function commit(category: PowerCategory) {
    dragging = null;
    dirty = true;
    feedback = "";
    try {
      const response = await wsClient.sendShipCommand("set_power_allocation", {
        allocation: translateCategoryWeightsToBusAllocation(weights),
      });
      if (isCommandRejected(response)) {
        feedback = `Error: ${describeCommandFailure(response)}`;
        return;
      }
      feedback = `${category.replaceAll("_", " ")} allocation transmitted`;
      dirty = false;
      void refresh();
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Allocation update failed";
    }
  }

  function busInfo(category: PowerCategory) {
    return asRecord(buses[POWER_CATEGORY_TO_BUS[category]]) ?? {};
  }
</script>

<Panel title="Power Allocation" domain="power" priority={$tier === "manual" || $tier === "raw" ? "primary" : "secondary"} className="power-allocation-panel">
  <div class="shell">
    {#if cpuAssistTier}
      <div class="assist-note">Auto-ops manages live power allocation in CPU-ASSIST mode.</div>
      {#each POWER_CATEGORY_ORDER as category}
        <div class="readonly-card">
          <div class="head">
            <strong>{category.replaceAll("_", " ").toUpperCase()}</strong>
            <span>{Math.round((sourceWeights[category] ?? 0) * 100)}%</span>
          </div>
          <div class="track">
            <div class="fill" style={`width:${Math.round((sourceWeights[category] ?? 0) * 100)}%;`}></div>
          </div>
        </div>
      {/each}
    {:else}
      {#each POWER_CATEGORY_ORDER as category}
        {@const info = busInfo(category)}
        <div class="alloc-card">
          <div class="head">
            <strong>{category.replaceAll("_", " ").toUpperCase()}</strong>
            <span>{POWER_CATEGORY_TO_BUS[category].toUpperCase()}</span>
          </div>
          <div class="slider-row">
            <input
              type="range"
              min="0"
              max="100"
              step="1"
              value={Math.round((weights[category] ?? 0) * 100)}
              on:mousedown={() => dragging = category}
              on:touchstart={() => dragging = category}
              on:input={(event) => setDraft(category, Number((event.currentTarget as HTMLInputElement).value))}
              on:change={() => commit(category)}
            />
            <strong>{Math.round((weights[category] ?? 0) * 100)}%</strong>
          </div>
          <div class="bus-meta">
            <span>Supply {formatKw(toNumber(info.available_kw))}</span>
            <span>Demand {formatKw(toNumber(info.requested_kw))}</span>
          </div>
        </div>
      {/each}
      {#if feedback}
        <div class="feedback">{feedback}</div>
      {/if}
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .alloc-card,
  .readonly-card,
  .assist-note,
  .feedback {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .bus-meta,
  .slider-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .head span,
  .bus-meta,
  .assist-note,
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

  input[type="range"] {
    flex: 1;
  }

  .track {
    height: 10px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.35), var(--tier-accent));
  }

  .feedback {
    color: var(--status-info);
  }
</style>
