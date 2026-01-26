/**
 * Position to Heading Calculator
 * Calculate heading from relative or absolute position coordinates
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class PositionHeadingCalculator extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._mode = "relative"; // "relative" or "absolute"
  }

  connectedCallback() {
    this.render();
    this._setupEvents();
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
          margin-bottom: 12px;
        }

        .mode-toggle {
          display: flex;
          gap: 8px;
          margin-bottom: 16px;
        }

        .mode-btn {
          flex: 1;
          padding: 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          font-size: 0.75rem;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .mode-btn.active {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .input-group {
          margin-bottom: 12px;
        }

        .input-group label {
          display: block;
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          margin-bottom: 4px;
        }

        .input-row {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
        }

        .input-row input {
          padding: 8px;
          background: var(--bg-primary, #0a0a0f);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
        }

        .input-row input:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .input-row label {
          font-size: 0.65rem;
          text-align: center;
          margin-bottom: 0;
        }

        .current-position {
          margin-bottom: 16px;
          padding: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
        }

        .current-position strong {
          color: var(--text-primary, #e0e0e0);
        }

        .result {
          margin-top: 16px;
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-active, #3a3a4a);
          border-radius: 6px;
        }

        .result-label {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          margin-bottom: 8px;
        }

        .result-values {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 12px;
        }

        .result-value {
          text-align: center;
        }

        .result-value-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          margin-bottom: 4px;
        }

        .result-value-number {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.2rem;
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .actions {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }

        .btn {
          flex: 1;
          padding: 10px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
          cursor: pointer;
          min-height: 44px;
          transition: all 0.15s ease;
        }

        .btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .btn.primary {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
          font-weight: 600;
        }

        .btn.primary:hover:not(:disabled) {
          filter: brightness(1.1);
        }
      </style>

      <div class="section-title">Position to Heading</div>

      <div class="mode-toggle">
        <button class="mode-btn active" data-mode="relative">Relative</button>
        <button class="mode-btn" data-mode="absolute">Absolute</button>
      </div>

      <div class="current-position" id="current-pos">
        <strong>Current Position:</strong> <span id="pos-display">Loading...</span>
      </div>

      <div class="input-group">
        <label>Target Position</label>
        <div class="input-row">
          <div>
            <label>X</label>
            <input type="number" id="target-x" value="0" step="0.1" />
          </div>
          <div>
            <label>Y</label>
            <input type="number" id="target-y" value="0" step="0.1" />
          </div>
          <div>
            <label>Z</label>
            <input type="number" id="target-z" value="0" step="0.1" />
          </div>
        </div>
      </div>

      <div class="result" id="result" style="display: none;">
        <div class="result-label">Calculated Heading</div>
        <div class="result-values">
          <div class="result-value">
            <div class="result-value-label">Pitch</div>
            <div class="result-value-number" id="result-pitch">0.0°</div>
          </div>
          <div class="result-value">
            <div class="result-value-label">Yaw</div>
            <div class="result-value-number" id="result-yaw">0.0°</div>
          </div>
          <div class="result-value">
            <div class="result-value-label">Range</div>
            <div class="result-value-number" id="result-range">0.0m</div>
          </div>
        </div>
      </div>

      <div class="actions">
        <button class="btn" id="calculate-btn">Calculate</button>
        <button class="btn primary" id="point-btn" disabled>Point At</button>
      </div>
    `;
  }

  _setupEvents() {
    // Mode toggle
    this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._mode = btn.dataset.mode;
        this.shadowRoot.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        this._updateCurrentPosition();
      });
    });

    // Calculate button
    this.shadowRoot.getElementById("calculate-btn").addEventListener("click", () => {
      this._calculate();
    });

    // Point at button
    this.shadowRoot.getElementById("point-btn").addEventListener("click", () => {
      this._pointAt();
    });

    // Update current position periodically
    this._updateCurrentPosition();
    setInterval(() => this._updateCurrentPosition(), 1000);
  }

  _updateCurrentPosition() {
    const nav = stateManager.getNavigation();
    const pos = nav.position || [0, 0, 0];
    const display = this.shadowRoot.getElementById("pos-display");
    display.textContent = `${pos[0].toFixed(1)}, ${pos[1].toFixed(1)}, ${pos[2].toFixed(1)}`;
  }

  _calculate() {
    const nav = stateManager.getNavigation();
    const currentPos = nav.position || [0, 0, 0];

    const targetX = parseFloat(this.shadowRoot.getElementById("target-x").value) || 0;
    const targetY = parseFloat(this.shadowRoot.getElementById("target-y").value) || 0;
    const targetZ = parseFloat(this.shadowRoot.getElementById("target-z").value) || 0;

    let targetPos;
    if (this._mode === "relative") {
      // Relative: add to current position
      targetPos = {
        x: currentPos[0] + targetX,
        y: currentPos[1] + targetY,
        z: currentPos[2] + targetZ
      };
    } else {
      // Absolute: use directly
      targetPos = { x: targetX, y: targetY, z: targetZ };
    }

    // Calculate bearing
    const dx = targetPos.x - currentPos[0];
    const dy = targetPos.y - currentPos[1];
    const dz = targetPos.z - currentPos[2];

    // Calculate range
    const range = Math.sqrt(dx * dx + dy * dy + dz * dz);

    // Calculate yaw (horizontal angle)
    const yaw = Math.atan2(dy, dx) * (180 / Math.PI);

    // Calculate pitch (vertical angle)
    const horizontalDist = Math.sqrt(dx * dx + dy * dy);
    const pitch = Math.atan2(dz, horizontalDist) * (180 / Math.PI);

    // Display results
    this.shadowRoot.getElementById("result-pitch").textContent = `${pitch.toFixed(1)}°`;
    this.shadowRoot.getElementById("result-yaw").textContent = `${yaw.toFixed(1)}°`;
    this.shadowRoot.getElementById("result-range").textContent = `${range.toFixed(1)}m`;
    this.shadowRoot.getElementById("result").style.display = "block";
    this.shadowRoot.getElementById("point-btn").disabled = false;

    // Store for point_at command
    this._calculatedHeading = { pitch, yaw, roll: 0 };
    this._targetPosition = targetPos;
  }

  async _pointAt() {
    if (!this._targetPosition) {
      this._calculate(); // Recalculate if needed
    }

    try {
      const response = await wsClient.sendShipCommand("point_at", {
        position: this._targetPosition
      });
      
      this._showMessage(`Pointing at position (${this._targetPosition.x.toFixed(1)}, ${this._targetPosition.y.toFixed(1)}, ${this._targetPosition.z.toFixed(1)})`, "info");
    } catch (error) {
      console.error("Point at position failed:", error);
      this._showMessage(`Point failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("position-heading-calculator", PositionHeadingCalculator);
export { PositionHeadingCalculator };
