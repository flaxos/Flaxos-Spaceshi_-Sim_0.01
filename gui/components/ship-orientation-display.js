/**
 * Ship Orientation Display — live helm schematic for drift, attitude, and RCS state.
 *
 * Uses:
 *   - stateManager.getNavigation() for heading, velocity, throttle
 *   - ship.trajectory for drift / velocity heading
 *   - ship.rcs for per-thruster firing state
 *   - ship.helm for the commanded attitude target
 *
 * The main top-down view keeps the ship body fixed in ship frame. Velocity and
 * command markers rotate around it, which makes drift and attitude error easy to
 * read at a glance. A small side inset mirrors pitch attitude.
 */
import { stateManager } from "../js/state-manager.js";

const THRUSTER_POS = {
  pitch_up:       { x: 211, y: 54 },
  pitch_down:     { x: 211, y: 110 },
  yaw_left:       { x: 222, y: 66 },
  yaw_right:      { x: 222, y: 98 },
  pitch_up_aft:   { x: 57,  y: 54 },
  pitch_down_aft: { x: 57,  y: 110 },
  yaw_left_aft:   { x: 46,  y: 66 },
  yaw_right_aft:  { x: 46,  y: 98 },
  roll_cw:        { x: 146, y: 124 },
  roll_ccw:       { x: 122, y: 40 },
  roll_cw_2:      { x: 122, y: 124 },
  roll_ccw_2:     { x: 146, y: 40 },
};

const SHIP_CENTER = { x: 134, y: 82 };
const SIDE_CENTER = { x: 269, y: 68 };

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function shortestAngle(targetDeg, currentDeg) {
  return ((targetDeg - currentDeg + 540) % 360) - 180;
}

function thrusterColor(throttle) {
  if (throttle < 0.02) return "#1a1d28";
  if (throttle < 0.25) return "#1d6f4f";
  if (throttle < 0.6) return "#35b46e";
  if (throttle < 0.85) return "#ffb020";
  return "#ff5a36";
}

function vectorSpeed(velocity = [0, 0, 0]) {
  const [vx, vy, vz] = velocity;
  return Math.sqrt(vx * vx + vy * vy + vz * vz);
}

function yawFromVelocity(velocity = [0, 0, 0]) {
  const [vx, vy] = velocity;
  if (Math.abs(vx) < 0.001 && Math.abs(vy) < 0.001) return null;
  return Math.atan2(vy, vx) * 180 / Math.PI;
}

function formatSignedAngle(angle, positiveLabel, negativeLabel) {
  if (Math.abs(angle) < 0.5) return "0°";
  return `${Math.abs(angle).toFixed(0)}° ${angle >= 0 ? positiveLabel : negativeLabel}`;
}

class ShipOrientationDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._lastUpdate = 0;
    this._rafId = null;
  }

  connectedCallback() {
    this._render();
    this._unsub = stateManager.subscribe("*", () => this._scheduleUpdate());
    this._scheduleUpdate();
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._rafId) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
  }

  _scheduleUpdate() {
    const now = performance.now();
    if (now - this._lastUpdate < 120) return;
    this._lastUpdate = now;
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = requestAnimationFrame(() => this._update());
  }

  _render() {
    const thrusterDots = Object.entries(THRUSTER_POS).map(([id, pos]) => `
      <circle id="t-${id}" cx="${pos.x}" cy="${pos.y}" r="4"
        fill="#1a1d28" stroke="#273046" stroke-width="0.8" />
    `).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        svg {
          width: 100%;
          height: auto;
          display: block;
        }

        .hull {
          fill: #171b26;
          stroke: #3a455a;
          stroke-width: 1.5;
        }

        .frame {
          fill: rgba(9, 12, 18, 0.55);
          stroke: #263042;
          stroke-width: 1;
        }

        .centerline,
        .side-axis {
          stroke: #334057;
          stroke-width: 0.7;
          stroke-dasharray: 4 3;
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

        #drive-plume,
        #vel-arrow,
        #target-arrow {
          transition: opacity 0.12s ease;
        }

        #side-ship,
        #side-target {
          transition: transform 0.12s ease;
          transform-origin: ${SIDE_CENTER.x}px ${SIDE_CENTER.y}px;
        }
      </style>

      <svg viewBox="0 0 320 180" xmlns="http://www.w3.org/2000/svg">
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

        <text class="label" x="16" y="22">DRIFT / ATTITUDE</text>
        <text class="label" x="236" y="22">PITCH</text>

        <ellipse id="drive-plume" cx="30" cy="82" rx="10" ry="7" fill="url(#plume-grad)" opacity="0" />

        <polygon class="hull" points="48,82 68,52 214,54 244,82 214,110 68,112" />
        <line class="centerline" x1="44" y1="${SHIP_CENTER.y}" x2="246" y2="${SHIP_CENTER.y}" />
        <ellipse cx="57" cy="70" rx="5" ry="3" fill="none" stroke="#31415a" stroke-width="1" />
        <ellipse cx="57" cy="94" rx="5" ry="3" fill="none" stroke="#31415a" stroke-width="1" />
        <polygon points="239,82 229,76 229,88" fill="#52617b" />

        <line id="vel-arrow"
          x1="${SHIP_CENTER.x}" y1="${SHIP_CENTER.y}"
          x2="${SHIP_CENTER.x + 42}" y2="${SHIP_CENTER.y}"
          stroke="#44aaff" stroke-width="1.8" opacity="0"
          marker-end="url(#vel-head)" />

        <line id="target-arrow"
          x1="${SHIP_CENTER.x}" y1="${SHIP_CENTER.y}"
          x2="${SHIP_CENTER.x + 34}" y2="${SHIP_CENTER.y}"
          stroke="#ffb020" stroke-width="1.4" stroke-dasharray="5 3" opacity="0"
          marker-end="url(#target-head)" />

        ${thrusterDots}

        <line class="side-axis" x1="236" y1="${SIDE_CENTER.y}" x2="302" y2="${SIDE_CENTER.y}" />
        <line class="side-axis" x1="${SIDE_CENTER.x}" y1="32" x2="${SIDE_CENTER.x}" y2="106" />

        <g id="side-target" transform="rotate(0 ${SIDE_CENTER.x} ${SIDE_CENTER.y})">
          <polygon points="250,68 264,61 287,61 294,68 287,75 264,75"
            fill="none" stroke="#ffb020" stroke-width="1" stroke-dasharray="4 2" opacity="0.9" />
        </g>
        <g id="side-ship" transform="rotate(0 ${SIDE_CENTER.x} ${SIDE_CENTER.y})">
          <polygon points="250,68 264,60 288,60 297,68 288,76 264,76"
            fill="#171b26" stroke="#4d5a71" stroke-width="1.2" />
        </g>

        <text id="speed-lbl" class="readout" x="16" y="142">SPD 0 m/s</text>
        <text id="drift-lbl" class="readout accent" x="16" y="154">DRIFT 0°</text>
        <text id="yawerr-lbl" class="readout warn" x="16" y="166">YAW ERR 0°</text>
        <text id="pitch-lbl" class="readout" x="236" y="118">PITCH 0°</text>
        <text id="pitcherr-lbl" class="readout warn" x="236" y="130">PITCH ERR 0°</text>
        <text id="rate-lbl" class="readout dim" x="236" y="142">OMEGA 0.0°/s</text>
      </svg>
    `;
  }

  _update() {
    const ship = stateManager.getShipState?.() || {};
    const nav = stateManager.getNavigation?.() || {};
    const rcs = ship?.rcs || ship?.systems?.rcs || null;
    const helm = ship?.helm || ship?.systems?.helm || null;
    const trajectory = ship?.trajectory || ship?.navigation || {};

    const heading = nav.heading || ship.orientation || { pitch: 0, yaw: 0, roll: 0 };
    const velocity = nav.velocity || [0, 0, 0];
    const speed = vectorSpeed(velocity);
    const velocityYaw = trajectory.velocity_heading?.yaw ?? yawFromVelocity(velocity);
    const driftYaw = velocityYaw == null ? 0 : shortestAngle(velocityYaw, heading.yaw || 0);

    const target = helm?.attitude_target || rcs?.attitude_target || null;
    const yawError = target ? shortestAngle(target.yaw ?? heading.yaw ?? 0, heading.yaw ?? 0) : 0;
    const pitchError = target ? shortestAngle(target.pitch ?? heading.pitch ?? 0, heading.pitch ?? 0) : 0;
    const angularVelocity = ship?.angular_velocity || {};
    const omegaMag = Math.sqrt(
      (angularVelocity.pitch || 0) ** 2 +
      (angularVelocity.yaw || 0) ** 2 +
      (angularVelocity.roll || 0) ** 2
    );

    const plume = this.shadowRoot.getElementById("drive-plume");
    const thrust = clamp(nav.thrust ?? helm?.manual_throttle ?? 0, 0, 1);
    if (plume) {
      plume.setAttribute("opacity", (thrust * 0.88).toFixed(2));
      plume.setAttribute("rx", (8 + thrust * 18).toFixed(1));
      plume.setAttribute("ry", (5 + thrust * 13).toFixed(1));
    }

    const velArrow = this.shadowRoot.getElementById("vel-arrow");
    if (velArrow) {
      if (speed > 1 && velocityYaw != null) {
        const angleRad = driftYaw * Math.PI / 180;
        const arrowLen = Math.min(48, 20 + speed * 0.015);
        velArrow.setAttribute("x2", (SHIP_CENTER.x + arrowLen * Math.cos(angleRad)).toFixed(1));
        velArrow.setAttribute("y2", (SHIP_CENTER.y - arrowLen * Math.sin(angleRad)).toFixed(1));
        velArrow.setAttribute("opacity", "0.9");
      } else {
        velArrow.setAttribute("opacity", "0");
      }
    }

    const targetArrow = this.shadowRoot.getElementById("target-arrow");
    if (targetArrow) {
      if (target && Math.abs(yawError) > 0.5) {
        const angleRad = yawError * Math.PI / 180;
        const arrowLen = 38;
        targetArrow.setAttribute("x2", (SHIP_CENTER.x + arrowLen * Math.cos(angleRad)).toFixed(1));
        targetArrow.setAttribute("y2", (SHIP_CENTER.y - arrowLen * Math.sin(angleRad)).toFixed(1));
        targetArrow.setAttribute("opacity", "0.9");
      } else {
        targetArrow.setAttribute("opacity", "0");
      }
    }

    const thrusters = rcs?.thrusters || [];
    Object.entries(THRUSTER_POS).forEach(([id]) => {
      const thruster = thrusters.find((entry) => entry.id === id);
      const el = this.shadowRoot.getElementById(`t-${id}`);
      if (!el) return;

      const throttle = thruster?.throttle || 0;
      const active = throttle > 0.02;
      el.setAttribute("fill", thrusterColor(throttle));
      el.setAttribute("stroke", active ? "#8df4b7" : "#273046");
      el.setAttribute("r", active ? "5" : "4");
      el.setAttribute("opacity", active ? "1" : "0.78");
    });

    const sideShip = this.shadowRoot.getElementById("side-ship");
    const sideTarget = this.shadowRoot.getElementById("side-target");
    const pitch = clamp(heading.pitch || 0, -60, 60);
    if (sideShip) {
      sideShip.setAttribute("transform", `rotate(${-pitch} ${SIDE_CENTER.x} ${SIDE_CENTER.y})`);
    }
    if (sideTarget) {
      const targetPitch = clamp(target?.pitch ?? pitch, -60, 60);
      sideTarget.setAttribute("transform", `rotate(${-targetPitch} ${SIDE_CENTER.x} ${SIDE_CENTER.y})`);
      sideTarget.style.opacity = target ? "1" : "0.2";
    }

    const speedLabel = this.shadowRoot.getElementById("speed-lbl");
    const driftLabel = this.shadowRoot.getElementById("drift-lbl");
    const yawErrLabel = this.shadowRoot.getElementById("yawerr-lbl");
    const pitchLabel = this.shadowRoot.getElementById("pitch-lbl");
    const pitchErrLabel = this.shadowRoot.getElementById("pitcherr-lbl");
    const rateLabel = this.shadowRoot.getElementById("rate-lbl");

    if (speedLabel) speedLabel.textContent = `SPD ${speed.toFixed(0)} m/s`;
    if (driftLabel) driftLabel.textContent = `DRIFT ${formatSignedAngle(driftYaw, "PORT", "STBD")}`;
    if (yawErrLabel) yawErrLabel.textContent = `YAW ERR ${target ? formatSignedAngle(yawError, "PORT", "STBD") : "—"}`;
    if (pitchLabel) pitchLabel.textContent = `PITCH ${(heading.pitch || 0).toFixed(0)}°`;
    if (pitchErrLabel) pitchErrLabel.textContent = `PITCH ERR ${target ? formatSignedAngle(pitchError, "UP", "DN") : "—"}`;
    if (rateLabel) rateLabel.textContent = `OMEGA ${omegaMag.toFixed(1)}°/s`;
  }
}

customElements.define("ship-orientation-display", ShipOrientationDisplay);
