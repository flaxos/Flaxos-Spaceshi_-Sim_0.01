<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { asRecord, formatDistance, toNumber, toStringValue } from "./opsData.js";

  interface DroneStatus {
    capacity: number;
    stored_count: number;
    active_count: number;
    stored_drones: Array<Record<string, unknown>>;
    active_drones: Array<Record<string, unknown>>;
  }

  const LABELS: Record<string, string> = {
    drone_sensor: "Sensor",
    drone_combat: "Combat",
    drone_decoy: "Decoy",
  };

  let status: DroneStatus = {
    capacity: 0,
    stored_count: 0,
    active_count: 0,
    stored_drones: [],
    active_drones: [],
  };

  let feedback = "";
  let pollHandle: number | null = null;

  $: counts = Object.entries(
    status.stored_drones.reduce<Record<string, number>>((acc, item) => {
      const type = toStringValue(asRecord(item)?.drone_type, "unknown");
      acc[type] = (acc[type] ?? 0) + 1;
      return acc;
    }, {}),
  );

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 2000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    try {
      const response = await wsClient.sendShipCommand("drone_status", {});
      const record = asRecord(response);
      status = {
        capacity: toNumber(record?.capacity, 0),
        stored_count: toNumber(record?.stored_count, 0),
        active_count: toNumber(record?.active_count, 0),
        stored_drones: Array.isArray(record?.stored_drones) ? record?.stored_drones as Array<Record<string, unknown>> : [],
        active_drones: Array.isArray(record?.active_drones) ? record?.active_drones as Array<Record<string, unknown>> : [],
      };
    } catch {
      // best effort
    }
  }

  async function launchDrone(droneType: string) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("launch_drone", { drone_type: droneType });
      feedback = `${LABELS[droneType] ?? droneType} drone launch requested`;
      void refresh();
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Launch failed";
    }
  }

  async function recallDrone(droneId: string) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("recall_drone", { drone_id: droneId });
      feedback = `Recall ordered for ${droneId}`;
      void refresh();
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Recall failed";
    }
  }
</script>

<Panel title="Drone Control" domain="power" priority="secondary" className="drone-control-panel">
  <div class="shell">
    <section class="summary-card">
      <div><span>Capacity</span><strong>{status.capacity}</strong></div>
      <div><span>Stored</span><strong>{status.stored_count}</strong></div>
      <div><span>Active</span><strong>{status.active_count}</strong></div>
    </section>

    <section class="stored-card">
      <div class="section-title">Drone Bay</div>
      {#if counts.length === 0}
        <div class="empty">No drones in bay.</div>
      {:else}
        {#each counts as [droneType, count]}
          <div class="stored-row">
            <strong>{LABELS[droneType] ?? droneType}</strong>
            <span>{count} ready</span>
            <button type="button" disabled={count <= 0} on:click={() => launchDrone(droneType)}>LAUNCH</button>
          </div>
        {/each}
      {/if}
    </section>

    <section class="active-card">
      <div class="section-title">Active Drones</div>
      {#if status.active_drones.length === 0}
        <div class="empty">No deployed drones.</div>
      {:else}
        {#each status.active_drones as drone}
          <div class="active-row">
            <div class="active-meta">
              <strong>{toStringValue(drone.label, toStringValue(drone.drone_id, "Drone"))}</strong>
              <span>{toStringValue(drone.ai_role, "unknown").toUpperCase()}</span>
            </div>
            <div class="active-stats">
              <span>Fuel {toNumber(drone.fuel_pct, 0).toFixed(0)}%</span>
              <span>Hull {toNumber(drone.hull_pct, 0).toFixed(0)}%</span>
              <span>{formatDistance(toNumber(drone.distance_m, 0))}</span>
            </div>
            <button type="button" on:click={() => recallDrone(toStringValue(drone.drone_id))}>RECALL</button>
          </div>
        {/each}
      {/if}
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

  .summary-card,
  .stored-card,
  .active-card,
  .empty,
  .feedback {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .summary-card {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .stored-row,
  .active-row,
  .active-meta,
  .active-stats {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .active-row {
    display: grid;
    gap: 6px;
  }

  .section-title,
  .summary-card span,
  .stored-row span,
  .active-stats,
  .active-meta span,
  .empty,
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

  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  .feedback {
    color: var(--status-info);
  }
</style>
