<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { describeCommandFailure, isCommandRejected } from "../../lib/ws/commandResponse.js";
  import {
    computeEta,
    distance,
    extractShipState,
    formatDistance,
    formatDuration,
    getOrientation,
    getPosition,
    getThrottle,
    getVelocity,
    getWaypoint,
    magnitude,
    normalizeAngle,
  } from "./helmData.js";

  let throttlePercent = 0;
  let draftPitch = 0;
  let draftYaw = 0;
  let draftRoll = 0;
  let courseX = "";
  let courseY = "";
  let courseZ = "";
  let feedback = "";
  let throttleTimer: number | null = null;

  $: ship = extractShipState($gameState);
  $: currentPosition = getPosition(ship);
  $: currentVelocity = getVelocity(ship);
  $: currentHeading = getOrientation(ship);
  $: waypoint = getWaypoint(ship);
  $: waypointDistance = waypoint ? distance(waypoint, currentPosition) : 0;
  $: waypointEta = waypoint ? computeEta(waypointDistance, magnitude(currentVelocity)) : null;
  $: throttlePercent = Math.round(getThrottle(ship) * 100);
  $: draftPitch = currentHeading.pitch;
  $: draftYaw = currentHeading.yaw;
  $: draftRoll = currentHeading.roll;

  function scheduleThrottle(value: number) {
    throttlePercent = value;
    if (throttleTimer != null) window.clearTimeout(throttleTimer);
    throttleTimer = window.setTimeout(() => {
      void wsClient.sendShipCommand("set_thrust", { thrust: value / 100 });
    }, 40);
  }

  async function applyOrientation() {
    feedback = "";
    try {
      const response = await wsClient.sendShipCommand("set_orientation", {
        pitch: draftPitch,
        yaw: draftYaw,
        roll: draftRoll,
      });
      if (isCommandRejected(response)) {
        feedback = `Error: ${describeCommandFailure(response)}`;
      }
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Heading command failed";
    }
  }

  async function uploadCourse() {
    if (![courseX, courseY, courseZ].every((value) => value.trim() !== "")) {
      feedback = "Enter waypoint coordinates first";
      return;
    }

    try {
      const response = await wsClient.sendShipCommand("set_course", {
        x: Number(courseX),
        y: Number(courseY),
        z: Number(courseZ),
        stop: true,
      });
      if (isCommandRejected(response)) {
        feedback = `Error: ${describeCommandFailure(response)}`;
        return;
      }
      feedback = "Waypoint uploaded";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Course upload failed";
    }
  }

  function nudgeOrientation(axis: "pitch" | "yaw" | "roll", amount: number) {
    if (axis === "pitch") draftPitch = Math.max(-90, Math.min(90, draftPitch + amount));
    if (axis === "yaw") draftYaw = normalizeAngle(draftYaw + amount);
    if (axis === "roll") draftRoll = normalizeAngle(draftRoll + amount);
    void applyOrientation();
  }

  function handleKeydown(event: KeyboardEvent) {
    if ($tier !== "manual") return;
    if (event.target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;

    const step = 4;

    switch (event.key.toLowerCase()) {
      case "w":
        event.preventDefault();
        nudgeOrientation("pitch", step);
        break;
      case "s":
        event.preventDefault();
        nudgeOrientation("pitch", -step);
        break;
      case "a":
        event.preventDefault();
        nudgeOrientation("yaw", -step);
        break;
      case "d":
        event.preventDefault();
        nudgeOrientation("yaw", step);
        break;
      case "q":
        event.preventDefault();
        nudgeOrientation("roll", -step);
        break;
      case "e":
        event.preventDefault();
        nudgeOrientation("roll", step);
        break;
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<Panel title="Manual Flight" domain="helm" priority={$tier === "manual" ? "primary" : "secondary"} className="manual-flight-panel">
  <div class="shell">
    <div class="throttle">
      <div class="row-head">
        <span>Throttle</span>
        <strong>{throttlePercent}%</strong>
      </div>
      <input type="range" min="0" max="100" step="1" value={throttlePercent} on:input={(event) => scheduleThrottle(Number((event.currentTarget as HTMLInputElement).value))} />
      <input type="number" min="0" max="100" step="1" value={throttlePercent} on:change={(event) => scheduleThrottle(Number((event.currentTarget as HTMLInputElement).value))} />
    </div>

    {#if $tier !== "arcade"}
      <div class="heading-grid">
        <div class="axis">
          <span>Pitch</span>
          <div class="axis-row">
            <button type="button" on:click={() => nudgeOrientation("pitch", -5)}>-</button>
            <input type="number" bind:value={draftPitch} on:change={applyOrientation} />
            <button type="button" on:click={() => nudgeOrientation("pitch", 5)}>+</button>
          </div>
        </div>
        <div class="axis">
          <span>Yaw</span>
          <div class="axis-row">
            <button type="button" on:click={() => nudgeOrientation("yaw", -5)}>-</button>
            <input type="number" bind:value={draftYaw} on:change={applyOrientation} />
            <button type="button" on:click={() => nudgeOrientation("yaw", 5)}>+</button>
          </div>
        </div>
        <div class="axis">
          <span>Roll</span>
          <div class="axis-row">
            <button type="button" on:click={() => nudgeOrientation("roll", -5)}>-</button>
            <input type="number" bind:value={draftRoll} on:change={applyOrientation} />
            <button type="button" on:click={() => nudgeOrientation("roll", 5)}>+</button>
          </div>
        </div>
      </div>
    {/if}

    <div class="waypoint">
      <div class="row-head">
        <span>Waypoint</span>
        <strong>{waypoint ? "ACTIVE" : "NONE"}</strong>
      </div>
      <div class="waypoint-grid">
        <div><span>Range</span><strong>{waypoint ? formatDistance(waypointDistance) : "--"}</strong></div>
        <div><span>ETA</span><strong>{waypointEta ? formatDuration(waypointEta) : "--"}</strong></div>
      </div>
    </div>

    {#if $tier !== "arcade"}
      <div class="course-grid">
        <label><span>X</span><input bind:value={courseX} placeholder="0" /></label>
        <label><span>Y</span><input bind:value={courseY} placeholder="0" /></label>
        <label><span>Z</span><input bind:value={courseZ} placeholder="0" /></label>
      </div>
      <button on:click={uploadCourse}>SET COURSE</button>
    {/if}

    {#if $tier === "manual"}
      <div class="keyboard-strip">Keyboard: W/S pitch · A/D yaw · Q/E roll</div>
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

  .throttle,
  .waypoint,
  .axis,
  .course-grid label {
    display: grid;
    gap: 6px;
  }

  .row-head,
  .waypoint-grid {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .row-head span,
  .axis span,
  .course-grid span,
  .keyboard-strip {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .row-head strong,
  .waypoint-grid strong {
    font-family: var(--font-mono);
  }

  .heading-grid,
  .course-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .axis-row {
    display: grid;
    grid-template-columns: 40px 1fr 40px;
    gap: 4px;
  }

  .keyboard-strip,
  .feedback {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    background: rgba(var(--tier-accent-rgb), 0.08);
  }

  .feedback {
    color: var(--text-primary);
  }

  @media (max-width: 900px) {
    .heading-grid,
    .course-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
