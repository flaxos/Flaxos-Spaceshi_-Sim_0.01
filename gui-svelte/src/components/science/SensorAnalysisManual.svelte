<script lang="ts">
  import { selectedScienceContactId } from "../../lib/stores/scienceUi.js";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    confidencePercent,
    currentNoiseFloor,
    findScienceContact,
    formatDistance,
    formatSquareMeters,
    formatVectorShort,
    formatWatts,
    getScienceContacts,
    getScienceShip,
    probeRows,
  } from "./scienceData.js";

  interface HistoryRow {
    timestamp: number;
    contactId: string;
    classification: string;
    confidence: number;
  }

  let history: HistoryRow[] = [];
  let lastHistoryKey = "";
  let feedback = "";

  $: ship = getScienceShip($gameState);
  $: contacts = getScienceContacts(ship);
  $: if (!$selectedScienceContactId && contacts.length) selectedScienceContactId.set(contacts[0].id);
  $: contact = findScienceContact(ship, $selectedScienceContactId);
  $: probes = probeRows(ship);
  $: noiseFloor = currentNoiseFloor(ship);

  $: if (contact) {
    const key = `${contact.id}:${contact.classification}:${Math.round(contact.confidence * 100)}`;
    if (key !== lastHistoryKey) {
      lastHistoryKey = key;
      history = [
        {
          timestamp: Date.now() / 1000,
          contactId: contact.id,
          classification: contact.classification,
          confidence: confidencePercent(contact),
        },
        ...history,
      ].slice(0, 8);
    }
  }

  async function deployProbe() {
    if (!contact) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("deploy_probe", {
        bearing: { azimuth: contact.bearing, elevation: 0 },
      });
      feedback = `Probe deployed toward ${contact.id}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Probe deploy failed";
    }
  }

  async function recallProbe() {
    const activeProbe = probes.find((probe) => probe.active);
    if (!activeProbe) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("recall_probe", { probe_id: activeProbe.id });
      feedback = `Probe ${String(activeProbe.id)} recalled`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Probe recall failed";
    }
  }
</script>

<Panel title="Manual Sensor Analysis" domain="sensor" priority="secondary" className="sensor-analysis-manual">
  <div class="shell">
    <label class="field">
      <span>Contact</span>
      <select bind:value={$selectedScienceContactId}>
        <option value="">Select contact</option>
        {#each contacts as row}
          <option value={row.id}>{row.id} · {row.classification}</option>
        {/each}
      </select>
    </label>

    <section class="data-card">
      <div class="data-grid">
        <span>IR Signature</span>
        <strong>{formatWatts(contact?.irWatts ?? null)}</strong>
        <span>Radar Cross Section</span>
        <strong>{formatSquareMeters(contact?.rcsSquareMeters ?? null)}</strong>
        <span>Noise Floor</span>
        <strong>{formatWatts(noiseFloor)}</strong>
        <span>Detection Confidence</span>
        <strong>{Math.round(confidencePercent(contact))}%</strong>
        <span>Range</span>
        <strong>{formatDistance(contact?.distance ?? null)}</strong>
        <span>Velocity Vector</span>
        <strong>{contact ? formatVectorShort(contact.velocity) : "--"}</strong>
      </div>
    </section>

    <section class="history-card">
      <div class="head">
        <span>Classification History</span>
        <strong>{history.length}</strong>
      </div>
      {#if history.length === 0}
        <div class="empty">No classification history.</div>
      {:else}
        <div class="history-table">
          {#each history as row}
            <div>{new Date(row.timestamp * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
            <div>{row.contactId}</div>
            <div>{row.classification}</div>
            <div>{Math.round(row.confidence)}%</div>
          {/each}
        </div>
      {/if}
    </section>

    <section class="probe-card">
      <div class="head">
        <span>Probe Control</span>
        <strong>{probes.length} active</strong>
      </div>
      <div class="button-row">
        <button type="button" disabled={!contact} on:click={deployProbe}>DEPLOY PROBE</button>
        <button type="button" disabled={!probes.find((probe) => probe.active)} on:click={recallProbe}>RECALL PROBE</button>
      </div>
    </section>

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

  .field,
  .data-card,
  .history-card,
  .probe-card,
  .feedback {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .field {
    padding: 0;
    border: none;
    background: none;
  }

  .head,
  .button-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .field span,
  .head span,
  .empty,
  .feedback,
  .history-table {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
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

  .data-grid,
  .history-table {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 6px 12px;
  }

  .history-table {
    grid-template-columns: 70px 1fr 1fr 56px;
  }

  .button-row button {
    flex: 1;
  }

  .feedback {
    color: var(--status-info);
  }
</style>
