<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedHelmTargetId } from "../../lib/stores/helmUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    clamp,
    extractShipState,
    findContact,
    formatDistance,
    formatSpeed,
    getContacts,
    getDockingSnapshot,
    getOrientation,
    headingToTarget,
    normalizeAngle,
    toStringValue,
  } from "./helmData.js";

  let feedback = "";

  $: ship = extractShipState($gameState);
  $: contacts = getContacts(ship);
  $: docking = getDockingSnapshot(ship);
  $: currentTargetId = docking.targetId || $selectedHelmTargetId || toStringValue(ship.target_id);
  $: stateLabel = docking.status === "docked" ? "docked" : docking.status === "idle" ? "free" : "approaching";
  $: contact = currentTargetId ? findContact(ship, currentTargetId) : null;
  $: guidanceHeading = contact ? headingToTarget(ship, contact.position) : null;
  $: shipHeading = getOrientation(ship);
  $: alignment = guidanceHeading
    ? clamp(100 - ((Math.abs(normalizeAngle(guidanceHeading.yaw - shipHeading.yaw)) + Math.abs(guidanceHeading.pitch - shipHeading.pitch)) / 180) * 100, 0, 100)
    : stateLabel === "docked" ? 100 : 0;

  function onTargetChange(event: Event) {
    selectedHelmTargetId.set((event.currentTarget as HTMLSelectElement).value);
  }

  async function requestDocking() {
    if (!currentTargetId) {
      feedback = "Select a contact first";
      return;
    }
    await wsClient.sendShipCommand("request_docking", { target_id: currentTargetId });
    feedback = `Docking requested with ${currentTargetId}`;
  }

  async function cancelDocking() {
    await wsClient.sendShipCommand("cancel_docking", {});
    feedback = "Docking cancelled";
  }

  async function undock() {
    await wsClient.sendShipCommand("undock", {});
    feedback = "Undocked";
  }
</script>

<Panel title="Docking" domain="helm" priority={stateLabel === "docked" ? "primary" : "secondary"} className="docking-panel">
  <div class="shell">
    <div class="status-row">
      <div class="state {stateLabel}">{stateLabel.toUpperCase()}</div>
      <div class="target">{currentTargetId || "No target"}</div>
    </div>

    <label>
      Docking target
      <select value={currentTargetId} on:change={onTargetChange} disabled={stateLabel === "docked"}>
        <option value="">Select a contact</option>
        {#each contacts as entry}
          <option value={entry.id}>{entry.id} · {entry.name}</option>
        {/each}
      </select>
    </label>

    <div class="guidance-grid">
      <div><span>Range</span><strong>{formatDistance(docking.range)}</strong></div>
      <div><span>Alignment</span><strong>{alignment.toFixed(0)}%</strong></div>
      <div><span>Rel velocity</span><strong>{formatSpeed(docking.relativeVelocity)}</strong></div>
    </div>

    {#if docking.serviceReport}
      <div class="service">
        <div class="eyebrow">Station service</div>
        <div class="guidance-grid">
          <div><span>Hull</span><strong>+{docking.serviceReport.hull_repaired ?? 0}</strong></div>
          <div><span>Fuel</span><strong>+{docking.serviceReport.fuel_added ?? 0}</strong></div>
          <div><span>Weapons</span><strong>+{docking.serviceReport.weapons_resupplied ?? 0}</strong></div>
        </div>
      </div>
    {/if}

    <div class="actions">
      <button on:click={requestDocking} disabled={stateLabel === "docked" || !currentTargetId}>REQUEST DOCK</button>
      <button on:click={cancelDocking} disabled={stateLabel === "free" || stateLabel === "docked"}>CANCEL</button>
      <button class="danger" on:click={undock} disabled={stateLabel !== "docked"}>UNDOCK</button>
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

  .status-row,
  .guidance-grid,
  .actions {
    display: grid;
    gap: var(--space-sm);
  }

  .status-row,
  .guidance-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .state,
  .target,
  .guidance-grid div,
  .service {
    padding: 10px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.02);
  }

  .state.free {
    color: var(--text-secondary);
  }

  .state.approaching {
    color: var(--status-warning);
  }

  .state.docked {
    color: var(--status-nominal);
  }

  .guidance-grid span,
  .feedback,
  .eyebrow,
  label {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .guidance-grid strong,
  .target {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .actions {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .danger {
    border-color: rgba(255, 68, 68, 0.4);
    color: var(--status-critical);
  }
</style>
