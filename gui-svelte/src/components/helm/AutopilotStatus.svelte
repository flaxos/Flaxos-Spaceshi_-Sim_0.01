<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    asRecord,
    extractShipState,
    formatDistance,
    formatDuration,
    getAutopilotSnapshot,
    getCourse,
    getWaypoint,
    toNumber,
  } from "./helmData.js";

  let busy = false;
  let feedback = "";

  $: ship = extractShipState($gameState);
  $: autopilot = getAutopilotSnapshot(ship);
  $: course = getCourse(ship);
  $: waypoint = getWaypoint(ship);
  $: courseDestination = waypoint ?? null;
  $: canResume = Boolean(autopilot.program || courseDestination);
  $: statusText = autopilot.status || (autopilot.active ? "Autopilot active" : "Standing by");
  $: progressWidth = `${autopilot.progress.toFixed(0)}%`;

  async function toggleAutopilot() {
    busy = true;
    feedback = "";

    try {
      if (autopilot.active) {
        await wsClient.sendShipCommand("autopilot", {
          enable: false,
          program: "off",
        });
        feedback = "Autopilot disengaged";
      } else if (autopilot.program) {
        await wsClient.sendShipCommand("autopilot", {
          enable: true,
          program: autopilot.program,
          target: autopilot.targetId || undefined,
        });
        feedback = `Autopilot engaged: ${autopilot.program}`;
      } else if (courseDestination) {
        await wsClient.sendShipCommand("set_course", {
          x: courseDestination.x,
          y: courseDestination.y,
          z: courseDestination.z,
          stop: true,
        });
        feedback = "Course resumed";
      }
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Autopilot command failed";
    } finally {
      busy = false;
    }
  }

  function phaseLabel(): string {
    if (!autopilot.phase) return "IDLE";
    return autopilot.phase.replaceAll("_", " ").toUpperCase();
  }

  function displayDistance(): string {
    return formatDistance(autopilot.distance);
  }

  function displayEta(): string {
    return formatDuration(autopilot.eta);
  }

  function phaseVariant(): string {
    const phase = autopilot.phase.toLowerCase();
    if (phase.includes("burn") || phase.includes("accel")) return "burn";
    if (phase.includes("coast")) return "coast";
    if (phase.includes("brake") || phase.includes("decel")) return "brake";
    if (phase.includes("hold") || phase.includes("stationkeep")) return "hold";
    return "idle";
  }

  $: autopilotState = asRecord(ship.autopilot_state) ?? asRecord(getCourse(ship));
  $: rawEta = autopilot.eta ?? toNumber(autopilotState?.time_to_arrival, 0);
</script>

<Panel title="Autopilot Status" domain="helm" priority={autopilot.active ? "primary" : "secondary"} className="autopilot-status-panel">
  <div class="status-grid">
    <div class="header-row">
      <div>
        <div class="program">{autopilot.program ? autopilot.program.replaceAll("_", " ").toUpperCase() : "NO PROGRAM"}</div>
        <div class="status-text">{statusText}</div>
      </div>
      <div class="phase {phaseVariant()}">{phaseLabel()}</div>
    </div>

    <div class="progress-track" aria-label="Autopilot progress">
      <div class="progress-fill {phaseVariant()}" style={`width: ${progressWidth};`}></div>
    </div>
    <div class="progress-caption">{autopilot.progress.toFixed(0)}%</div>

    <div class="metrics">
      <div class="metric">
        <span>Distance</span>
        <strong>{displayDistance()}</strong>
      </div>
      <div class="metric">
        <span>ETA</span>
        <strong>{rawEta > 0 ? displayEta() : "--"}</strong>
      </div>
      <div class="metric">
        <span>Target</span>
        <strong>{autopilot.targetId || "--"}</strong>
      </div>
    </div>

    <button class:disengage={autopilot.active} disabled={busy || (!autopilot.active && !canResume)} on:click={toggleAutopilot}>
      {#if autopilot.active}
        DISENGAGE
      {:else if autopilot.program}
        ENGAGE
      {:else if courseDestination}
        RESUME COURSE
      {:else}
        NO COURSE
      {/if}
    </button>

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .status-grid {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .header-row {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .program {
    font-family: var(--font-mono);
    font-size: 0.92rem;
    color: var(--text-primary);
    letter-spacing: 0.06em;
  }

  .status-text,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .phase {
    padding: 5px 10px;
    border-radius: 999px;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: 1px solid var(--border-default);
  }

  .phase.burn {
    color: var(--status-warning);
    border-color: rgba(255, 170, 0, 0.4);
  }

  .phase.coast {
    color: var(--status-info);
    border-color: rgba(0, 170, 255, 0.4);
  }

  .phase.brake {
    color: var(--status-critical);
    border-color: rgba(255, 68, 68, 0.4);
  }

  .phase.hold {
    color: var(--status-nominal);
    border-color: rgba(0, 255, 136, 0.4);
  }

  .progress-track {
    height: 10px;
    background: var(--bg-input);
    border-radius: 999px;
    overflow: hidden;
    border: 1px solid var(--border-subtle);
  }

  .progress-fill {
    height: 100%;
    transition: width var(--transition-base);
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.35), var(--tier-accent));
  }

  .progress-fill.burn {
    background: linear-gradient(90deg, rgba(255, 170, 0, 0.25), var(--status-warning));
  }

  .progress-fill.coast {
    background: linear-gradient(90deg, rgba(0, 170, 255, 0.25), var(--status-info));
  }

  .progress-fill.brake {
    background: linear-gradient(90deg, rgba(255, 68, 68, 0.25), var(--status-critical));
  }

  .progress-fill.hold {
    background: linear-gradient(90deg, rgba(0, 255, 136, 0.25), var(--status-nominal));
  }

  .progress-caption {
    margin-top: -4px;
    text-align: right;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-dim);
  }

  .metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .metric {
    display: grid;
    gap: 2px;
    padding: 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.015);
  }

  .metric span {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-dim);
  }

  .metric strong {
    font-family: var(--font-mono);
    font-size: 0.82rem;
  }

  button.disengage {
    border-color: rgba(255, 68, 68, 0.4);
    color: var(--status-critical);
  }

  button.disengage:hover:not(:disabled) {
    background: rgba(255, 68, 68, 0.08);
  }
</style>
