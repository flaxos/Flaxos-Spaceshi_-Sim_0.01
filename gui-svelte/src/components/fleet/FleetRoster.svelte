<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { fleetIdFromRecord, fleetShipsFromStatus, statusClass, type FleetShipRow } from "./fleetData.js";

  let fleetRecord: Record<string, unknown> = {};
  let ships: FleetShipRow[] = [];
  let newFleetName = "";
  let shipToAdd = "";
  let feedback = "";
  let pollHandle: number | null = null;

  $: fleetId = fleetIdFromRecord(fleetRecord);

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 4000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    try {
      const response = await wsClient.sendShipCommand("fleet_status", {});
      fleetRecord = (response as Record<string, unknown>) ?? {};
      ships = fleetShipsFromStatus(response);
    } catch {
      fleetRecord = {};
      ships = [];
    }
  }

  async function createFleet() {
    if (!newFleetName.trim()) return;
    feedback = "";
    const fleet_id = globalThis.crypto?.randomUUID?.() ?? `fleet-${Date.now()}`;
    try {
      await wsClient.sendShipCommand("fleet_create", { fleet_id, name: newFleetName.trim() });
      newFleetName = "";
      feedback = "Fleet created";
      await refresh();
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Fleet create failed";
    }
  }

  async function addShip() {
    if (!shipToAdd.trim() || !fleetId) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("fleet_add_ship", {
        fleet_id: fleetId,
        target_ship: shipToAdd.trim(),
      });
      shipToAdd = "";
      feedback = "Ship added to fleet";
      await refresh();
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Add ship failed";
    }
  }
</script>

<Panel title="Fleet Roster" domain="weapons" priority="secondary" className="fleet-roster-panel">
  <div class="shell">
    {#if !fleetId}
      <section class="entry-card">
        <div class="head">
          <span>No fleet assigned</span>
          <strong>CREATE</strong>
        </div>
        <input bind:value={newFleetName} placeholder="Task force name" maxlength="40" />
        <button type="button" disabled={!newFleetName.trim()} on:click={createFleet}>CREATE FLEET</button>
      </section>
    {:else}
      <section class="entry-card">
        <div class="head">
          <span>Fleet</span>
          <strong>{fleetId}</strong>
        </div>
        <div class="adder">
          <input bind:value={shipToAdd} placeholder="Ship ID" />
          <button type="button" disabled={!shipToAdd.trim()} on:click={addShip}>ADD SHIP</button>
        </div>
      </section>

      {#if ships.length === 0}
        <div class="empty">Fleet exists but no ship telemetry is currently available.</div>
      {:else}
        <div class="ship-list">
          {#each ships as row}
            <section class="ship-card {statusClass(row.status)}">
              <div class="card-head">
                <strong>{row.name}</strong>
                {#if row.isFlagship}
                  <span class="flag">FLAG</span>
                {/if}
              </div>
              <div class="meta">
                <span>{row.className.toUpperCase()}</span>
                <span>{row.status.toUpperCase()}</span>
              </div>
              <div class="track"><div class="fill" style={`width:${row.hullPercent.toFixed(1)}%;`}></div></div>
              <div class="meta">
                <span>Hull</span>
                <span>{Math.round(row.hullPercent)}%</span>
              </div>
            </section>
          {/each}
        </div>
      {/if}
    {/if}

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

  .entry-card,
  .ship-card,
  .feedback,
  .empty {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .card-head,
  .meta,
  .adder {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .ship-list {
    display: grid;
    gap: 8px;
  }

  .head span,
  .meta,
  .feedback,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  strong,
  input,
  button {
    font-family: var(--font-mono);
  }

  strong {
    color: var(--text-primary);
  }

  input,
  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-size: 0.72rem;
  }

  .adder input {
    flex: 1;
  }

  .track {
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(0, 255, 136, 0.18), rgba(0, 255, 136, 0.85));
  }

  .ship-card.warning {
    border-color: rgba(255, 184, 77, 0.35);
  }

  .ship-card.critical {
    border-color: rgba(255, 68, 68, 0.35);
  }

  .flag {
    padding: 2px 6px;
    border-radius: 999px;
    border: 1px solid rgba(255, 212, 107, 0.4);
    color: #ffd46b;
    font-size: 0.65rem;
  }

  .feedback {
    color: var(--status-info);
  }
</style>
