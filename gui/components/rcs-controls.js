/**
 * RCS Controls
 * Quick actions for attitude control: flip, point at target, manual pitch/yaw/roll
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { calculate3DBearing } from "../js/helm-requests.js";

class RCSControls extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._selectedTarget = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupEvents();
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

    // Listen for contact selection from sensor panel
    document.addEventListener("contact-selected", (e) => {
      this._selectedTarget = e.detail.contactId;
      this._updateTargetDisplay();
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

        .section {
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .quick-actions {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
        }

        .action-btn {
          padding: 12px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
          cursor: pointer;
          min-height: 44px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          transition: all 0.15s ease;
        }

        .action-btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .action-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .action-btn.primary {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .action-btn.warning {
          border-color: var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .action-btn.full-width {
          grid-column: 1 / -1;
        }

        .btn-icon {
          font-size: 1.2rem;
        }

        .btn-label {
          font-size: 0.7rem;
          text-transform: uppercase;
        }

        .target-info {
          padding: 12px;
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 6px;
          margin-bottom: 12px;
        }

        .target-info.no-target {
          background: rgba(85, 85, 102, 0.1);
          border-color: var(--border-default, #2a2a3a);
        }

        .target-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-bottom: 4px;
        }

        .target-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
        }

        .target-details {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-top: 8px;
          font-size: 0.7rem;
        }

        .detail-item {
          text-align: center;
        }

        .detail-label {
          color: var(--text-dim, #555566);
        }

        .detail-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-secondary, #888899);
        }

        .manual-controls {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
        }

        .axis-group {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
        }

        .axis-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .axis-btns {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .axis-btn {
          width: 40px;
          height: 32px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          cursor: pointer;
          font-size: 0.8rem;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: auto;
          padding: 0;
        }

        .axis-btn:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .axis-btn:active {
          background: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .current-attitude {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
          text-align: center;
        }

        .attitude-item {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .attitude-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-bottom: 2px;
        }

        .attitude-value {
          font-size: 0.9rem;
          color: var(--text-primary, #e0e0e0);
        }

        .stop-rotation-btn {
          width: 100%;
          margin-top: 8px;
          padding: 8px;
          background: var(--status-critical, #ff4444);
          border: none;
          border-radius: 4px;
          color: white;
          font-size: 0.75rem;
          cursor: pointer;
          min-height: 36px;
        }

        .stop-rotation-btn:hover {
          filter: brightness(1.1);
        }
      </style>

      <!-- Current Attitude Display -->
      <div class="section">
        <div class="section-title">Current Attitude</div>
        <div class="current-attitude">
          <div class="attitude-item">
            <div class="attitude-label">Pitch</div>
            <div class="attitude-value" id="current-pitch">+0.0°</div>
          </div>
          <div class="attitude-item">
            <div class="attitude-label">Yaw</div>
            <div class="attitude-value" id="current-yaw">000.0°</div>
          </div>
          <div class="attitude-item">
            <div class="attitude-label">Roll</div>
            <div class="attitude-value" id="current-roll">+0.0°</div>
          </div>
        </div>
      </div>

      <!-- Target Info -->
      <div class="section">
        <div class="section-title">Selected Target</div>
        <div class="target-info no-target" id="target-info">
          <div class="target-label">No target selected</div>
          <div class="target-value" id="target-name">Select a contact from sensors</div>
          <div class="target-details" id="target-details" style="display: none;">
            <div class="detail-item">
              <div class="detail-label">Bearing</div>
              <div class="detail-value" id="target-bearing">---°</div>
            </div>
            <div class="detail-item">
              <div class="detail-label">Range</div>
              <div class="detail-value" id="target-range">--- km</div>
            </div>
            <div class="detail-item">
              <div class="detail-label">Closure</div>
              <div class="detail-value" id="target-closure">--- m/s</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="section">
        <div class="section-title">Quick Actions</div>
        <div class="quick-actions">
          <button class="action-btn warning" id="flip-btn">
            <span class="btn-icon">↻</span>
            <span class="btn-label">FLIP 180°</span>
          </button>
          <button class="action-btn" id="point-target-btn" disabled>
            <span class="btn-icon">◎</span>
            <span class="btn-label">Point at Target</span>
          </button>
          <button class="action-btn" id="point-prograde-btn">
            <span class="btn-icon">→</span>
            <span class="btn-label">Prograde</span>
          </button>
          <button class="action-btn" id="point-retrograde-btn">
            <span class="btn-icon">←</span>
            <span class="btn-label">Retrograde</span>
          </button>
        </div>
      </div>

      <!-- Manual Attitude Control -->
      <div class="section">
        <div class="section-title">Manual RCS</div>
        <div class="manual-controls">
          <div class="axis-group">
            <span class="axis-label">Pitch</span>
            <div class="axis-btns">
              <button class="axis-btn" data-axis="pitch" data-delta="10">▲</button>
              <button class="axis-btn" data-axis="pitch" data-delta="-10">▼</button>
            </div>
          </div>
          <div class="axis-group">
            <span class="axis-label">Yaw</span>
            <div class="axis-btns">
              <button class="axis-btn" data-axis="yaw" data-delta="-15">◄</button>
              <button class="axis-btn" data-axis="yaw" data-delta="15">►</button>
            </div>
          </div>
          <div class="axis-group">
            <span class="axis-label">Roll</span>
            <div class="axis-btns">
              <button class="axis-btn" data-axis="roll" data-delta="-10">↺</button>
              <button class="axis-btn" data-axis="roll" data-delta="10">↻</button>
            </div>
          </div>
        </div>
        <button class="stop-rotation-btn" id="stop-rotation-btn">STOP ROTATION</button>
      </div>
    `;
  }

  _setupEvents() {
    // Quick action buttons
    this.shadowRoot.getElementById("flip-btn").addEventListener("click", () => {
      this._flip();
    });

    this.shadowRoot.getElementById("point-target-btn").addEventListener("click", () => {
      this._pointAtTarget();
    });

    this.shadowRoot.getElementById("point-prograde-btn").addEventListener("click", () => {
      this._pointPrograde();
    });

    this.shadowRoot.getElementById("point-retrograde-btn").addEventListener("click", () => {
      this._pointRetrograde();
    });

    // Manual axis controls
    this.shadowRoot.querySelectorAll(".axis-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const axis = btn.dataset.axis;
        const delta = parseFloat(btn.dataset.delta);
        this._rotateAxis(axis, delta);
      });
    });

    // Stop rotation
    this.shadowRoot.getElementById("stop-rotation-btn").addEventListener("click", () => {
      this._stopRotation();
    });
  }

  _updateDisplay() {
    const nav = stateManager.getNavigation();
    const heading = nav.heading || { pitch: 0, yaw: 0, roll: 0 };

    // Update current attitude display
    const pitchSign = heading.pitch >= 0 ? "+" : "";
    this.shadowRoot.getElementById("current-pitch").textContent = 
      `${pitchSign}${(heading.pitch || 0).toFixed(1)}°`;
    
    // Format yaw to always show 3 digits
    const yawNorm = ((heading.yaw || 0) + 360) % 360;
    this.shadowRoot.getElementById("current-yaw").textContent = 
      `${yawNorm.toFixed(1).padStart(5, "0")}°`;
    
    const rollSign = (heading.roll || 0) >= 0 ? "+" : "";
    this.shadowRoot.getElementById("current-roll").textContent = 
      `${rollSign}${(heading.roll || 0).toFixed(1)}°`;

    this._updateTargetDisplay();
  }

  _updateTargetDisplay() {
    const targetInfo = this.shadowRoot.getElementById("target-info");
    const targetName = this.shadowRoot.getElementById("target-name");
    const targetDetails = this.shadowRoot.getElementById("target-details");
    const pointBtn = this.shadowRoot.getElementById("point-target-btn");

    if (!this._selectedTarget) {
      targetInfo.classList.add("no-target");
      targetName.textContent = "Select a contact from sensors";
      targetDetails.style.display = "none";
      pointBtn.disabled = true;
      return;
    }

    // Find contact in state
    const contacts = stateManager.getContacts();
    const contact = contacts.find(c => 
      (c.contact_id || c.id) === this._selectedTarget
    );

    if (!contact) {
      targetInfo.classList.add("no-target");
      targetName.textContent = `Target lost: ${this._selectedTarget}`;
      targetDetails.style.display = "none";
      pointBtn.disabled = true;
      return;
    }

    targetInfo.classList.remove("no-target");
    targetName.textContent = `${contact.contact_id || contact.id} (${contact.classification || "UNKNOWN"})`;
    targetDetails.style.display = "grid";
    pointBtn.disabled = false;

    // Update target details
    const bearing = contact.bearing ?? contact.bearing_to ?? 0;
    const range = contact.range ?? contact.distance ?? 0;
    const closure = contact.range_rate ?? contact.closure ?? 0;

    this.shadowRoot.getElementById("target-bearing").textContent = 
      `${bearing.toFixed(0).padStart(3, "0")}°`;
    this.shadowRoot.getElementById("target-range").textContent = 
      range >= 1000 ? `${(range / 1000).toFixed(1)} km` : `${range.toFixed(0)} m`;
    this.shadowRoot.getElementById("target-closure").textContent = 
      `${closure >= 0 ? "+" : ""}${closure.toFixed(0)} m/s`;
  }

  async _flip() {
    // Flip = rotate 180° on yaw axis
    const nav = stateManager.getNavigation();
    const currentYaw = nav.heading?.yaw || 0;
    const newYaw = (currentYaw + 180) % 360;

    try {
      console.log("Executing FLIP: current yaw", currentYaw, "-> target yaw", newYaw);
      await wsClient.sendShipCommand("set_orientation", {
        pitch: nav.heading?.pitch || 0,
        yaw: newYaw,
        roll: nav.heading?.roll || 0
      });
      this._showMessage("Flip initiated - rotating 180°", "info");
    } catch (error) {
      console.error("Flip command failed:", error);
      this._showMessage(`Flip failed: ${error.message}`, "error");
    }
  }

  async _pointAtTarget() {
    if (!this._selectedTarget) {
      this._showMessage("No target selected", "warning");
      return;
    }

    const contacts = stateManager.getContacts();
    const contact = contacts.find(c =>
      (c.contact_id || c.id) === this._selectedTarget
    );

    if (!contact) {
      this._showMessage("Target not found", "error");
      return;
    }

    // Calculate 3D bearing to target (both pitch AND yaw)
    const ship = stateManager.getShipState();
    const shipPos = ship?.position || { x: 0, y: 0, z: 0 };
    const targetPos = contact.position;

    if (!targetPos) {
      this._showMessage("Cannot determine target position", "error");
      return;
    }

    // Calculate proper 3D bearing including pitch
    const bearing = calculate3DBearing(shipPos, targetPos);

    try {
      console.log("Pointing at target:", this._selectedTarget, "bearing:", bearing);
      await wsClient.sendShipCommand("set_orientation", {
        pitch: bearing.pitch,
        yaw: bearing.yaw,
        roll: 0
      });
      this._showMessage(`Pointing at ${this._selectedTarget} (P: ${bearing.pitch.toFixed(1)}° Y: ${bearing.yaw.toFixed(1)}°)`, "info");
    } catch (error) {
      console.error("Point at target failed:", error);
      this._showMessage(`Point at target failed: ${error.message}`, "error");
    }
  }

  async _pointPrograde() {
    // Point in direction of travel (velocity vector)
    const nav = stateManager.getNavigation();
    const vel = nav.velocity || [0, 0, 0];

    const vx = vel[0] ?? vel.x ?? 0;
    const vy = vel[1] ?? vel.y ?? 0;
    const vz = vel[2] ?? vel.z ?? 0;

    const speed = Math.sqrt(vx * vx + vy * vy + vz * vz);
    if (speed < 0.1) {
      this._showMessage("No significant velocity", "warning");
      return;
    }

    // Calculate 3D bearing from velocity vector
    const horizontalSpeed = Math.sqrt(vx * vx + vy * vy);
    const yaw = Math.atan2(vy, vx) * (180 / Math.PI);
    const pitch = Math.atan2(vz, horizontalSpeed) * (180 / Math.PI);

    try {
      console.log("Pointing prograde: P:", pitch.toFixed(1), "Y:", yaw.toFixed(1));
      await wsClient.sendShipCommand("set_orientation", {
        pitch: pitch,
        yaw: yaw,
        roll: 0
      });
      this._showMessage(`Pointing prograde (P: ${pitch.toFixed(1)}° Y: ${yaw.toFixed(1)}°)`, "info");
    } catch (error) {
      console.error("Point prograde failed:", error);
      this._showMessage(`Point prograde failed: ${error.message}`, "error");
    }
  }

  async _pointRetrograde() {
    // Point opposite to direction of travel
    const nav = stateManager.getNavigation();
    const vel = nav.velocity || [0, 0, 0];

    const vx = vel[0] ?? vel.x ?? 0;
    const vy = vel[1] ?? vel.y ?? 0;
    const vz = vel[2] ?? vel.z ?? 0;

    const speed = Math.sqrt(vx * vx + vy * vy + vz * vz);
    if (speed < 0.1) {
      this._showMessage("No significant velocity", "warning");
      return;
    }

    // Calculate 3D bearing from opposite velocity vector
    const horizontalSpeed = Math.sqrt(vx * vx + vy * vy);
    const yaw = Math.atan2(-vy, -vx) * (180 / Math.PI);
    const pitch = Math.atan2(-vz, horizontalSpeed) * (180 / Math.PI);

    try {
      console.log("Pointing retrograde: P:", pitch.toFixed(1), "Y:", yaw.toFixed(1));
      await wsClient.sendShipCommand("set_orientation", {
        pitch: pitch,
        yaw: yaw,
        roll: 0
      });
      this._showMessage(`Pointing retrograde (P: ${pitch.toFixed(1)}° Y: ${yaw.toFixed(1)}°)`, "info");
    } catch (error) {
      console.error("Point retrograde failed:", error);
      this._showMessage(`Point retrograde failed: ${error.message}`, "error");
    }
  }

  async _rotateAxis(axis, delta) {
    const nav = stateManager.getNavigation();
    const heading = nav.heading || { pitch: 0, yaw: 0, roll: 0 };

    try {
      console.log(`Rotating ${axis} by ${delta}°`);
      await wsClient.sendShipCommand("rotate", {
        axis: axis,
        amount: delta
      });
    } catch (error) {
      console.error(`Rotate ${axis} failed:`, error);
    }
  }

  async _stopRotation() {
    try {
      console.log("Stopping rotation");
      await wsClient.sendShipCommand("set_angular_velocity", {
        pitch: 0,
        yaw: 0,
        roll: 0
      });
      this._showMessage("Rotation stopped", "info");
    } catch (error) {
      console.error("Stop rotation failed:", error);
      this._showMessage(`Stop rotation failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("rcs-controls", RCSControls);
export { RCSControls };
