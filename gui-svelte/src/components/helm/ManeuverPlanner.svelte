<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedHelmTargetId } from "../../lib/stores/helmUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { describeCommandFailure, isCommandRejected } from "../../lib/ws/commandResponse.js";
  import {
    asRecord,
    clamp,
    computeRelativeSpeed,
    extractShipState,
    findContact,
    formatDuration,
    formatSpeed,
    getContacts,
    getMaxAccel,
    getOrientation,
    getVelocity,
    magnitude,
    normalizeAngle,
    toStringValue,
  } from "./helmData.js";

  let executionMode: "autopilot" | "plan" | "burn" = "autopilot";
  let burnDuration = 18;
  let burnThrottle = 0.55;
  let feedback = "";

  $: ship = extractShipState($gameState);
  $: contacts = getContacts(ship);
  $: targetId = $selectedHelmTargetId || toStringValue(ship.target_id);
  $: contact = targetId ? findContact(ship, targetId) : null;
  $: speed = magnitude(getVelocity(ship));
  $: relativeSpeed = computeRelativeSpeed(ship, targetId);
  $: maxAccel = Math.max(getMaxAccel(ship), 0.01);
  $: range = contact?.distance ?? 0;
  $: heading = getOrientation(ship);
  $: rcsState = asRecord(asRecord(ship.systems)?.rcs);
  $: rcsController = asRecord(rcsState?.controller);
  $: flipTime = 180 / Math.max(toNumber(rcsController?.max_rate, 30), 1) * 1.4;
  $: flipBurnEta = range > 0 ? 2 * Math.sqrt(range / maxAccel) + flipTime : 0;
  $: interceptTime = range > 0 ? range / Math.max(relativeSpeed ?? speed, 20) : 0;
  $: deltaVCost = range > 0 ? Math.sqrt(2 * range * maxAccel) : 0;

  function toNumber(value: unknown, fallback = 0): number {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }

  function onTargetChange(event: Event) {
    selectedHelmTargetId.set((event.currentTarget as HTMLSelectElement).value);
  }

  function retrogradeHeading() {
    const velocity = getVelocity(ship);
    if (magnitude(velocity) <= 0.01) {
      return { pitch: heading.pitch, yaw: normalizeAngle(heading.yaw + 180) };
    }
    const opposite = { x: -velocity.x, y: -velocity.y, z: -velocity.z };
    const horizontal = Math.sqrt(opposite.x * opposite.x + opposite.y * opposite.y);
    return {
      pitch: Math.atan2(opposite.z, Math.max(horizontal, 0.001)) * 180 / Math.PI,
      yaw: normalizeAngle(Math.atan2(opposite.y, opposite.x) * 180 / Math.PI),
    };
  }

  function buildPlan() {
    return {
      name: targetId ? `Intercept ${targetId}` : "Helm burn plan",
      type: "helm_sequence",
      source: "svelte_helm",
      target: targetId ? { id: targetId } : undefined,
      steps: [
        { action: "point_at", detail: targetId ? `Acquire ${targetId}` : "Acquire burn heading" },
        { action: "burn", detail: `Burn ${Math.round(burnThrottle * 100)}% for ${burnDuration}s` },
        { action: "hold", detail: "Stabilize and reassess" },
      ],
    };
  }

  async function executePlan() {
    feedback = "";
    try {
      if (executionMode === "autopilot") {
        if (!targetId) {
          feedback = "Select a target for intercept autopilot";
          return;
        }
        const response = await wsClient.sendShipCommand("autopilot", {
          enable: true,
          program: "intercept",
          target: targetId,
        });
        if (isCommandRejected(response)) {
          feedback = `Error: ${describeCommandFailure(response)}`;
          return;
        }
        feedback = `Intercept autopilot engaged for ${targetId}`;
        return;
      }

      if (executionMode === "plan") {
        const response = await wsClient.sendShipCommand("set_plan", { plan: buildPlan() });
        if (isCommandRejected(response)) {
          feedback = `Error: ${describeCommandFailure(response)}`;
          return;
        }
        feedback = "Flight plan queued";
        return;
      }

      const retro = retrogradeHeading();
      const response = await wsClient.sendShipCommand("execute_burn", {
        duration: burnDuration,
        throttle: burnThrottle,
        pitch: retro.pitch,
        yaw: retro.yaw,
      });
      if (isCommandRejected(response)) {
        feedback = `Error: ${describeCommandFailure(response)}`;
        return;
      }
      feedback = "Timed burn queued";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Planner execution failed";
    }
  }
</script>

<Panel title="Maneuver Planner" domain="helm" priority="secondary" className="maneuver-planner-panel">
  <div class="shell">
    <label>
      Target
      <select value={targetId} on:change={onTargetChange}>
        <option value="">Select a contact</option>
        {#each contacts as entry}
          <option value={entry.id}>{entry.id} · {entry.name}</option>
        {/each}
      </select>
    </label>

    <div class="metrics">
      <div><span>Flip-and-burn ETA</span><strong>{flipBurnEta ? formatDuration(flipBurnEta) : "--"}</strong></div>
      <div><span>Intercept time</span><strong>{interceptTime ? formatDuration(interceptTime) : "--"}</strong></div>
      <div><span>Delta-V cost</span><strong>{deltaVCost ? formatSpeed(deltaVCost) : "--"}</strong></div>
    </div>

    <div class="controls">
      <label><span>Execute as</span><select bind:value={executionMode}><option value="autopilot">Autopilot</option><option value="plan">Queued plan</option><option value="burn">Timed burn</option></select></label>
      <label><span>Burn duration</span><input type="range" min="2" max="60" step="1" bind:value={burnDuration} /><strong>{burnDuration}s</strong></label>
      <label><span>Throttle</span><input type="range" min="0.1" max="1" step="0.05" bind:value={burnThrottle} /><strong>{Math.round(burnThrottle * 100)}%</strong></label>
    </div>

    <button on:click={executePlan}>
      {executionMode === "autopilot" ? "EXECUTE INTERCEPT" : executionMode === "plan" ? "QUEUE FLIGHT PLAN" : "EXECUTE BURN"}
    </button>

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .shell,
  .metrics,
  .controls,
  label {
    display: grid;
    gap: var(--space-sm);
  }

  .shell {
    padding: var(--space-sm);
  }

  .metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metrics div {
    display: grid;
    gap: 4px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.02);
  }

  .metrics span,
  label span,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .metrics strong,
  label strong {
    font-family: var(--font-mono);
  }

  @media (max-width: 900px) {
    .metrics {
      grid-template-columns: 1fr;
    }
  }
</style>
