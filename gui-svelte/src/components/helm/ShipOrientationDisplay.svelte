<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import {
    asRecord,
    clamp,
    extractShipState,
    getOrientation,
    getSystem,
    getThrottle,
    getThrusters,
    getVelocity,
    magnitude,
    normalizeAngle,
    toNumber,
  } from "./helmData.js";

  interface ArrowGeometry {
    x2: number;
    y2: number;
  }

  const THRUSTER_POS: Record<string, { x: number; y: number }> = {
    pitch_up: { x: 211, y: 54 },
    pitch_down: { x: 211, y: 110 },
    yaw_left: { x: 222, y: 66 },
    yaw_right: { x: 222, y: 98 },
    pitch_up_aft: { x: 57, y: 54 },
    pitch_down_aft: { x: 57, y: 110 },
    yaw_left_aft: { x: 46, y: 66 },
    yaw_right_aft: { x: 46, y: 98 },
    roll_cw: { x: 146, y: 124 },
    roll_ccw: { x: 122, y: 40 },
    roll_cw_2: { x: 122, y: 124 },
    roll_ccw_2: { x: 146, y: 40 },
  };

  const SHIP_CENTER = { x: 134, y: 82 };
  const SIDE_CENTER = { x: 269, y: 68 };

  function shortestAngle(targetDeg: number, currentDeg: number) {
    return ((targetDeg - currentDeg + 540) % 360) - 180;
  }

  function thrusterColor(throttle: number) {
    if (throttle < 0.02) return "#1a1d28";
    if (throttle < 0.25) return "#1d6f4f";
    if (throttle < 0.6) return "#35b46e";
    if (throttle < 0.85) return "#ffb020";
    return "#ff5a36";
  }

  function yawFromVelocity(velocity: { x: number; y: number; z: number }) {
    if (Math.abs(velocity.x) < 0.001 && Math.abs(velocity.y) < 0.001) return null;
    return Math.atan2(velocity.y, velocity.x) * 180 / Math.PI;
  }

  function formatSignedAngle(angle: number, positiveLabel: string, negativeLabel: string) {
    if (Math.abs(angle) < 0.5) return "0°";
    return `${Math.abs(angle).toFixed(0)}° ${angle >= 0 ? positiveLabel : negativeLabel}`;
  }

  function arrowFromAngle(angleDeg: number, length: number): ArrowGeometry {
    const angleRad = angleDeg * Math.PI / 180;
    return {
      x2: SHIP_CENTER.x + length * Math.cos(angleRad),
      y2: SHIP_CENTER.y - length * Math.sin(angleRad),
    };
  }

  $: ship = extractShipState($gameState);
  $: helm = asRecord(ship.helm) ?? getSystem(ship, "helm");
  $: rcs = asRecord(ship.rcs) ?? getSystem(ship, "rcs");
  $: trajectory = asRecord(ship.trajectory) ?? {};
  $: heading = getOrientation(ship);
  $: velocity = getVelocity(ship);
  $: speed = magnitude(velocity);
  $: velocityHeading = asRecord(trajectory.velocity_heading);
  $: velocityYaw = velocityHeading ? toNumber(velocityHeading.yaw, yawFromVelocity(velocity) ?? 0) : yawFromVelocity(velocity);
  $: driftYaw = velocityYaw == null ? 0 : shortestAngle(velocityYaw, heading.yaw);
  $: target = asRecord(helm.attitude_target) ?? asRecord(rcs.attitude_target);
  $: yawError = target ? shortestAngle(toNumber(target.yaw, heading.yaw), heading.yaw) : 0;
  $: pitchError = target ? shortestAngle(toNumber(target.pitch, heading.pitch), heading.pitch) : 0;
  $: angularVelocity = asRecord(ship.angular_velocity) ?? {};
  $: omegaMag = Math.sqrt(
    toNumber(angularVelocity.pitch, 0) ** 2 +
    toNumber(angularVelocity.yaw, 0) ** 2 +
    toNumber(angularVelocity.roll, 0) ** 2
  );
  $: thrust = clamp(getThrottle(ship), 0, 1);
  $: drivePlume = {
    opacity: thrust * 0.88,
    rx: 8 + thrust * 18,
    ry: 5 + thrust * 13,
  };
  $: velocityArrow = speed > 1 && velocityYaw != null
    ? arrowFromAngle(driftYaw, Math.min(48, 20 + speed * 0.015))
    : null;
  $: targetArrow = target && Math.abs(yawError) > 0.5
    ? arrowFromAngle(yawError, 38)
    : null;
  $: targetPitch = clamp(target ? toNumber(target.pitch, heading.pitch) : heading.pitch, -60, 60);
  $: thrusters = getThrusters(ship);
  $: thrusterDots = Object.entries(THRUSTER_POS).map(([id, pos]) => {
    const thruster = thrusters.find((entry) => entry.id === id);
    const throttle = thruster?.throttle ?? 0;
    return {
      id,
      x: pos.x,
      y: pos.y,
      fill: thrusterColor(throttle),
      stroke: throttle > 0.02 ? "#8df4b7" : "#273046",
      radius: throttle > 0.02 ? 5 : 4,
      opacity: throttle > 0.02 ? 1 : 0.78,
    };
  });
</script>

<Panel title="Orientation" domain="helm" priority="primary" className="ship-orientation-panel">
  <div class="shell">
    <svg viewBox="0 0 320 180" aria-label="Ship orientation display">
      <defs>
        <radialGradient id="plume-grad" cx="80%" cy="50%" r="80%" fx="80%" fy="50%">
          <stop offset="0%" stop-color="#ffb020" stop-opacity="0.95" />
          <stop offset="55%" stop-color="#ff5a36" stop-opacity="0.45" />
          <stop offset="100%" stop-color="#250000" stop-opacity="0" />
        </radialGradient>
        <marker id="vel-head" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <polygon points="0 0, 6 3, 0 6" fill="#44aaff" opacity="0.85" />
        </marker>
        <marker id="target-head" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <polygon points="0 0, 6 3, 0 6" fill="#ffb020" opacity="0.85" />
        </marker>
      </defs>

      <rect class="frame" x="8" y="8" width="304" height="164" rx="8" />

      <text class="label" x="16" y="22">Drift / Attitude</text>
      <text class="label" x="236" y="22">Pitch</text>

      <ellipse
        cx="30"
        cy="82"
        fill="url(#plume-grad)"
        opacity={drivePlume.opacity}
        rx={drivePlume.rx}
        ry={drivePlume.ry}
      />

      <polygon class="hull" points="48,82 68,52 214,54 244,82 214,110 68,112" />
      <line class="centerline" x1="44" y1={SHIP_CENTER.y} x2="246" y2={SHIP_CENTER.y} />
      <ellipse cx="57" cy="70" rx="5" ry="3" class="engine-ring" />
      <ellipse cx="57" cy="94" rx="5" ry="3" class="engine-ring" />
      <polygon points="239,82 229,76 229,88" class="nose" />

      {#if velocityArrow}
        <line
          x1={SHIP_CENTER.x}
          y1={SHIP_CENTER.y}
          x2={velocityArrow.x2}
          y2={velocityArrow.y2}
          class="velocity-arrow"
          marker-end="url(#vel-head)"
        />
      {/if}

      {#if targetArrow}
        <line
          x1={SHIP_CENTER.x}
          y1={SHIP_CENTER.y}
          x2={targetArrow.x2}
          y2={targetArrow.y2}
          class="target-arrow"
          marker-end="url(#target-head)"
        />
      {/if}

      {#each thrusterDots as thruster}
        <circle
          cx={thruster.x}
          cy={thruster.y}
          r={thruster.radius}
          fill={thruster.fill}
          stroke={thruster.stroke}
          opacity={thruster.opacity}
          class="thruster-dot"
        />
      {/each}

      <line class="side-axis" x1="236" y1={SIDE_CENTER.y} x2="302" y2={SIDE_CENTER.y} />
      <line class="side-axis" x1={SIDE_CENTER.x} y1="32" x2={SIDE_CENTER.x} y2="106" />

      <g transform={`rotate(${-targetPitch} ${SIDE_CENTER.x} ${SIDE_CENTER.y})`} opacity={target ? 1 : 0.2}>
        <polygon
          points="250,68 264,61 287,61 294,68 287,75 264,75"
          class="pitch-target"
        />
      </g>
      <g transform={`rotate(${-clamp(heading.pitch, -60, 60)} ${SIDE_CENTER.x} ${SIDE_CENTER.y})`}>
        <polygon
          points="250,68 264,60 288,60 297,68 288,76 264,76"
          class="pitch-ship"
        />
      </g>

      <text class="readout" x="16" y="142">SPD {speed.toFixed(0)} m/s</text>
      <text class="readout accent" x="16" y="154">DRIFT {formatSignedAngle(driftYaw, "PORT", "STBD")}</text>
      <text class="readout warn" x="16" y="166">YAW ERR {target ? formatSignedAngle(yawError, "PORT", "STBD") : "—"}</text>
      <text class="readout" x="236" y="118">PITCH {heading.pitch.toFixed(0)}°</text>
      <text class="readout warn" x="236" y="130">PITCH ERR {target ? formatSignedAngle(pitchError, "UP", "DN") : "—"}</text>
      <text class="readout dim" x="236" y="142">OMEGA {omegaMag.toFixed(1)}°/s</text>
    </svg>
  </div>
</Panel>

<style>
  .shell {
    padding: var(--space-sm);
  }

  svg {
    width: 100%;
    height: auto;
    display: block;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background:
      radial-gradient(circle at 24% 30%, rgba(68, 170, 255, 0.12), transparent 28%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0)),
      #091018;
  }

  .frame {
    fill: rgba(9, 12, 18, 0.55);
    stroke: #263042;
    stroke-width: 1;
  }

  .hull {
    fill: #171b26;
    stroke: #3a455a;
    stroke-width: 1.5;
  }

  .centerline,
  .side-axis {
    stroke: #334057;
    stroke-width: 0.7;
    stroke-dasharray: 4 3;
  }

  .engine-ring {
    fill: none;
    stroke: #31415a;
    stroke-width: 1;
  }

  .nose {
    fill: #52617b;
  }

  .label {
    font-size: 7px;
    letter-spacing: 0.12em;
    fill: #6f7f98;
    text-transform: uppercase;
  }

  .readout {
    font-size: 8px;
    fill: #b7c5d8;
  }

  .dim {
    fill: #7a889b;
  }

  .accent {
    fill: #44aaff;
  }

  .warn {
    fill: #ffb020;
  }

  .velocity-arrow {
    stroke: #44aaff;
    stroke-width: 1.8;
    opacity: 0.9;
  }

  .target-arrow {
    stroke: #ffb020;
    stroke-width: 1.4;
    stroke-dasharray: 5 3;
    opacity: 0.9;
  }

  .pitch-target {
    fill: none;
    stroke: #ffb020;
    stroke-width: 1;
    stroke-dasharray: 4 2;
  }

  .pitch-ship {
    fill: #171b26;
    stroke: #4d5a71;
    stroke-width: 1.2;
  }

  .thruster-dot {
    transition: fill var(--transition-fast), stroke var(--transition-fast), r var(--transition-fast);
  }
</style>
