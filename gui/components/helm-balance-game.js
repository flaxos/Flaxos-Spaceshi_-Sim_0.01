/**
 * Helm Balance Game (ARCADE tier)
 *
 * Ambient flight stability indicator. A ball drifts inside a circular zone
 * based on real ship physics — thrust G-force, RCS torque, and angular
 * velocity push the ball away from center. When the ship flies smoothly the
 * ball stays centered ("SMOOTH"), when maneuvering hard it drifts outward
 * ("ROUGH" / "UNSTABLE").
 *
 * This is purely visual feedback — the server handles actual fuel consumption.
 * The panel auto-fades when the ship is idle (no thrust, no rotation).
 *
 * Reads from stateManager ship telemetry. Does NOT send any commands.
 */

import { stateManager } from "../js/state-manager.js";
import { getDegradation } from "../js/minigame-difficulty.js";

// Zone thresholds (fraction of radius, 0 = center, 1 = edge)
const SMOOTH_THRESHOLD = 0.30;
const ROUGH_THRESHOLD = 0.65;

// Spring / damping constants
const SPRING_K = 3.0;       // pull toward center when stable
const DAMPING = 0.92;       // velocity decay per frame
const FORCE_SCALE_G = 0.35; // how much thrust G pushes the ball
const FORCE_SCALE_ANG = 0.25; // how much angular velocity pushes the ball
const JOLT_SCALE = 0.15;    // random jolt from RCS firings

// Visibility thresholds
const THRUST_VIS_THRESHOLD = 0.01;  // G
const ANGULAR_VIS_THRESHOLD = 0.5;  // deg/s equivalent
const FADE_DELAY_MS = 2000;         // ms after last activity before fading

// Canvas sizing
const CANVAS_SIZE = 160;
const BALL_RADIUS = 6;
const TRAIL_LENGTH = 8;

class HelmBalanceGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    // Ball state (normalized -1..1, 0 = center)
    this._ballX = 0;
    this._ballY = 0;
    this._ballVX = 0;
    this._ballVY = 0;

    // Animation
    this._animFrame = null;
    this._lastTime = 0;

    // Efficiency display
    this._efficiency = 1.0;
    this._zone = "SMOOTH";

    // Trail history (array of {x, y})
    this._trail = [];

    // Visibility fade
    this._isActive = false;
    this._lastActivityTime = 0;
    this._fadeOpacity = 0;

    // State subscription
    this._unsub = null;

    // Cached ship state values (updated from stateManager)
    this._thrustG = 0;
    this._angularVel = { roll: 0, pitch: 0, yaw: 0 };
    this._lastThrustG = 0; // for detecting thrust changes (jolts)
  }

  connectedCallback() {
    this._render();
    this._canvas = this.shadowRoot.getElementById("balance-canvas");
    this._ctx = this._canvas.getContext("2d");
    this._zoneLabel = this.shadowRoot.getElementById("zone-label");
    this._effLabel = this.shadowRoot.getElementById("eff-label");
    this._headingArrow = this.shadowRoot.getElementById("heading-arrow");

    this._subscribe();
    this._lastTime = performance.now();
    this._tick(this._lastTime);
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._updateFromState();
    });
    // Initial read
    this._updateFromState();
  }

  _updateFromState() {
    const ship = stateManager.getShipState();
    if (!ship) return;

    const prop = ship?.systems?.propulsion;
    const rcs = ship?.systems?.rcs;

    // Thrust G — try multiple telemetry paths
    this._lastThrustG = this._thrustG;
    this._thrustG = ship?.thrust_g
      || (typeof prop === "object" ? prop?.thrust_g : 0)
      || 0;

    // Angular velocity — try rcs telemetry or ship-level
    if (rcs && typeof rcs === "object" && rcs.total_torque) {
      this._angularVel = rcs.total_torque;
    } else if (ship?.angular_velocity) {
      this._angularVel = ship.angular_velocity;
    } else {
      this._angularVel = { roll: 0, pitch: 0, yaw: 0 };
    }

    // Heading for the arrow (degrees)
    this._heading = ship?.heading || ship?.course?.heading || 0;
  }

  /**
   * Main animation loop via requestAnimationFrame.
   */
  _tick(timestamp) {
    const dt = Math.min((timestamp - this._lastTime) / 1000, 0.1); // cap at 100ms
    this._lastTime = timestamp;

    this._updatePhysics(dt);
    this._updateZone();
    this._updateVisibility(timestamp);
    this._draw();

    this._animFrame = requestAnimationFrame((t) => this._tick(t));
  }

  /**
   * Simple spring + damping physics for the ball.
   * Ship forces push the ball; spring pulls it back to center.
   */
  _updatePhysics(dt) {
    if (dt <= 0) return;

    const thrustG = this._thrustG;
    const angMag = Math.sqrt(
      (this._angularVel.roll || 0) ** 2 +
      (this._angularVel.pitch || 0) ** 2 +
      (this._angularVel.yaw || 0) ** 2
    );

    // Force from thrust — pushes ball "down" (positive Y) proportional to G
    let forceX = 0;
    let forceY = thrustG * FORCE_SCALE_G;

    // Force from angular velocity — pushes ball laterally
    // Yaw pushes X, pitch pushes Y, roll adds a twist
    forceX += (this._angularVel.yaw || 0) * FORCE_SCALE_ANG;
    forceY += (this._angularVel.pitch || 0) * FORCE_SCALE_ANG;
    forceX += (this._angularVel.roll || 0) * FORCE_SCALE_ANG * 0.5;

    // Jolt from thrust changes (simulates RCS corrections)
    const thrustDelta = Math.abs(thrustG - this._lastThrustG);
    if (thrustDelta > 0.05) {
      forceX += (Math.random() - 0.5) * thrustDelta * JOLT_SCALE * 10;
      forceY += (Math.random() - 0.5) * thrustDelta * JOLT_SCALE * 10;
    }

    // Small random perturbation when under thrust (turbulence feel)
    if (thrustG > THRUST_VIS_THRESHOLD) {
      forceX += (Math.random() - 0.5) * thrustG * 0.08;
      forceY += (Math.random() - 0.5) * thrustG * 0.08;
    }

    // RCS damage weakens spring return and damping
    const dmg = getDegradation("rcs");
    const effectiveSpring = SPRING_K * (1 - dmg * 0.7);
    const effectiveDamping = DAMPING * (1 - dmg * 0.5);

    // Spring force pulling ball back to center
    const springFX = -this._ballX * effectiveSpring;
    const springFY = -this._ballY * effectiveSpring;

    // Apply forces
    this._ballVX += (forceX + springFX) * dt;
    this._ballVY += (forceY + springFY) * dt;

    // Damping
    this._ballVX *= effectiveDamping;
    this._ballVY *= effectiveDamping;

    // Integrate position
    this._ballX += this._ballVX * dt;
    this._ballY += this._ballVY * dt;

    // Clamp to unit circle
    const dist = Math.sqrt(this._ballX ** 2 + this._ballY ** 2);
    if (dist > 1.0) {
      this._ballX /= dist;
      this._ballY /= dist;
      // Bounce: kill velocity component pointing outward
      this._ballVX *= -0.3;
      this._ballVY *= -0.3;
    }

    // Update trail (sample every ~2 frames worth)
    this._trail.push({ x: this._ballX, y: this._ballY });
    if (this._trail.length > TRAIL_LENGTH) {
      this._trail.shift();
    }
  }

  /**
   * Determine which zone the ball is in and update efficiency display.
   */
  _updateZone() {
    const dist = Math.sqrt(this._ballX ** 2 + this._ballY ** 2);

    if (dist <= SMOOTH_THRESHOLD) {
      this._zone = "SMOOTH";
      this._efficiency = 1.0 + (SMOOTH_THRESHOLD - dist) * 0.1; // up to 103%
    } else if (dist <= ROUGH_THRESHOLD) {
      this._zone = "ROUGH";
      const t = (dist - SMOOTH_THRESHOLD) / (ROUGH_THRESHOLD - SMOOTH_THRESHOLD);
      this._efficiency = 1.0 - t * 0.05; // 100% down to 95%
    } else {
      this._zone = "UNSTABLE";
      const t = (dist - ROUGH_THRESHOLD) / (1.0 - ROUGH_THRESHOLD);
      this._efficiency = 0.95 - t * 0.15; // 95% down to 80%
    }

    // Update DOM labels
    if (this._zoneLabel) {
      this._zoneLabel.textContent = this._zone;
      this._zoneLabel.className = `zone-label zone-${this._zone.toLowerCase()}`;
    }
    if (this._effLabel) {
      this._effLabel.textContent = `FUEL EFF: ${Math.round(this._efficiency * 100)}%`;
    }
  }

  /**
   * Manage fade in/out based on ship activity.
   */
  _updateVisibility(timestamp) {
    const thrustG = this._thrustG;
    const angMag = Math.sqrt(
      (this._angularVel.roll || 0) ** 2 +
      (this._angularVel.pitch || 0) ** 2 +
      (this._angularVel.yaw || 0) ** 2
    );

    const hasActivity = thrustG > THRUST_VIS_THRESHOLD || angMag > ANGULAR_VIS_THRESHOLD;

    if (hasActivity) {
      this._lastActivityTime = timestamp;
      this._isActive = true;
    } else if (timestamp - this._lastActivityTime > FADE_DELAY_MS) {
      this._isActive = false;
    }

    // Smooth fade
    const targetOpacity = this._isActive ? 1.0 : 0.0;
    this._fadeOpacity += (targetOpacity - this._fadeOpacity) * 0.05;

    const host = this.shadowRoot.host;
    if (host) {
      host.style.opacity = Math.max(0, Math.min(1, this._fadeOpacity)).toFixed(2);
      host.style.pointerEvents = this._fadeOpacity < 0.1 ? "none" : "auto";
    }
  }

  /**
   * Draw the balance indicator on the canvas.
   */
  _draw() {
    const ctx = this._ctx;
    if (!ctx) return;

    const size = CANVAS_SIZE;
    const center = size / 2;
    const radius = (size / 2) - 8; // leave margin for glow

    ctx.clearRect(0, 0, size, size);

    // --- Graduated zone rings ---
    // Outer ring (UNSTABLE zone) — red
    this._drawRing(ctx, center, radius, ROUGH_THRESHOLD, 1.0, "rgba(255, 60, 60, 0.12)", "rgba(255, 60, 60, 0.25)");
    // Middle ring (ROUGH zone) — yellow
    this._drawRing(ctx, center, radius, SMOOTH_THRESHOLD, ROUGH_THRESHOLD, "rgba(255, 200, 40, 0.08)", "rgba(255, 200, 40, 0.2)");
    // Inner ring (SMOOTH zone) — green
    this._drawRing(ctx, center, radius, 0, SMOOTH_THRESHOLD, "rgba(0, 255, 100, 0.06)", "rgba(0, 255, 100, 0.2)");

    // --- Crosshair lines ---
    ctx.strokeStyle = "rgba(100, 120, 160, 0.15)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(center - radius, center);
    ctx.lineTo(center + radius, center);
    ctx.moveTo(center, center - radius);
    ctx.lineTo(center, center + radius);
    ctx.stroke();

    // --- Outer boundary ---
    ctx.strokeStyle = "rgba(100, 120, 160, 0.3)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.stroke();

    // --- Heading arrow ---
    const headingRad = ((this._heading || 0) - 90) * (Math.PI / 180);
    const arrowDist = radius + 4;
    const arrowX = center + Math.cos(headingRad) * arrowDist;
    const arrowY = center + Math.sin(headingRad) * arrowDist;
    ctx.save();
    ctx.translate(arrowX, arrowY);
    ctx.rotate(headingRad + Math.PI / 2);
    ctx.fillStyle = "rgba(68, 136, 255, 0.6)";
    ctx.beginPath();
    ctx.moveTo(0, -4);
    ctx.lineTo(-3, 3);
    ctx.lineTo(3, 3);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // --- Motion trail ---
    for (let i = 0; i < this._trail.length; i++) {
      const t = this._trail[i];
      const alpha = (i / this._trail.length) * 0.4;
      const trailR = BALL_RADIUS * (0.3 + (i / this._trail.length) * 0.5);
      const px = center + t.x * radius;
      const py = center + t.y * radius;
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha.toFixed(2)})`;
      ctx.beginPath();
      ctx.arc(px, py, trailR, 0, Math.PI * 2);
      ctx.fill();
    }

    // --- Ball ---
    const ballPx = center + this._ballX * radius;
    const ballPy = center + this._ballY * radius;

    // Glow based on zone
    let glowColor;
    if (this._zone === "SMOOTH") {
      glowColor = "rgba(0, 255, 100, 0.4)";
    } else if (this._zone === "ROUGH") {
      glowColor = "rgba(255, 200, 40, 0.4)";
    } else {
      glowColor = "rgba(255, 60, 60, 0.5)";
    }

    ctx.shadowColor = glowColor;
    ctx.shadowBlur = 10;
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(ballPx, ballPy, BALL_RADIUS, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Ball border
    ctx.strokeStyle = glowColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(ballPx, ballPy, BALL_RADIUS, 0, Math.PI * 2);
    ctx.stroke();
  }

  /**
   * Draw a graduated ring zone between innerFrac and outerFrac of the radius.
   */
  _drawRing(ctx, center, radius, innerFrac, outerFrac, fillColor, strokeColor) {
    const innerR = innerFrac * radius;
    const outerR = outerFrac * radius;

    ctx.fillStyle = fillColor;
    ctx.beginPath();
    ctx.arc(center, center, outerR, 0, Math.PI * 2);
    if (innerR > 0) {
      ctx.arc(center, center, innerR, 0, Math.PI * 2, true);
    }
    ctx.fill();

    // Ring boundary
    if (innerR > 0) {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 0.5;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.arc(center, center, innerR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 0;
          opacity: 0;
          transition: opacity 0.3s ease;
        }

        .balance-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          padding: 12px 8px;
        }

        .zone-label {
          font-size: 0.7rem;
          font-weight: 700;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          text-align: center;
          min-height: 1em;
        }

        .zone-smooth   { color: #44ee88; text-shadow: 0 0 6px rgba(68, 238, 136, 0.4); }
        .zone-rough    { color: #eec844; text-shadow: 0 0 6px rgba(238, 200, 68, 0.4); }
        .zone-unstable { color: #ee4444; text-shadow: 0 0 6px rgba(238, 68, 68, 0.5); animation: pulse-unstable 0.6s ease-in-out infinite alternate; }

        @keyframes pulse-unstable {
          from { opacity: 0.7; }
          to { opacity: 1.0; }
        }

        canvas {
          display: block;
          border-radius: 50%;
        }

        .eff-label {
          font-size: 0.65rem;
          letter-spacing: 0.12em;
          color: #667;
          font-weight: 600;
          text-align: center;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .heading-indicator {
          font-size: 0.55rem;
          color: rgba(68, 136, 255, 0.5);
          letter-spacing: 0.1em;
          text-align: center;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        @media (prefers-reduced-motion: reduce) {
          :host { transition: none; }
          .zone-unstable { animation: none; }
        }
      </style>

      <div class="balance-container">
        <div id="zone-label" class="zone-label zone-smooth">SMOOTH</div>
        <canvas id="balance-canvas" width="${CANVAS_SIZE}" height="${CANVAS_SIZE}"></canvas>
        <div id="eff-label" class="eff-label">FUEL EFF: 100%</div>
        <div id="heading-arrow" class="heading-indicator">HDG ---</div>
      </div>
    `;
  }
}

customElements.define("helm-balance-game", HelmBalanceGame);
