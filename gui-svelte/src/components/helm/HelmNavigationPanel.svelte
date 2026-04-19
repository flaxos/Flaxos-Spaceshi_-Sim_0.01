<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import {
    extractShipState,
    formatDistance,
    formatDuration,
    formatSpeed,
    getAutopilotSnapshot,
    getPosition,
    getVelocity,
  } from "./helmData.js";

  $: ship = extractShipState($gameState);
  $: position = getPosition(ship);
  $: velocity = getVelocity(ship);
  $: autopilot = getAutopilotSnapshot(ship);
  $: progressWidth = `${Math.max(0, Math.min(100, autopilot.progress)).toFixed(0)}%`;
</script>

<Panel title="Navigation" domain="nav" priority="secondary" className="helm-navigation-panel">
  <div class="shell">
    <div class="grid">
      <div><span>Pos X</span><strong>{formatDistance(position.x)}</strong></div>
      <div><span>Pos Z</span><strong>{formatDistance(position.z)}</strong></div>
      <div><span>Vel X</span><strong>{formatSpeed(velocity.x)}</strong></div>
      <div><span>Vel Z</span><strong>{formatSpeed(velocity.z)}</strong></div>
    </div>

    <div class="intercept">
      <span>Time To {autopilot.targetId ? `Intercept ${autopilot.targetId}` : "Destination"}</span>
      <strong>{autopilot.eta != null && autopilot.eta > 0 ? formatDuration(autopilot.eta) : "--"}</strong>
    </div>

    <div class="progress-track">
      <div class="progress-fill" style={`width:${progressWidth};`}></div>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 12px;
  }

  .grid div,
  .intercept {
    display: grid;
    gap: 2px;
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .intercept strong {
    font-size: 1.05rem;
    color: var(--text-bright);
  }

  .progress-track {
    height: 6px;
    border-radius: 999px;
    overflow: hidden;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(30, 140, 255, 0.3), var(--status-info));
  }
</style>
