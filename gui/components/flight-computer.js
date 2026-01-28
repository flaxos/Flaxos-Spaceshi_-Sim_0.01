/**
 * Flight Computer - Physics Estimation Engine
 * Provides time-to-intercept, flip-and-burn calculations, waypoint navigation
 * Inspired by The Expanse / Empty Epsilon style navigation assistance
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

// Constants
const G_ACCEL = 9.81; // m/s^2

class FlightComputer extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._mode = "waypoint"; // "waypoint", "intercept", "flip_burn"
    this._targetContact = null;
    this._waypoint = { x: 0, y: 0, z: 0 };
    this._computedSolution = null;
    this._waypointExecutionMode = "point";
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .mode-toggle {
          display: flex;
          gap: 4px;
          margin-bottom: 12px;
        }

        .mode-btn {
          flex: 1;
          padding: 6px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          font-size: 0.65rem;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .mode-btn.active {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .waypoint-toggle {
          display: flex;
          gap: 4px;
          margin-bottom: 12px;
        }

        .toggle-btn {
          flex: 1;
          padding: 6px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          font-size: 0.65rem;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .toggle-btn.active {
          background: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          color: var(--bg-primary, #0a0a0f);
        }

        /* Waypoint Input */
        .waypoint-input {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-bottom: 12px;
        }

        .input-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .input-group label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          text-align: center;
        }

        .input-group input, .input-group select {
          padding: 8px;
          background: var(--bg-primary, #0a0a0f);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          text-align: center;
        }

        .input-group input:focus, .input-group select:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .autopilot-options {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-bottom: 12px;
        }

        /* Solution Display */
        .solution-panel {
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 12px;
        }

        .solution-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .solution-status {
          font-size: 0.7rem;
          font-weight: 600;
          padding: 2px 8px;
          border-radius: 3px;
        }

        .solution-status.valid {
          background: var(--status-nominal, #00ff88);
          color: #000;
        }

        .solution-status.computing {
          background: var(--status-warning, #ffaa00);
          color: #000;
        }

        .solution-status.invalid {
          background: var(--status-critical, #ff4444);
          color: #fff;
        }

        .solution-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
        }

        .solution-item {
          padding: 8px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 4px;
        }

        .solution-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-bottom: 4px;
        }

        .solution-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.9rem;
          color: var(--text-primary, #e0e0e0);
        }

        .solution-value.highlight {
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .solution-item.full-width {
          grid-column: span 2;
        }

        /* Maneuver Plan */
        .maneuver-plan {
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 12px;
        }

        .maneuver-step {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 0;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .maneuver-step:last-child {
          border-bottom: none;
        }

        .step-number {
          width: 24px;
          height: 24px;
          background: var(--status-info, #00aaff);
          color: #000;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.75rem;
          font-weight: 600;
        }

        .step-content {
          flex: 1;
        }

        .step-action {
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
        }

        .step-detail {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
        }

        .step-countdown {
          font-size: 0.65rem;
          color: var(--status-info, #00aaff);
          margin-top: 2px;
        }

        .plan-options {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
        }

        .plan-options label {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
          display: flex;
          align-items: center;
          gap: 6px;
        }

        /* Actions */
        .actions {
          display: flex;
          gap: 8px;
        }

        .btn {
          flex: 1;
          padding: 10px 16px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
          cursor: pointer;
          min-height: 44px;
        }

        .btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .btn.primary {
          background: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          color: var(--bg-primary, #0a0a0f);
          font-weight: 600;
        }

        .btn.primary:hover:not(:disabled) {
          filter: brightness(1.1);
        }

        .hidden {
          display: none !important;
        }
      </style>

      <div class="section-title">Flight Computer</div>

      <!-- Mode Toggle -->
      <div class="mode-toggle">
        <button class="mode-btn active" data-mode="waypoint">Waypoint</button>
        <button class="mode-btn" data-mode="intercept">Intercept</button>
        <button class="mode-btn" data-mode="flip_burn">Flip & Burn</button>
      </div>

      <!-- Waypoint Mode -->
      <div id="waypoint-section">
        <div class="waypoint-input">
          <div class="input-group">
            <label>X (m)</label>
            <input type="number" id="waypoint-x" value="0" step="100" />
          </div>
          <div class="input-group">
            <label>Y (m)</label>
            <input type="number" id="waypoint-y" value="0" step="100" />
          </div>
          <div class="input-group">
            <label>Z (m)</label>
            <input type="number" id="waypoint-z" value="0" step="100" />
          </div>
        </div>
        <div class="input-group" style="margin-bottom: 12px;">
          <label>Approach G-Force</label>
          <input type="number" id="approach-g" value="1.0" min="0.1" max="10" step="0.1" style="width: 100%;" />
        </div>
        <div class="waypoint-toggle">
          <button class="toggle-btn active" data-waypoint-mode="point">Point At</button>
          <button class="toggle-btn" data-waypoint-mode="autopilot">Fly To</button>
        </div>
        <div class="autopilot-options hidden" id="autopilot-options">
          <div class="input-group">
            <label>Stop at Target</label>
            <select id="course-stop">
              <option value="true" selected>Yes</option>
              <option value="false">No</option>
            </select>
          </div>
          <div class="input-group">
            <label>Tolerance (m)</label>
            <input type="number" id="course-tolerance" value="50" min="1" step="1" />
          </div>
          <div class="input-group">
            <label>Max Thrust (0-1)</label>
            <input type="number" id="course-max-thrust" min="0" max="1" step="0.05" placeholder="Auto" />
          </div>
        </div>
      </div>

      <!-- Intercept Mode -->
      <div id="intercept-section" class="hidden">
        <div class="input-group" style="margin-bottom: 12px;">
          <label>Target Contact</label>
          <select id="target-select">
            <option value="">-- Select Target --</option>
          </select>
        </div>
        <div class="input-group" style="margin-bottom: 12px;">
          <label>Intercept G-Force</label>
          <input type="number" id="intercept-g" value="2.0" min="0.1" max="10" step="0.1" style="width: 100%;" />
        </div>
      </div>

      <!-- Flip & Burn Mode -->
      <div id="flip-burn-section" class="hidden">
        <div class="input-group" style="margin-bottom: 12px;">
          <label>Braking G-Force</label>
          <input type="number" id="brake-g" value="1.0" min="0.1" max="10" step="0.1" style="width: 100%;" />
        </div>
      </div>

      <!-- Solution Display -->
      <div class="solution-panel">
        <div class="solution-header">
          <span class="section-title" style="margin-bottom: 0;">Computed Solution</span>
          <span class="solution-status" id="solution-status">READY</span>
        </div>
        <div class="solution-grid" id="solution-grid">
          <div class="solution-item">
            <div class="solution-label">Range</div>
            <div class="solution-value" id="sol-range">--</div>
          </div>
          <div class="solution-item">
            <div class="solution-label">Closing Rate</div>
            <div class="solution-value" id="sol-closing">--</div>
          </div>
          <div class="solution-item">
            <div class="solution-label">Time to Target</div>
            <div class="solution-value highlight" id="sol-tti">--</div>
          </div>
          <div class="solution-item">
            <div class="solution-label">Required Delta-V</div>
            <div class="solution-value highlight" id="sol-dv">--</div>
          </div>
          <div class="solution-item">
            <div class="solution-label">Burn Duration</div>
            <div class="solution-value" id="sol-burn">--</div>
          </div>
          <div class="solution-item">
            <div class="solution-label">Flip Point</div>
            <div class="solution-value" id="sol-flip">--</div>
          </div>
          <div class="solution-item full-width">
            <div class="solution-label">Suggested Heading</div>
            <div class="solution-value highlight" id="sol-heading">P: -- | Y: --</div>
          </div>
        </div>
      </div>

      <!-- Maneuver Plan -->
      <div class="maneuver-plan" id="maneuver-plan" style="display: none;">
        <div class="section-title" style="margin-bottom: 8px;">Maneuver Plan</div>
        <div id="maneuver-steps"></div>
      </div>

      <div class="plan-options">
        <label>
          <input type="checkbox" id="queue-plan" />
          Queue plan
        </label>
      </div>

      <!-- Actions -->
      <div class="actions">
        <button class="btn" id="compute-btn">Compute</button>
        <button class="btn primary" id="execute-btn" disabled>Execute</button>
      </div>
    `;
  }

  _setupInteraction() {
    // Mode toggle
    this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._setMode(btn.dataset.mode);
      });
    });

    this.shadowRoot.querySelectorAll(".toggle-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._setWaypointExecutionMode(btn.dataset.waypointMode);
      });
    });

    // Input changes trigger recompute
    this.shadowRoot.querySelectorAll("input, select").forEach(input => {
      input.addEventListener("change", () => {
        this._compute();
      });
    });

    // Compute button
    this.shadowRoot.getElementById("compute-btn").addEventListener("click", () => {
      this._compute();
    });

    // Execute button
    this.shadowRoot.getElementById("execute-btn").addEventListener("click", () => {
      this._execute();
    });
  }

  _setMode(mode) {
    this._mode = mode;

    // Update button states
    this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });

    // Show/hide sections
    this.shadowRoot.getElementById("waypoint-section").classList.toggle("hidden", mode !== "waypoint");
    this.shadowRoot.getElementById("intercept-section").classList.toggle("hidden", mode !== "intercept");
    this.shadowRoot.getElementById("flip-burn-section").classList.toggle("hidden", mode !== "flip_burn");

    // Reset solution
    this._computedSolution = null;
    this._updateSolutionDisplay();

    // Update target dropdown if intercept mode
    if (mode === "intercept") {
      this._updateTargetDropdown();
    }
  }

  _setWaypointExecutionMode(mode) {
    if (!mode) return;
    this._waypointExecutionMode = mode;
    this.shadowRoot.querySelectorAll(".toggle-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.waypointMode === mode);
    });
    const autopilotOptions = this.shadowRoot.getElementById("autopilot-options");
    autopilotOptions.classList.toggle("hidden", mode !== "autopilot");
    if (this._computedSolution) {
      this._compute();
    }
  }

  _updateTargetDropdown() {
    const contacts = stateManager.getContacts();
    const select = this.shadowRoot.getElementById("target-select");

    select.innerHTML = '<option value="">-- Select Target --</option>';
    contacts.forEach(contact => {
      const id = contact.contact_id || contact.id;
      const option = document.createElement("option");
      option.value = id;
      option.textContent = `${id} (${contact.classification || "UNKNOWN"})`;
      select.appendChild(option);
    });
  }

  _updateDisplay() {
    // Update target dropdown in intercept mode
    if (this._mode === "intercept") {
      this._updateTargetDropdown();
    }

    // Recompute if we have a solution
    if (this._computedSolution) {
      this._compute();
    }
  }

  _compute() {
    const nav = stateManager.getNavigation();
    const ship = stateManager.getShipState();

    const position = nav.position || [0, 0, 0];
    const velocity = nav.velocity || [0, 0, 0];

    const statusEl = this.shadowRoot.getElementById("solution-status");
    statusEl.className = "solution-status computing";
    statusEl.textContent = "COMPUTING";

    let solution = null;

    try {
      switch (this._mode) {
        case "waypoint":
          solution = this._computeWaypointSolution(position, velocity, ship);
          break;
        case "intercept":
          solution = this._computeInterceptSolution(position, velocity, ship);
          break;
        case "flip_burn":
          solution = this._computeFlipBurnSolution(position, velocity, ship);
          break;
      }

      if (solution) {
        this._computedSolution = solution;
        statusEl.className = "solution-status valid";
        statusEl.textContent = "VALID";
        this.shadowRoot.getElementById("execute-btn").disabled = false;
      } else {
        statusEl.className = "solution-status invalid";
        statusEl.textContent = "NO SOLUTION";
        this.shadowRoot.getElementById("execute-btn").disabled = true;
      }
    } catch (error) {
      console.error("Flight computer error:", error);
      statusEl.className = "solution-status invalid";
      statusEl.textContent = "ERROR";
      this.shadowRoot.getElementById("execute-btn").disabled = true;
      this._showMessage(`Flight computer error: ${error.message}`, "error");
    }

    this._updateSolutionDisplay();
  }

  _computeWaypointSolution(position, velocity, ship) {
    const targetX = parseFloat(this.shadowRoot.getElementById("waypoint-x").value) || 0;
    const targetY = parseFloat(this.shadowRoot.getElementById("waypoint-y").value) || 0;
    const targetZ = parseFloat(this.shadowRoot.getElementById("waypoint-z").value) || 0;
    const approachG = parseFloat(this.shadowRoot.getElementById("approach-g").value) || 1.0;
    const stopValue = this.shadowRoot.getElementById("course-stop")?.value ?? "true";
    const stop = stopValue !== "false";
    const tolerance = parseFloat(this.shadowRoot.getElementById("course-tolerance")?.value) || 50;
    const maxThrustValue = parseFloat(this.shadowRoot.getElementById("course-max-thrust")?.value);
    const maxThrust = Number.isFinite(maxThrustValue) ? maxThrustValue : null;

    // Calculate relative vector
    const dx = targetX - position[0];
    const dy = targetY - position[1];
    const dz = targetZ - position[2];
    const range = Math.sqrt(dx * dx + dy * dy + dz * dz);

    if (range < 1) {
      return null; // Already at target
    }

    // Current velocity magnitude
    const velMag = Math.sqrt(velocity[0]**2 + velocity[1]**2 + velocity[2]**2);

    // Closing rate (velocity towards target)
    const dirX = dx / range;
    const dirY = dy / range;
    const dirZ = dz / range;
    const closingRate = velocity[0] * dirX + velocity[1] * dirY + velocity[2] * dirZ;

    // Acceleration for approach
    const accel = approachG * G_ACCEL;

    // Calculate brachistochrone trajectory (constant thrust)
    // For point-to-point: accelerate halfway, then decelerate
    const flipDistance = range / 2;

    // Time to flip point using kinematic equation: d = v0*t + 0.5*a*t^2
    // Solving for t when accelerating from current velocity
    // For simplicity, use: t = sqrt(2*d/a) for starting from rest approach
    const timeToFlip = Math.sqrt(2 * flipDistance / accel);
    const totalTime = timeToFlip * 2;

    // Velocity at flip point
    const flipVelocity = accel * timeToFlip;

    // Total delta-v required (accelerate + decelerate)
    const deltaV = flipVelocity * 2 - closingRate;

    // Calculate heading to target
    const yaw = Math.atan2(dy, dx) * (180 / Math.PI);
    const horizontalDist = Math.sqrt(dx * dx + dy * dy);
    const pitch = Math.atan2(dz, horizontalDist) * (180 / Math.PI);

    // Build maneuver plan
    const maneuverPlan = [
      {
        action: "Point prograde",
        detail: `Heading: P=${pitch.toFixed(1)} Y=${yaw.toFixed(1)}`,
        trigger: { distance_remaining: range }
      },
      {
        action: `Burn at ${approachG}G`,
        detail: `Duration: ${this._formatTime(timeToFlip)}`,
        trigger: { time_to_target: totalTime }
      },
      {
        action: "Flip 180 degrees",
        detail: `At ${this._formatDistance(flipDistance)} from start`,
        trigger: { distance_remaining: range - flipDistance }
      },
      {
        action: `Brake at ${approachG}G`,
        detail: `Duration: ${this._formatTime(timeToFlip)}`,
        trigger: { distance_remaining: range - flipDistance }
      },
      {
        action: "Arrival",
        detail: "Zero relative velocity",
        trigger: { distance_remaining: 0, time_to_target: 0 }
      }
    ];

    const plan = {
      name: "Waypoint Plan",
      type: "waypoint",
      source: "flight_computer",
      target: { position: { x: targetX, y: targetY, z: targetZ } },
      steps: maneuverPlan.map(step => ({
        action: step.action,
        detail: step.detail,
        trigger: step.trigger
      }))
    };

    return {
      range,
      closingRate,
      timeToIntercept: totalTime,
      deltaV: Math.abs(deltaV),
      burnDuration: timeToFlip,
      flipPoint: flipDistance,
      heading: { pitch, yaw },
      targetPosition: { x: targetX, y: targetY, z: targetZ },
      maneuverPlan,
      plan,
      command: {
        type: "waypoint",
        position: { x: targetX, y: targetY, z: targetZ },
        g: approachG,
        executionMode: this._waypointExecutionMode,
        stop,
        tolerance,
        max_thrust: maxThrust
      }
    };
  }

  _computeInterceptSolution(position, velocity, ship) {
    const targetId = this.shadowRoot.getElementById("target-select").value;
    const interceptG = parseFloat(this.shadowRoot.getElementById("intercept-g").value) || 2.0;

    if (!targetId) return null;

    // Get target contact
    const contacts = stateManager.getContacts();
    const target = contacts.find(c => (c.contact_id || c.id) === targetId);

    if (!target) return null;

    const targetPos = target.position || [0, 0, 0];
    const targetVel = target.velocity || [0, 0, 0];

    // Calculate relative motion
    const dx = targetPos[0] - position[0];
    const dy = targetPos[1] - position[1];
    const dz = targetPos[2] - position[2];
    const range = Math.sqrt(dx * dx + dy * dy + dz * dz);

    // Relative velocity
    const dvx = targetVel[0] - velocity[0];
    const dvy = targetVel[1] - velocity[1];
    const dvz = targetVel[2] - velocity[2];
    const closingRate = -(dx * dvx + dy * dvy + dz * dvz) / range;

    // For intercept, use lead pursuit
    // Estimate time to intercept assuming constant acceleration
    const accel = interceptG * G_ACCEL;

    // Simple estimate: t = sqrt(2*range/accel) for stationary target
    // For moving target, iterate or use approximation
    let timeToIntercept;
    if (closingRate > 0) {
      // Already closing, adjust for that
      timeToIntercept = range / closingRate;
    } else {
      timeToIntercept = Math.sqrt(2 * range / accel);
    }

    // Predicted intercept point
    const interceptX = targetPos[0] + targetVel[0] * timeToIntercept;
    const interceptY = targetPos[1] + targetVel[1] * timeToIntercept;
    const interceptZ = targetPos[2] + targetVel[2] * timeToIntercept;

    // Heading to intercept point
    const interceptDx = interceptX - position[0];
    const interceptDy = interceptY - position[1];
    const interceptDz = interceptZ - position[2];
    const yaw = Math.atan2(interceptDy, interceptDx) * (180 / Math.PI);
    const horizontalDist = Math.sqrt(interceptDx * interceptDx + interceptDy * interceptDy);
    const pitch = Math.atan2(interceptDz, horizontalDist) * (180 / Math.PI);

    // Delta-v to match velocity at intercept
    const deltaV = Math.sqrt(dvx * dvx + dvy * dvy + dvz * dvz);
    const burnDuration = deltaV / accel;

    // Build maneuver plan
    const maneuverPlan = [
      {
        action: "Point at lead",
        detail: `Heading: P=${pitch.toFixed(1)} Y=${yaw.toFixed(1)}`,
        trigger: { distance_remaining: range }
      },
      {
        action: `Burn at ${interceptG}G`,
        detail: `Intercept in ${this._formatTime(timeToIntercept)}`,
        trigger: { time_to_target: timeToIntercept }
      },
      {
        action: "Match velocity",
        detail: `Delta-V: ${deltaV.toFixed(1)} m/s`,
        trigger: { distance_remaining: 0, time_to_target: 0 }
      }
    ];

    const plan = {
      name: "Intercept Plan",
      type: "intercept",
      source: "flight_computer",
      target: { contact_id: targetId },
      steps: maneuverPlan.map(step => ({
        action: step.action,
        detail: step.detail,
        trigger: step.trigger
      }))
    };

    return {
      range,
      closingRate,
      timeToIntercept,
      deltaV,
      burnDuration,
      flipPoint: range / 2,
      heading: { pitch, yaw },
      targetId,
      maneuverPlan,
      plan,
      command: {
        type: "intercept",
        target: targetId,
        g: interceptG
      }
    };
  }

  _computeFlipBurnSolution(position, velocity, ship) {
    const brakeG = parseFloat(this.shadowRoot.getElementById("brake-g").value) || 1.0;

    // Current velocity magnitude
    const velMag = Math.sqrt(velocity[0]**2 + velocity[1]**2 + velocity[2]**2);

    if (velMag < 1) {
      return null; // Already stationary
    }

    // Deceleration
    const accel = brakeG * G_ACCEL;

    // Time to stop: v = a*t => t = v/a
    const burnDuration = velMag / accel;

    // Distance to stop: d = v^2 / (2*a)
    const stoppingDistance = (velMag * velMag) / (2 * accel);

    // Retrograde heading (opposite of velocity)
    const retroYaw = Math.atan2(-velocity[1], -velocity[0]) * (180 / Math.PI);
    const retroHorizDist = Math.sqrt(velocity[0]**2 + velocity[1]**2);
    const retroPitch = Math.atan2(-velocity[2], retroHorizDist) * (180 / Math.PI);

    // Build maneuver plan
    const maneuverPlan = [
      {
        action: "Flip to retrograde",
        detail: `Heading: P=${retroPitch.toFixed(1)} Y=${retroYaw.toFixed(1)}`,
        trigger: { time_to_target: burnDuration }
      },
      {
        action: `Brake at ${brakeG}G`,
        detail: `Duration: ${this._formatTime(burnDuration)}`,
        trigger: { time_to_target: burnDuration }
      },
      {
        action: "Full stop",
        detail: `After ${this._formatDistance(stoppingDistance)}`,
        trigger: { distance_remaining: 0, time_to_target: 0 }
      }
    ];

    const plan = {
      name: "Flip & Burn Plan",
      type: "flip_burn",
      source: "flight_computer",
      target: { stop: true },
      steps: maneuverPlan.map(step => ({
        action: step.action,
        detail: step.detail,
        trigger: step.trigger
      }))
    };

    return {
      range: stoppingDistance,
      closingRate: velMag,
      timeToIntercept: burnDuration,
      deltaV: velMag,
      burnDuration,
      flipPoint: 0,
      heading: { pitch: retroPitch, yaw: retroYaw },
      maneuverPlan,
      plan,
      command: {
        type: "maneuver",
        maneuver: "retrograde",
        g: brakeG
      }
    };
  }

  _updateSolutionDisplay() {
    const sol = this._computedSolution;

    const rangeEl = this.shadowRoot.getElementById("sol-range");
    const closingEl = this.shadowRoot.getElementById("sol-closing");
    const ttiEl = this.shadowRoot.getElementById("sol-tti");
    const dvEl = this.shadowRoot.getElementById("sol-dv");
    const burnEl = this.shadowRoot.getElementById("sol-burn");
    const flipEl = this.shadowRoot.getElementById("sol-flip");
    const headingEl = this.shadowRoot.getElementById("sol-heading");
    const maneuverPlan = this.shadowRoot.getElementById("maneuver-plan");
    const maneuverSteps = this.shadowRoot.getElementById("maneuver-steps");

    if (!sol) {
      rangeEl.textContent = "--";
      closingEl.textContent = "--";
      ttiEl.textContent = "--";
      dvEl.textContent = "--";
      burnEl.textContent = "--";
      flipEl.textContent = "--";
      headingEl.textContent = "P: -- | Y: --";
      maneuverPlan.style.display = "none";
      return;
    }

    rangeEl.textContent = this._formatDistance(sol.range);
    closingEl.textContent = `${sol.closingRate.toFixed(1)} m/s`;
    ttiEl.textContent = this._formatTime(sol.timeToIntercept);
    dvEl.textContent = `${sol.deltaV.toFixed(1)} m/s`;
    burnEl.textContent = this._formatTime(sol.burnDuration);
    flipEl.textContent = this._formatDistance(sol.flipPoint);
    headingEl.textContent = `P: ${sol.heading.pitch.toFixed(1)} | Y: ${sol.heading.yaw.toFixed(1)}`;

    // Show maneuver plan
    if (sol.maneuverPlan && sol.maneuverPlan.length > 0) {
      maneuverPlan.style.display = "block";
      const liveMetrics = this._getLiveTargetMetrics(sol);
      maneuverSteps.innerHTML = sol.maneuverPlan.map((step, i) => {
        const countdown = this._formatTriggerCountdown(step.trigger, liveMetrics);
        return `
          <div class="maneuver-step">
            <div class="step-number">${i + 1}</div>
            <div class="step-content">
              <div class="step-action">${step.action}</div>
              <div class="step-detail">${step.detail}</div>
              <div class="step-countdown">${countdown}</div>
            </div>
          </div>
        `;
      }).join("");
    } else {
      maneuverPlan.style.display = "none";
    }
  }

  async _execute() {
    if (!this._computedSolution) return;

    const cmd = this._computedSolution.command;
    const queuePlan = this.shadowRoot.getElementById("queue-plan")?.checked;

    try {
      let response;

      if (queuePlan && this._computedSolution.plan) {
        try {
          await wsClient.sendShipCommand("set_plan", { plan: this._computedSolution.plan });
          this._showMessage("Flight plan queued", "success");
        } catch (error) {
          console.error("Queue plan failed:", error);
          this._showMessage(`Plan queue failed: ${error.message}`, "warning");
        }
      }

      switch (cmd.type) {
        case "waypoint":
          if (cmd.executionMode === "autopilot") {
            const payload = {
              x: cmd.position.x,
              y: cmd.position.y,
              z: cmd.position.z,
              stop: cmd.stop,
              tolerance: cmd.tolerance
            };
            if (cmd.max_thrust !== null && cmd.max_thrust !== undefined) {
              payload.max_thrust = cmd.max_thrust;
            }
            await wsClient.sendShipCommand("set_course", payload);
            this._showMessage(`Course set to (${cmd.position.x.toFixed(0)}, ${cmd.position.y.toFixed(0)}, ${cmd.position.z.toFixed(0)})`, "success");
          } else {
            await wsClient.sendShipCommand("point_at", { position: cmd.position });
            this._showMessage(`Pointing at waypoint (${cmd.position.x.toFixed(0)}, ${cmd.position.y.toFixed(0)}, ${cmd.position.z.toFixed(0)})`, "info");
          }
          break;

        case "intercept":
          response = await wsClient.sendShipCommand("autopilot", {
            program: "intercept",
            target: cmd.target
          });
          this._showMessage(`Intercept autopilot engaged: ${cmd.target}`, "success");
          break;

        case "maneuver":
          response = await wsClient.sendShipCommand("maneuver", {
            type: cmd.maneuver,
            g: cmd.g
          });
          this._showMessage(`${cmd.maneuver} maneuver initiated at ${cmd.g}G`, "success");
          break;
      }
    } catch (error) {
      console.error("Execute failed:", error);
      this._showMessage(`Execution failed: ${error.message}`, "error");
    }
  }

  _getLiveTargetMetrics(solution) {
    const nav = stateManager.getNavigation();
    const position = nav.position || [0, 0, 0];
    const velocity = nav.velocity || [0, 0, 0];
    const mode = solution?.command?.type;

    if (!mode) {
      return { distanceRemaining: null, timeToTarget: null };
    }

    if (mode === "maneuver") {
      const gForce = solution.command?.g || 1.0;
      const accel = gForce * G_ACCEL;
      const speed = Math.sqrt(velocity[0]**2 + velocity[1]**2 + velocity[2]**2);
      if (accel <= 0) {
        return { distanceRemaining: null, timeToTarget: null };
      }
      return {
        distanceRemaining: (speed * speed) / (2 * accel),
        timeToTarget: speed / accel,
      };
    }

    let targetPos = null;
    let targetVel = [0, 0, 0];

    if (mode === "waypoint") {
      const target = solution.command?.position;
      if (target) {
        targetPos = [target.x || 0, target.y || 0, target.z || 0];
      }
    } else if (mode === "intercept") {
      const contacts = stateManager.getContacts();
      const targetId = solution.command?.target;
      const target = contacts.find(c => (c.contact_id || c.id) === targetId);
      if (target) {
        targetPos = target.position || [0, 0, 0];
        targetVel = target.velocity || [0, 0, 0];
      }
    }

    if (!targetPos) {
      return { distanceRemaining: null, timeToTarget: null };
    }

    const dx = targetPos[0] - position[0];
    const dy = targetPos[1] - position[1];
    const dz = targetPos[2] - position[2];
    const range = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (range <= 0) {
      return { distanceRemaining: 0, timeToTarget: 0 };
    }

    let closingRate = 0;
    if (mode === "waypoint") {
      const dirX = dx / range;
      const dirY = dy / range;
      const dirZ = dz / range;
      closingRate = velocity[0] * dirX + velocity[1] * dirY + velocity[2] * dirZ;
    } else {
      const dvx = targetVel[0] - velocity[0];
      const dvy = targetVel[1] - velocity[1];
      const dvz = targetVel[2] - velocity[2];
      closingRate = -(dx * dvx + dy * dvy + dz * dvz) / range;
    }

    const timeToTarget = closingRate > 0 ? range / closingRate : null;

    return {
      distanceRemaining: range,
      timeToTarget,
    };
  }

  _formatTriggerCountdown(trigger, metrics) {
    const hasDistance = metrics.distanceRemaining !== null && metrics.distanceRemaining !== undefined;
    const hasTime = metrics.timeToTarget !== null && metrics.timeToTarget !== undefined;

    if (!trigger || (!hasDistance && !hasTime)) {
      return "Trigger: --";
    }

    const parts = [];

    if (trigger.distance_remaining !== undefined && trigger.distance_remaining !== null && hasDistance) {
      const delta = metrics.distanceRemaining - trigger.distance_remaining;
      const label = delta <= 0 ? "dist: NOW" : `dist: ${this._formatDistance(delta)}`;
      parts.push(label);
    }

    if (trigger.time_to_target !== undefined && trigger.time_to_target !== null && hasTime) {
      const delta = metrics.timeToTarget - trigger.time_to_target;
      const label = delta <= 0 ? "time: NOW" : `time: ${this._formatTime(delta)}`;
      parts.push(label);
    }

    if (!parts.length) {
      return "Trigger: --";
    }

    return `Trigger: ${parts.join(" • ")}`;
  }

  _formatTime(seconds) {
    if (seconds === null || seconds === undefined || !isFinite(seconds)) return "--";
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  }

  _formatDistance(meters) {
    if (meters === null || meters === undefined || !isFinite(meters)) return "--";
    if (Math.abs(meters) >= 1000000) return `${(meters / 1000).toFixed(0)} km`;
    if (Math.abs(meters) >= 1000) return `${(meters / 1000).toFixed(2)} km`;
    return `${meters.toFixed(1)} m`;
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("flight-computer", FlightComputer);
export { FlightComputer };
