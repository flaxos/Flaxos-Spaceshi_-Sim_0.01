<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedHelmTargetId } from "../../lib/stores/helmUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    extractShipState,
    getContacts,
    getOrientation,
    normalizeAngle,
    toStringValue,
  } from "./helmData.js";

  let pitchRate = 0;
  let yawRate = 0;
  let rollRate = 0;
  let feedback = "";

  $: ship = extractShipState($gameState);
  $: contacts = getContacts(ship);
  $: activeTargetId = $selectedHelmTargetId || toStringValue(ship.target_id);
  $: heading = getOrientation(ship);

  async function setRate(nextPitch = pitchRate, nextYaw = yawRate, nextRoll = rollRate) {
    pitchRate = nextPitch;
    yawRate = nextYaw;
    rollRate = nextRoll;
    try {
      await wsClient.sendShipCommand("set_angular_velocity", {
        pitch: pitchRate,
        yaw: yawRate,
        roll: rollRate,
      });
    } catch (error) {
      feedback = error instanceof Error ? error.message : "RCS rate command failed";
    }
  }

  async function flip180() {
    await wsClient.sendShipCommand("set_orientation", {
      pitch: heading.pitch,
      yaw: normalizeAngle(heading.yaw + 180),
      roll: heading.roll,
    });
  }

  async function pointAtTarget() {
    if (!activeTargetId) {
      feedback = "Select a target first";
      return;
    }
    await wsClient.sendShipCommand("point_at", { target: activeTargetId });
  }

  async function cancelRotation() {
    await wsClient.sendShipCommand("set_orientation", {
      pitch: heading.pitch,
      yaw: heading.yaw,
      roll: heading.roll,
    });
    await killRotation();
  }

  async function killRotation() {
    await setRate(0, 0, 0);
  }

  function onTargetChange(event: Event) {
    selectedHelmTargetId.set((event.currentTarget as HTMLSelectElement).value);
  }
</script>

<Panel title="RCS Controls" domain="helm" priority="secondary" className="rcs-controls-panel">
  <div class="shell">
    <label>
      Point-at target
      <select on:change={onTargetChange} value={activeTargetId}>
        <option value="">No target selected</option>
        {#each contacts as contact}
          <option value={contact.id}>{contact.id} · {contact.name}</option>
        {/each}
      </select>
    </label>

    <div class="quick-grid">
      <button on:click={flip180}>FLIP 180</button>
      <button on:click={pointAtTarget} disabled={!activeTargetId}>POINT AT TARGET</button>
      <button on:click={cancelRotation}>CANCEL ROTATION</button>
      <button on:click={killRotation}>KILL ROTATION</button>
    </div>

    <div class="slider-grid">
      <label><span>Pitch rate</span><input type="range" min="-20" max="20" step="0.5" value={pitchRate} on:input={(event) => setRate(Number((event.currentTarget as HTMLInputElement).value), yawRate, rollRate)} /><strong>{pitchRate.toFixed(1)}°/s</strong></label>
      <label><span>Yaw rate</span><input type="range" min="-20" max="20" step="0.5" value={yawRate} on:input={(event) => setRate(pitchRate, Number((event.currentTarget as HTMLInputElement).value), rollRate)} /><strong>{yawRate.toFixed(1)}°/s</strong></label>
      <label><span>Roll rate</span><input type="range" min="-20" max="20" step="0.5" value={rollRate} on:input={(event) => setRate(pitchRate, yawRate, Number((event.currentTarget as HTMLInputElement).value))} /><strong>{rollRate.toFixed(1)}°/s</strong></label>
    </div>

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .shell,
  .slider-grid,
  label {
    display: grid;
    gap: var(--space-sm);
  }

  .shell {
    padding: var(--space-sm);
  }

  .quick-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-xs);
  }

  label span {
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    color: var(--text-secondary);
    letter-spacing: 0.06em;
  }

  label strong {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-primary);
  }

  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }
</style>
