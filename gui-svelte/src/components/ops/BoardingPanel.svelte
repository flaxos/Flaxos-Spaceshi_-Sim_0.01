<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getTacticalContacts } from "../tactical/tacticalData.js";
  import {
    asRecord,
    formatPercent,
    getBoardingTelemetry,
    getOpsShip,
    toNumber,
    toStringValue,
  } from "./opsData.js";

  let status: Record<string, unknown> = {};
  let selectedTarget = "";
  let feedback = "";
  let pollHandle: number | null = null;

  $: ship = getOpsShip($gameState);
  $: contacts = getTacticalContacts(ship);
  $: telemetry = getBoardingTelemetry(ship);
  $: boarding = Object.keys(status).length ? status : telemetry;
  $: state = toStringValue(boarding.state, "idle");
  $: targetId = toStringValue(boarding.target, selectedTarget);
  $: progress = Math.max(0, Math.min(100, toNumber(boarding.progress) * 100));
  $: resistance = asRecord(boarding.resistance) ?? {};
  $: resistanceFactor = toNumber(resistance.total_factor, 1);

  onMount(() => {
    if (!selectedTarget && contacts.length) selectedTarget = contacts[0].id;
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 1500);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    try {
      const response = await wsClient.sendShipCommand("boarding_status", {});
      status = (asRecord(response) ?? {}) as Record<string, unknown>;
    } catch {
      status = {};
    }
  }

  async function beginBoarding() {
    if (!selectedTarget) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("begin_boarding", { target_id: selectedTarget });
      feedback = `Boarding started on ${selectedTarget}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Boarding start failed";
    }
  }

  async function cancelBoarding() {
    feedback = "";
    try {
      await wsClient.sendShipCommand("cancel_boarding", {});
      feedback = "Boarding cancelled";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Cancel failed";
    }
  }

  function resistanceLabel(): string {
    if (resistanceFactor <= 0.35) return "SEVERE";
    if (resistanceFactor <= 0.6) return "HIGH";
    if (resistanceFactor <= 0.85) return "MODERATE";
    return "LIGHT";
  }
</script>

<Panel title="Boarding" domain="power" priority="secondary" className="boarding-panel">
  <div class="shell">
    <section class="status-card">
      <div class="head">
        <span>Boarding State</span>
        <strong>{state.toUpperCase()}</strong>
      </div>
      <div class="track">
        <div class="fill" style={`width:${progress.toFixed(0)}%;`}></div>
      </div>
      <div class="meta">
        <span>Progress {formatPercent(progress)}</span>
        <span>{targetId || "NO TARGET"}</span>
      </div>
    </section>

    <label class="selector">
      <span>Target</span>
      <select bind:value={selectedTarget}>
        <option value="">Select target</option>
        {#each contacts as contact}
          <option value={contact.id}>{contact.id} · {contact.classification}</option>
        {/each}
      </select>
    </label>

    <div class="resistance-card">
      <div class="head">
        <span>Resistance</span>
        <strong>{resistanceLabel()}</strong>
      </div>
      <div class="meta">
        <span>Factor {resistanceFactor.toFixed(2)}</span>
        <span>Weapons {toNumber(resistance.active_weapons, 0).toFixed(0)}</span>
      </div>
    </div>

    <div class="actions">
      <button type="button" disabled={!selectedTarget || state === "boarding"} on:click={beginBoarding}>BEGIN BOARDING</button>
      <button class="secondary" type="button" disabled={state !== "boarding"} on:click={cancelBoarding}>CANCEL</button>
    </div>

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

  .status-card,
  .resistance-card,
  .feedback {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .meta,
  .actions {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .selector {
    display: grid;
    gap: 6px;
  }

  .selector span,
  .meta,
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

  select,
  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  button.secondary {
    color: var(--text-secondary);
  }

  .feedback {
    color: var(--status-info);
  }
</style>
