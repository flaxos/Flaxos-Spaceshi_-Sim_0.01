/**
 * Manual Thrust Input (DEBUG MODE)
 * Direct X, Y, Z thrust entry with numeric inputs
 * 
 * WARNING: This bypasses Expanse-style ship-frame thrust.
 * For realistic gameplay, use the Throttle Control instead.
 * Vector thrust applies force directly in world coordinates.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class ManualThrust extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._thrustX = 0;
    this._thrustY = 0;
    this._thrustZ = 0;
    this._maxThrust = 100;
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
      this._updateFromState();
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

        .thrust-grid {
          display: grid;
          gap: 12px;
        }

        .axis-row {
          display: grid;
          grid-template-columns: 40px 1fr auto;
          gap: 8px;
          align-items: center;
        }

        .axis-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.9rem;
          font-weight: 600;
          text-align: center;
          padding: 8px;
          border-radius: 4px;
        }

        .axis-label.x { background: rgba(255, 68, 68, 0.2); color: #ff6666; }
        .axis-label.y { background: rgba(68, 255, 68, 0.2); color: #66ff66; }
        .axis-label.z { background: rgba(68, 68, 255, 0.2); color: #6666ff; }

        .thrust-input {
          width: 100%;
          padding: 10px 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.9rem;
          text-align: center;
        }

        .thrust-input:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .adjust-btns {
          display: flex;
          gap: 4px;
        }

        .adjust-btn {
          width: 32px;
          height: 32px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          cursor: pointer;
          font-size: 1rem;
          min-height: auto;
          padding: 0;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .adjust-btn:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--border-active, #3a3a4a);
        }

        .adjust-btn:active {
          transform: scale(0.95);
        }

        .section-divider {
          height: 1px;
          background: var(--border-default, #2a2a3a);
          margin: 12px 0;
        }

        .action-row {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }

        .action-btn {
          flex: 1;
          padding: 12px 16px;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 44px;
        }

        .apply-btn {
          background: var(--status-info, #00aaff);
          border: none;
          color: var(--bg-primary, #0a0a0f);
        }

        .apply-btn:hover {
          filter: brightness(1.1);
        }

        .zero-btn {
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .zero-btn:hover {
          background: rgba(255, 170, 0, 0.1);
        }

        .stop-btn {
          background: var(--status-critical, #ff4444);
          border: none;
          color: white;
        }

        .stop-btn:hover {
          filter: brightness(1.1);
        }

        .current-display {
          margin-top: 16px;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }

        .display-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .display-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          text-align: center;
        }

        .display-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
        }

        .display-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .magnitude {
          margin-top: 8px;
          text-align: center;
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .magnitude-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--status-info, #00aaff);
        }
      </style>

      <div class="thrust-grid">
        <div class="axis-row">
          <span class="axis-label x">X</span>
          <input type="number" class="thrust-input" id="thrust-x" value="0" step="10">
          <div class="adjust-btns">
            <button class="adjust-btn" data-axis="x" data-delta="-10">-</button>
            <button class="adjust-btn" data-axis="x" data-delta="10">+</button>
          </div>
        </div>

        <div class="axis-row">
          <span class="axis-label y">Y</span>
          <input type="number" class="thrust-input" id="thrust-y" value="0" step="10">
          <div class="adjust-btns">
            <button class="adjust-btn" data-axis="y" data-delta="-10">-</button>
            <button class="adjust-btn" data-axis="y" data-delta="10">+</button>
          </div>
        </div>

        <div class="axis-row">
          <span class="axis-label z">Z</span>
          <input type="number" class="thrust-input" id="thrust-z" value="0" step="10">
          <div class="adjust-btns">
            <button class="adjust-btn" data-axis="z" data-delta="-10">-</button>
            <button class="adjust-btn" data-axis="z" data-delta="10">+</button>
          </div>
        </div>
      </div>

      <div class="action-row">
        <button class="action-btn apply-btn" id="apply-btn">Apply Thrust</button>
        <button class="action-btn zero-btn" id="zero-btn">Zero All</button>
      </div>

      <button class="action-btn stop-btn" id="stop-btn" style="width: 100%; margin-top: 8px;">
        🛑 EMERGENCY STOP
      </button>

      <div class="current-display">
        <div class="display-title">Current Thrust</div>
        <div class="display-grid">
          <div>
            <div class="display-value" id="current-x">0.0</div>
            <div class="display-label">X</div>
          </div>
          <div>
            <div class="display-value" id="current-y">0.0</div>
            <div class="display-label">Y</div>
          </div>
          <div>
            <div class="display-value" id="current-z">0.0</div>
            <div class="display-label">Z</div>
          </div>
        </div>
        <div class="magnitude">
          Magnitude: <span class="magnitude-value" id="current-mag">0.0</span>
        </div>
      </div>
    `;
  }

  _setupInteraction() {
    // Input change handlers
    ["x", "y", "z"].forEach(axis => {
      const input = this.shadowRoot.getElementById(`thrust-${axis}`);
      input.addEventListener("input", () => {
        this[`_thrust${axis.toUpperCase()}`] = parseFloat(input.value) || 0;
      });
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          this._applyThrust();
        }
      });
    });

    // Adjust buttons
    this.shadowRoot.querySelectorAll(".adjust-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const axis = btn.dataset.axis;
        const delta = parseFloat(btn.dataset.delta);
        const input = this.shadowRoot.getElementById(`thrust-${axis}`);
        const current = parseFloat(input.value) || 0;
        const newValue = Math.max(-this._maxThrust, Math.min(this._maxThrust, current + delta));
        input.value = newValue;
        this[`_thrust${axis.toUpperCase()}`] = newValue;
      });
    });

    // Action buttons
    this.shadowRoot.getElementById("apply-btn").addEventListener("click", () => {
      this._applyThrust();
    });

    this.shadowRoot.getElementById("zero-btn").addEventListener("click", () => {
      this._zeroAll();
    });

    this.shadowRoot.getElementById("stop-btn").addEventListener("click", () => {
      this._emergencyStop();
    });
  }

  _updateFromState() {
    const ship = stateManager.getShipState();
    const thrust = ship?.thrust || { x: 0, y: 0, z: 0 };
    
    // Get thrust values (handle both object and array formats)
    let x = 0, y = 0, z = 0;
    if (typeof thrust === "object" && !Array.isArray(thrust)) {
      x = thrust.x || 0;
      y = thrust.y || 0;
      z = thrust.z || 0;
    }

    // Update current display
    this.shadowRoot.getElementById("current-x").textContent = x.toFixed(1);
    this.shadowRoot.getElementById("current-y").textContent = y.toFixed(1);
    this.shadowRoot.getElementById("current-z").textContent = z.toFixed(1);

    const magnitude = Math.sqrt(x*x + y*y + z*z);
    this.shadowRoot.getElementById("current-mag").textContent = magnitude.toFixed(1);

    // Update max thrust if available
    const propulsion = ship?.systems?.propulsion;
    if (propulsion?.max_thrust) {
      this._maxThrust = propulsion.max_thrust;
    }
  }

  async _applyThrust() {
    const x = parseFloat(this.shadowRoot.getElementById("thrust-x").value) || 0;
    const y = parseFloat(this.shadowRoot.getElementById("thrust-y").value) || 0;
    const z = parseFloat(this.shadowRoot.getElementById("thrust-z").value) || 0;

    try {
      // DEBUG: Use set_thrust_vector for direct world-frame thrust
      // This bypasses ship-frame rotation (not realistic for gameplay)
      await wsClient.sendShipCommand("set_thrust_vector", { x, y, z });
      console.log("DEBUG: Applied vector thrust", { x, y, z });
    } catch (error) {
      console.error("Set thrust vector failed:", error);
    }
  }

  _zeroAll() {
    this.shadowRoot.getElementById("thrust-x").value = 0;
    this.shadowRoot.getElementById("thrust-y").value = 0;
    this.shadowRoot.getElementById("thrust-z").value = 0;
    this._thrustX = 0;
    this._thrustY = 0;
    this._thrustZ = 0;
    this._applyThrust();
  }

  async _emergencyStop() {
    this.shadowRoot.getElementById("thrust-x").value = 0;
    this.shadowRoot.getElementById("thrust-y").value = 0;
    this.shadowRoot.getElementById("thrust-z").value = 0;

    try {
      // Zero all thrust (both scalar and vector modes)
      await wsClient.sendShipCommand("set_thrust", { thrust: 0 });
      console.log("DEBUG: Emergency stop activated");
    } catch (error) {
      console.error("Emergency stop failed:", error);
    }
  }
}

customElements.define("manual-thrust", ManualThrust);
export { ManualThrust };
