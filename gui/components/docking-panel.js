/**
 * Docking Panel
 * Provides docking request/cancel controls and approach guidance display.
 * Subscribes to stateManager for docking state.
 * Sends docking commands via wsClient.sendShipCommand().
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

/** Docking state constants used for display logic */
const DOCKING_STATES = {
  IDLE: "idle",
  REQUESTING: "requesting",
  APPROVED: "approved",
  DOCKING: "docking",
  DOCKED: "docked",
};

class DockingPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._dockingState = null;
    this._selectedTargetId = null;
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
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", (value, key, fullState) => {
      this._dockingState = this._extractDockingState(fullState);
      this._refreshContactList();
      this._updateDisplay();
    });
  }

  /**
   * Extract docking state from various possible state locations.
   * The server may place it under systems.docking or at the top-level docking key.
   */
  _extractDockingState(fullState) {
    const ship = stateManager.getShipState();
    if (!ship) return null;
    // Prefer top-level docking object (full state from telemetry)
    // over systems.docking which is just a status string
    const docking = ship.docking;
    if (docking && typeof docking === "object") return docking;
    const sysDocking = ship.systems?.docking;
    if (sysDocking && typeof sysDocking === "object") return sysDocking;
    return null;
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        /* Status display */
        .status-display {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 16px;
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .status-indicator {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .status-indicator.idle {
          background: var(--text-dim, #555566);
        }

        .status-indicator.requesting {
          background: var(--status-warning, #ffaa00);
          animation: pulse-amber 1.5s ease-in-out infinite;
        }

        .status-indicator.approved {
          background: var(--status-nominal, #00ff88);
        }

        .status-indicator.docking {
          background: var(--status-info, #00aaff);
          animation: pulse-blue 1.5s ease-in-out infinite;
        }

        .status-indicator.docked {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 8px rgba(0, 255, 136, 0.4);
        }

        @keyframes pulse-amber {
          0%, 100% { box-shadow: 0 0 4px rgba(255, 170, 0, 0.3); }
          50% { box-shadow: 0 0 14px rgba(255, 170, 0, 0.6); }
        }

        @keyframes pulse-blue {
          0%, 100% { box-shadow: 0 0 4px rgba(0, 170, 255, 0.3); }
          50% { box-shadow: 0 0 14px rgba(0, 170, 255, 0.6); }
        }

        .status-info {
          flex: 1;
        }

        .status-badge {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          font-weight: 700;
          letter-spacing: 1.5px;
          text-transform: uppercase;
        }

        .status-badge.idle { color: var(--text-dim, #555566); }
        .status-badge.requesting { color: var(--status-warning, #ffaa00); }
        .status-badge.approved { color: var(--status-nominal, #00ff88); }
        .status-badge.docking { color: var(--status-info, #00aaff); }
        .status-badge.docked { color: var(--status-nominal, #00ff88); }

        .status-text {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
          margin-top: 2px;
        }

        /* Target selection */
        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .target-section {
          margin-bottom: 16px;
        }

        .target-select {
          width: 100%;
          padding: 8px 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          min-height: 36px;
          box-sizing: border-box;
        }

        .target-select:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .target-select:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        /* Approach guidance */
        .approach-guidance {
          display: none;
          margin-bottom: 16px;
          padding: 10px;
          background: rgba(0, 170, 255, 0.05);
          border: 1px solid rgba(0, 170, 255, 0.15);
          border-radius: 6px;
        }

        .approach-guidance.visible {
          display: block;
        }

        .guidance-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
        }

        .guidance-item {
          text-align: center;
        }

        .guidance-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .guidance-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        /* Control buttons */
        .controls {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }

        .ctrl-btn {
          padding: 10px 6px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-secondary, #888899);
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          cursor: pointer;
          transition: all 0.1s ease;
          min-height: 44px;
          letter-spacing: 0.3px;
        }

        .ctrl-btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }

        .ctrl-btn:active:not(:disabled) {
          transform: scale(0.96);
        }

        .ctrl-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .ctrl-btn.request {
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .ctrl-btn.request:hover:not(:disabled) {
          background: rgba(0, 255, 136, 0.1);
          border-color: var(--status-nominal, #00ff88);
        }

        .ctrl-btn.cancel {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .ctrl-btn.cancel:hover:not(:disabled) {
          background: rgba(255, 68, 68, 0.15);
          border-color: var(--status-critical, #ff4444);
        }

        .ctrl-btn.undock {
          grid-column: 1 / -1;
          border-color: var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .ctrl-btn.undock:hover:not(:disabled) {
          background: rgba(255, 170, 0, 0.12);
          border-color: var(--status-warning, #ffaa00);
        }

        /* Docked state prominent display */
        .docked-info {
          display: none;
          margin-bottom: 16px;
          padding: 14px;
          background: rgba(0, 255, 136, 0.06);
          border: 1px solid rgba(0, 255, 136, 0.2);
          border-radius: 6px;
          text-align: center;
        }

        .docked-info.visible {
          display: block;
        }

        .docked-target {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1rem;
          font-weight: 700;
          color: var(--status-nominal, #00ff88);
          letter-spacing: 0.5px;
          margin-bottom: 6px;
        }

        .docked-secured {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .service-report {
          margin-top: 10px;
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px 12px;
          text-align: left;
          padding: 8px 12px;
          background: rgba(0, 255, 136, 0.04);
          border-radius: 4px;
        }

        .service-item {
          display: flex;
          justify-content: space-between;
          font-size: 0.7rem;
        }

        .service-label {
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }

        .service-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--status-nominal, #00ff88);
          font-weight: 600;
        }

        .service-value.none {
          color: var(--text-dim, #555566);
        }

        .hidden {
          display: none !important;
        }

        @media (max-width: 768px) {
          .guidance-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
      </style>

      <!-- Docking Status Display -->
      <div class="status-display">
        <div class="status-indicator idle" id="status-indicator"></div>
        <div class="status-info">
          <div class="status-badge idle" id="status-badge">IDLE</div>
          <div class="status-text" id="status-text">No active docking procedure</div>
        </div>
      </div>

      <!-- Target Selection -->
      <div class="target-section">
        <div class="section-title">Dock With</div>
        <select class="target-select" id="target-select">
          <option value="">-- Select Target --</option>
        </select>
      </div>

      <!-- Docked State Info (visible when docked) -->
      <div class="docked-info" id="docked-info">
        <div class="docked-target" id="docked-target">DOCKED</div>
        <div class="docked-secured">All systems secured. Ship stationary.</div>
        <div class="service-report" id="service-report" style="display:none;">
          <div class="service-item">
            <span class="service-label">Hull</span>
            <span class="service-value" id="svc-hull">--</span>
          </div>
          <div class="service-item">
            <span class="service-label">Subsystems</span>
            <span class="service-value" id="svc-subsystems">--</span>
          </div>
          <div class="service-item">
            <span class="service-label">Fuel</span>
            <span class="service-value" id="svc-fuel">--</span>
          </div>
          <div class="service-item">
            <span class="service-label">Weapons</span>
            <span class="service-value" id="svc-weapons">--</span>
          </div>
        </div>
      </div>

      <!-- Approach Guidance (visible during docking) -->
      <div class="approach-guidance" id="approach-guidance">
        <div class="section-title">Approach Guidance</div>
        <div class="guidance-grid">
          <div class="guidance-item">
            <div class="guidance-label">Range</div>
            <div class="guidance-value" id="guidance-range">--</div>
          </div>
          <div class="guidance-item">
            <div class="guidance-label">Closing Speed</div>
            <div class="guidance-value" id="guidance-speed">--</div>
          </div>
          <div class="guidance-item">
            <div class="guidance-label">Alignment</div>
            <div class="guidance-value" id="guidance-alignment">--</div>
          </div>
        </div>
      </div>

      <!-- Controls -->
      <div class="controls">
        <button class="ctrl-btn request" id="btn-request" title="Request docking clearance (D)">Request Docking</button>
        <button class="ctrl-btn cancel" id="btn-cancel" title="Cancel docking procedure" disabled>Cancel Docking</button>
        <button class="ctrl-btn undock hidden" id="btn-undock" title="Undock from target (U)">Undock</button>
      </div>
    `;
  }

  _setupInteraction() {
    // Request docking
    this.shadowRoot.getElementById("btn-request").addEventListener("click", () => {
      this._requestDocking();
    });

    // Cancel docking
    this.shadowRoot.getElementById("btn-cancel").addEventListener("click", () => {
      this._cancelDocking();
    });

    // Undock
    this.shadowRoot.getElementById("btn-undock").addEventListener("click", () => {
      this._undock();
    });

    // Track target selection changes
    this.shadowRoot.getElementById("target-select").addEventListener("change", (e) => {
      this._selectedTargetId = e.target.value || null;
    });

    // Keyboard shortcuts: D to request docking, U to undock
    this._keyHandler = (e) => {
      const tag = e.target.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if (e.composedPath().some(el => {
        const t = el.tagName?.toLowerCase();
        return t === "input" || t === "textarea" || t === "select";
      })) return;

      const key = e.key.toUpperCase();
      if (key === "D") {
        e.preventDefault();
        this._requestDocking();
      } else if (key === "U") {
        // Only undock when actually docked
        if (this._getCurrentDockingState() === DOCKING_STATES.DOCKED) {
          e.preventDefault();
          this._undock();
        }
      }
    };
    document.addEventListener("keydown", this._keyHandler);
  }

  /**
   * Refresh the contact dropdown from stateManager.
   * Preserves the current selection if the contact still exists.
   */
  _refreshContactList() {
    const select = this.shadowRoot.getElementById("target-select");
    const contacts = stateManager.getContacts();
    const previousValue = select.value;

    select.innerHTML = '<option value="">-- Select Target --</option>';
    if (Array.isArray(contacts)) {
      contacts.forEach(contact => {
        const id = contact.contact_id || contact.id;
        const option = document.createElement("option");
        option.value = id;
        option.textContent = `${id} — ${contact.name || contact.classification || "UNKNOWN"}`;
        select.appendChild(option);
      });
    }

    // Restore previous selection if still available
    if (previousValue && select.querySelector(`option[value="${previousValue}"]`)) {
      select.value = previousValue;
      this._selectedTargetId = previousValue;
    } else {
      this._selectedTargetId = select.value || null;
    }

    // Disable target selection when docking is actively in progress
    const state = this._getCurrentDockingState();
    const locked = state === DOCKING_STATES.DOCKING || state === DOCKING_STATES.DOCKED;
    select.disabled = locked;
  }

  /**
   * Determine the current docking state string from server data.
   * Falls back to IDLE if no docking state is present.
   */
  _getCurrentDockingState() {
    const ds = this._dockingState;
    if (!ds) return DOCKING_STATES.IDLE;

    const raw = (ds.docking_state || ds.status || ds.state || "idle").toLowerCase();

    // Normalize server values to known states
    if (raw === "requesting" || raw === "requested" || raw === "docking_initiated") return DOCKING_STATES.REQUESTING;
    if (raw === "approved" || raw === "cleared") return DOCKING_STATES.APPROVED;
    if (raw === "docking" || raw === "approach" || raw === "approaching") return DOCKING_STATES.DOCKING;
    if (raw === "docked") return DOCKING_STATES.DOCKED;
    return DOCKING_STATES.IDLE;
  }

  _updateDisplay() {
    const state = this._getCurrentDockingState();
    const ds = this._dockingState;
    const isDocked = state === DOCKING_STATES.DOCKED;

    const indicator = this.shadowRoot.getElementById("status-indicator");
    const badge = this.shadowRoot.getElementById("status-badge");
    const statusText = this.shadowRoot.getElementById("status-text");
    const guidance = this.shadowRoot.getElementById("approach-guidance");
    const dockedInfo = this.shadowRoot.getElementById("docked-info");
    const dockedTarget = this.shadowRoot.getElementById("docked-target");
    const targetSection = this.shadowRoot.querySelector(".target-section");
    const btnRequest = this.shadowRoot.getElementById("btn-request");
    const btnCancel = this.shadowRoot.getElementById("btn-cancel");
    const btnUndock = this.shadowRoot.getElementById("btn-undock");

    // Reset classes
    indicator.className = `status-indicator ${state}`;
    badge.className = `status-badge ${state}`;
    badge.textContent = state.toUpperCase();

    // Hide/show docked-only elements
    dockedInfo.classList.toggle("visible", isDocked);
    btnUndock.classList.toggle("hidden", !isDocked);
    // Hide target selector and request/cancel when docked
    targetSection.classList.toggle("hidden", isDocked);
    btnRequest.classList.toggle("hidden", isDocked);
    btnCancel.classList.toggle("hidden", isDocked);

    // State-specific text and button states
    switch (state) {
      case DOCKING_STATES.IDLE:
        statusText.textContent = "No active docking procedure";
        btnRequest.disabled = false;
        btnCancel.disabled = true;
        guidance.classList.remove("visible");
        break;

      case DOCKING_STATES.REQUESTING:
        statusText.textContent = "Requesting docking clearance...";
        btnRequest.disabled = true;
        btnCancel.disabled = false;
        guidance.classList.remove("visible");
        break;

      case DOCKING_STATES.APPROVED: {
        const targetLabel = ds?.target_id || ds?.target || "target";
        statusText.textContent = `Docking approved \u2014 approach ${targetLabel}`;
        btnRequest.disabled = true;
        btnCancel.disabled = false;
        guidance.classList.remove("visible");
        break;
      }

      case DOCKING_STATES.DOCKING:
        statusText.textContent = "Docking approach in progress";
        btnRequest.disabled = true;
        btnCancel.disabled = false;
        guidance.classList.add("visible");
        this._updateGuidance(ds);
        break;

      case DOCKING_STATES.DOCKED: {
        const targetName = ds?.target_id || ds?.target || "target";
        statusText.textContent = "All systems secured";
        dockedTarget.textContent = `DOCKED with ${targetName}`;
        guidance.classList.remove("visible");
        this._updateServiceReport(ds);
        break;
      }
    }
  }

  /**
   * Update approach guidance readouts from docking state data.
   */
  _updateGuidance(ds) {
    if (!ds) return;

    const rangeEl = this.shadowRoot.getElementById("guidance-range");
    const speedEl = this.shadowRoot.getElementById("guidance-speed");
    const alignEl = this.shadowRoot.getElementById("guidance-alignment");

    // The server sends last_check: {range, relative_velocity}
    const lc = ds.last_check || {};
    const range = lc.range ?? ds.range;
    rangeEl.textContent = range !== undefined && range !== null
      ? this._formatRange(range)
      : "--";

    const speed = lc.relative_velocity ?? ds.approach_speed;
    speedEl.textContent = speed !== undefined && speed !== null
      ? `${speed.toFixed(1)} m/s`
      : "--";

    // Show docking criteria: range ≤ docking_range and speed ≤ max_relative_velocity
    const maxRange = ds.docking_range || 50;
    const maxSpeed = ds.max_relative_velocity || 1.0;
    const rangeOk = range !== undefined && range <= maxRange;
    const speedOk = speed !== undefined && speed <= maxSpeed;
    alignEl.textContent = rangeOk && speedOk ? "GO" : `Need ≤${maxRange}m / ≤${maxSpeed}m/s`;
  }

  /**
   * Update the service report section when docked at a station.
   * Shows what was repaired, refueled, and resupplied.
   */
  _updateServiceReport(ds) {
    const report = ds?.service_report;
    const container = this.shadowRoot.getElementById("service-report");
    if (!container) return;

    if (!report) {
      container.style.display = "none";
      return;
    }

    container.style.display = "";

    const setField = (id, value, zeroLabel) => {
      const el = this.shadowRoot.getElementById(id);
      if (!el) return;
      if (value > 0) {
        el.textContent = typeof value === "number" && value % 1 !== 0
          ? `+${value.toFixed(0)}`
          : `+${value}`;
        el.classList.remove("none");
      } else {
        el.textContent = zeroLabel || "OK";
        el.classList.add("none");
      }
    };

    setField("svc-hull", report.hull_repaired || 0, "OK");
    setField("svc-subsystems", report.subsystems_repaired || 0, "OK");
    setField("svc-fuel", report.fuel_added || 0, "FULL");
    setField("svc-weapons", report.weapons_resupplied || 0, "FULL");
  }

  /**
   * Format range value into a human-readable string with appropriate units.
   */
  _formatRange(meters) {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(2)} km`;
    }
    return `${meters.toFixed(0)} m`;
  }

  async _requestDocking() {
    const targetId = this._selectedTargetId;
    if (!targetId) {
      this._showMessage("Select a target before requesting docking", "error");
      return;
    }

    try {
      const response = await wsClient.sendShipCommand("request_docking", { target_id: targetId });
      if (response?.error) {
        this._showMessage(`Docking error: ${response.error}`, "error");
      } else {
        this._showMessage(`Docking requested with ${targetId}`, "success");
      }
    } catch (error) {
      this._showMessage(`Docking request failed: ${error.message}`, "error");
    }
  }

  async _cancelDocking() {
    try {
      const response = await wsClient.sendShipCommand("cancel_docking", {});
      if (response?.error) {
        this._showMessage(`Cancel error: ${response.error}`, "error");
      } else {
        this._showMessage("Docking cancelled", "success");
      }
    } catch (error) {
      this._showMessage(`Cancel failed: ${error.message}`, "error");
    }
  }

  async _undock() {
    if (this._getCurrentDockingState() !== DOCKING_STATES.DOCKED) return;
    try {
      const response = await wsClient.sendShipCommand("undock", {});
      if (response?.error) {
        this._showMessage(`Undock error: ${response.error}`, "error");
      } else {
        this._showMessage("Undocked successfully", "success");
      }
    } catch (error) {
      this._showMessage(`Undock failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("docking-panel", DockingPanel);
export { DockingPanel };
