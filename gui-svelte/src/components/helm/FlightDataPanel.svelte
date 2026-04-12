<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import {
    computeRelativeSpeed,
    extractShipState,
    formatDistance,
    formatSpeed,
    formatVector,
    getAutopilotSnapshot,
    getDeltaV,
    getOrientation,
    getPONR,
    getPosition,
    getVelocity,
    magnitude,
    signed,
    toNumber,
    toPercent,
    toStringValue,
  } from "./helmData.js";

  $: ship = extractShipState($gameState);
  $: position = getPosition(ship);
  $: velocity = getVelocity(ship);
  $: heading = getOrientation(ship);
  $: speed = magnitude(velocity);
  $: autopilot = getAutopilotSnapshot(ship);
  $: relativeSpeed = computeRelativeSpeed(ship, autopilot.targetId || toStringValue(ship.target_id));
  $: deltaV = getDeltaV(ship);
  $: ponr = getPONR(ship);
  $: pastPonr = Boolean(ponr.past_ponr);
  $: manualLike = $tier === "manual" || $tier === "raw";
  $: showRawVectors = manualLike;
  $: stopMargin = toNumber(ponr.dv_margin);
</script>

<Panel title="Flight Data" domain="helm" priority={$tier === "manual" ? "primary" : "secondary"} className="flight-data-panel">
  <div class="stack">
    {#if pastPonr}
      <div class="alert critical">PAST POINT OF NO RETURN</div>
    {:else if toNumber(ponr.margin_percent, 100) < 25 && toNumber(ponr.dv_to_stop) > 0}
      <div class="alert warning">Brake margin {toPercent(toNumber(ponr.margin_percent), 0)} · reserve {formatSpeed(stopMargin)}</div>
    {/if}

    <section class="section">
      <div class="section-title">Position</div>
      <div class="metric-row">
        <span class="label">X</span>
        <span class="value">{formatDistance(position.x)}</span>
      </div>
      <div class="metric-row">
        <span class="label">Y</span>
        <span class="value">{formatDistance(position.y)}</span>
      </div>
      <div class="metric-row">
        <span class="label">Z</span>
        <span class="value">{formatDistance(position.z)}</span>
      </div>
      {#if showRawVectors}
        <div class="vector-readout">{formatVector(position, 1)}</div>
      {/if}
    </section>

    <section class="section">
      <div class="section-title">Velocity</div>
      <div class="hero">{formatSpeed(speed)}</div>
      <div class="metric-row">
        <span class="label">Vs Target</span>
        <span class="value accent">{relativeSpeed == null ? "--" : formatSpeed(relativeSpeed)}</span>
      </div>
      {#if showRawVectors}
        <div class="metric-row">
          <span class="label">Vector</span>
          <span class="value">{formatVector(velocity, 1)}</span>
        </div>
      {/if}
    </section>

    <section class="section compact">
      <div class="section-title">Attitude</div>
      <div class="triple">
        <div>
          <div class="micro-label">Pitch</div>
          <div class="micro-value">{signed(heading.pitch, 1)}°</div>
        </div>
        <div>
          <div class="micro-label">Yaw</div>
          <div class="micro-value">{signed(heading.yaw, 1)}°</div>
        </div>
        <div>
          <div class="micro-label">Roll</div>
          <div class="micro-value">{signed(heading.roll, 1)}°</div>
        </div>
      </div>
    </section>

    <section class="section compact">
      <div class="section-title">Budget</div>
      <div class="metric-row">
        <span class="label">Delta-V</span>
        <span class="value accent">{formatSpeed(deltaV)}</span>
      </div>
      <div class="metric-row">
        <span class="label">Stop Burn</span>
        <span class="value">{formatSpeed(toNumber(ponr.dv_to_stop))}</span>
      </div>
      <div class="metric-row">
        <span class="label">Target Range</span>
        <span class="value">{formatDistance(autopilot.distance)}</span>
      </div>
    </section>
  </div>
</Panel>

<style>
  .stack {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .section {
    display: grid;
    gap: 6px;
    padding: 10px;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
  }

  .section.compact {
    gap: 8px;
  }

  .section-title {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-secondary);
  }

  .metric-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .label,
  .micro-label {
    color: var(--text-dim);
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .value,
  .micro-value,
  .hero,
  .vector-readout {
    font-family: var(--font-mono);
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .hero {
    font-size: 1.25rem;
    color: var(--tier-accent);
  }

  .accent {
    color: var(--status-info);
  }

  .vector-readout {
    padding-top: 4px;
    color: var(--text-secondary);
    font-size: var(--font-size-xs);
    word-break: break-word;
  }

  .triple {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .alert {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .alert.warning {
    color: var(--status-warning);
    border: 1px solid rgba(255, 170, 0, 0.4);
    background: rgba(255, 170, 0, 0.09);
  }

  .alert.critical {
    color: var(--status-critical);
    border: 1px solid rgba(255, 68, 68, 0.45);
    background: rgba(255, 68, 68, 0.1);
    box-shadow: var(--glow-critical);
  }
</style>
