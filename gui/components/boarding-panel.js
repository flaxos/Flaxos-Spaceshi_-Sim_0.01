/**
 * Boarding Panel
 * Displays boarding state, progress bar, resistance info, and begin/cancel controls.
 * Attaches to the OPS view.  Subscribes to stateManager for boarding telemetry
 * and sends boarding commands via wsClient.sendShipCommand().
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const BOARDING_STATES = {
  IDLE: "idle",
  DOCKING: "docking",
  BOARDING: "boarding",
  CAPTURED: "captured",
  FAILED: "failed",
};

class BoardingPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._boardingState = null;
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
      this._unsubscribe = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", (value, key, fullState) => {
      this._boardingState = this._extractBoardingState(fullState);
      this._refreshContactList();
      this._updateDisplay();
    });
  }

  /**
   * Extract boarding system state from telemetry.
   * The server places it under systems.boarding or top-level boarding key.
   */
  _extractBoardingState(fullState) {
    const ship = stateManager.getShipState();
    if (!ship) return null;
    const boarding = ship.boarding;
    if (boarding && typeof boarding === "object") return boarding;
    const sysBoarding = ship.systems?.boarding;
    if (sysBoarding && typeof sysBoarding === "object") return sysBoarding;
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

        .status-indicator.idle { background: var(--text-dim, #555566); }
        .status-indicator.boarding {
          background: var(--status-warning, #ffaa00);
          animation: pulse-amber 1.5s ease-in-out infinite;
        }
        .status-indicator.captured {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 8px rgba(0, 255, 136, 0.4);
        }
        .status-indicator.failed {
          background: var(--status-critical, #ff4444);
        }
        .status-indicator.docking {
          background: var(--status-info, #00aaff);
          animation: pulse-blue 1.5s ease-in-out infinite;
        }

        @keyframes pulse-amber {
          0%, 100% { box-shadow: 0 0 4px rgba(255, 170, 0, 0.3); }
          50% { box-shadow: 0 0 14px rgba(255, 170, 0, 0.6); }
        }

        @keyframes pulse-blue {
          0%, 100% { box-shadow: 0 0 4px rgba(0, 170, 255, 0.3); }
          50% { box-shadow: 0 0 14px rgba(0, 170, 255, 0.6); }
        }

        .status-info { flex: 1; }

        .status-badge {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          font-weight: 700;
          letter-spacing: 1.5px;
          text-transform: uppercase;
        }

        .status-badge.idle { color: var(--text-dim, #555566); }
        .status-badge.boarding { color: var(--status-warning, #ffaa00); }
        .status-badge.captured { color: var(--status-nominal, #00ff88); }
        .status-badge.failed { color: var(--status-critical, #ff4444); }
        .status-badge.docking { color: var(--status-info, #00aaff); }

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

        .target-section { margin-bottom: 16px; }

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

        /* Progress bar */
        .progress-section {
          display: none;
          margin-bottom: 16px;
        }

        .progress-section.visible { display: block; }

        .progress-bar-track {
          width: 100%;
          height: 10px;
          background: var(--bg-input, #1a1a24);
          border-radius: 5px;
          border: 1px solid var(--border-default, #2a2a3a);
          overflow: hidden;
          margin-bottom: 6px;
        }

        .progress-bar-fill {
          height: 100%;
          border-radius: 5px;
          background: var(--status-warning, #ffaa00);
          transition: width 0.3s ease;
        }

        .progress-bar-fill.captured {
          background: var(--status-nominal, #00ff88);
        }

        .progress-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
          text-align: center;
        }

        /* Resistance info */
        .resistance-section {
          display: none;
          margin-bottom: 16px;
          padding: 10px;
          background: rgba(255, 170, 0, 0.05);
          border: 1px solid rgba(255, 170, 0, 0.15);
          border-radius: 6px;
        }

        .resistance-section.visible { display: block; }

        .resistance-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px 12px;
        }

        .resistance-item {
          display: flex;
          justify-content: space-between;
          font-size: 0.7rem;
        }

        .resistance-label {
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }

        .resistance-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        .resistance-value.high { color: var(--status-critical, #ff4444); }
        .resistance-value.low { color: var(--status-nominal, #00ff88); }

        /* Controls */
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

        .ctrl-btn:active:not(:disabled) { transform: scale(0.96); }

        .ctrl-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .ctrl-btn.begin {
          border-color: var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .ctrl-btn.begin:hover:not(:disabled) {
          background: rgba(255, 170, 0, 0.12);
        }

        .ctrl-btn.cancel {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .ctrl-btn.cancel:hover:not(:disabled) {
          background: rgba(255, 68, 68, 0.15);
        }

        /* Captured banner */
        .captured-banner {
          display: none;
          margin-bottom: 16px;
          padding: 14px;
          background: rgba(0, 255, 136, 0.06);
          border: 1px solid rgba(0, 255, 136, 0.2);
          border-radius: 6px;
          text-align: center;
        }

        .captured-banner.visible { display: block; }

        .captured-text {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1rem;
          font-weight: 700;
          color: var(--status-nominal, #00ff88);
          letter-spacing: 0.5px;
        }

        .captured-subtext {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
          margin-top: 4px;
        }

        /* Failed banner */
        .failed-banner {
          display: none;
          margin-bottom: 16px;
          padding: 14px;
          background: rgba(255, 68, 68, 0.06);
          border: 1px solid rgba(255, 68, 68, 0.2);
          border-radius: 6px;
          text-align: center;
        }

        .failed-banner.visible { display: block; }

        .failed-text {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          font-weight: 700;
          color: var(--status-critical, #ff4444);
        }

        .hidden { display: none !important; }
      </style>

      <!-- Status Display -->
      <div class="status-display">
        <div class="status-indicator idle" id="status-indicator"></div>
        <div class="status-info">
          <div class="status-badge idle" id="status-badge">IDLE</div>
          <div class="status-text" id="status-text">No boarding action in progress</div>
        </div>
      </div>

      <!-- Target Selection -->
      <div class="target-section" id="target-section">
        <div class="section-title">Board Target</div>
        <select class="target-select" id="target-select">
          <option value="">-- Select Target --</option>
        </select>
      </div>

      <!-- Progress Bar -->
      <div class="progress-section" id="progress-section">
        <div class="section-title">Boarding Progress</div>
        <div class="progress-bar-track">
          <div class="progress-bar-fill" id="progress-fill" style="width: 0%"></div>
        </div>
        <div class="progress-label" id="progress-label">0%</div>
      </div>

      <!-- Resistance Info -->
      <div class="resistance-section" id="resistance-section">
        <div class="section-title">Defender Resistance</div>
        <div class="resistance-grid" id="resistance-grid"></div>
      </div>

      <!-- Captured Banner -->
      <div class="captured-banner" id="captured-banner">
        <div class="captured-text" id="captured-text">TARGET CAPTURED</div>
        <div class="captured-subtext">Faction ownership transferred</div>
      </div>

      <!-- Failed Banner -->
      <div class="failed-banner" id="failed-banner">
        <div class="failed-text" id="failed-text">BOARDING FAILED</div>
      </div>

      <!-- Controls -->
      <div class="controls" id="controls">
        <button class="ctrl-btn begin" id="btn-begin"
                title="Begin boarding the selected target (must be docked, target mission-killed)">
          Begin Boarding
        </button>
        <button class="ctrl-btn cancel" id="btn-cancel"
                title="Abort the current boarding action" disabled>
          Cancel Boarding
        </button>
      </div>
    `;
  }

  _setupInteraction() {
    this.shadowRoot.getElementById("btn-begin").addEventListener("click", () => {
      this._beginBoarding();
    });
    this.shadowRoot.getElementById("btn-cancel").addEventListener("click", () => {
      this._cancelBoarding();
    });
    this.shadowRoot.getElementById("target-select").addEventListener("change", (e) => {
      this._selectedTargetId = e.target.value || null;
    });
  }

  _refreshContactList() {
    const select = this.shadowRoot.getElementById("target-select");
    const contacts = stateManager.getContacts();
    const previousValue = select.value;

    select.innerHTML = '<option value="">-- Select Target --</option>';
    if (Array.isArray(contacts)) {
      contacts.forEach((contact) => {
        const id = contact.contact_id || contact.id;
        const option = document.createElement("option");
        option.value = id;
        option.textContent = `${id} -- ${contact.name || contact.classification || "UNKNOWN"}`;
        select.appendChild(option);
      });
    }

    if (previousValue && select.querySelector(`option[value="${previousValue}"]`)) {
      select.value = previousValue;
      this._selectedTargetId = previousValue;
    } else {
      this._selectedTargetId = select.value || null;
    }

    // Disable selection when boarding is active
    const state = this._getCurrentState();
    select.disabled = state === BOARDING_STATES.BOARDING || state === BOARDING_STATES.CAPTURED;
  }

  _getCurrentState() {
    const bs = this._boardingState;
    if (!bs) return BOARDING_STATES.IDLE;
    const raw = (bs.state || bs.status || "idle").toLowerCase();
    if (raw === "boarding") return BOARDING_STATES.BOARDING;
    if (raw === "captured") return BOARDING_STATES.CAPTURED;
    if (raw === "failed") return BOARDING_STATES.FAILED;
    if (raw === "docking") return BOARDING_STATES.DOCKING;
    return BOARDING_STATES.IDLE;
  }

  _updateDisplay() {
    const state = this._getCurrentState();
    const bs = this._boardingState;
    const isBoarding = state === BOARDING_STATES.BOARDING;
    const isCaptured = state === BOARDING_STATES.CAPTURED;
    const isFailed = state === BOARDING_STATES.FAILED;

    const indicator = this.shadowRoot.getElementById("status-indicator");
    const badge = this.shadowRoot.getElementById("status-badge");
    const statusText = this.shadowRoot.getElementById("status-text");
    const targetSection = this.shadowRoot.getElementById("target-section");
    const progressSection = this.shadowRoot.getElementById("progress-section");
    const progressFill = this.shadowRoot.getElementById("progress-fill");
    const progressLabel = this.shadowRoot.getElementById("progress-label");
    const resistanceSection = this.shadowRoot.getElementById("resistance-section");
    const capturedBanner = this.shadowRoot.getElementById("captured-banner");
    const capturedText = this.shadowRoot.getElementById("captured-text");
    const failedBanner = this.shadowRoot.getElementById("failed-banner");
    const failedText = this.shadowRoot.getElementById("failed-text");
    const btnBegin = this.shadowRoot.getElementById("btn-begin");
    const btnCancel = this.shadowRoot.getElementById("btn-cancel");

    // Status indicator and badge
    indicator.className = `status-indicator ${state}`;
    badge.className = `status-badge ${state}`;
    badge.textContent = state.toUpperCase();

    // Visibility toggles
    targetSection.classList.toggle("hidden", isBoarding || isCaptured);
    progressSection.classList.toggle("visible", isBoarding || isCaptured);
    resistanceSection.classList.toggle("visible", isBoarding);
    capturedBanner.classList.toggle("visible", isCaptured);
    failedBanner.classList.toggle("visible", isFailed);

    // Progress bar
    const progress = bs?.progress || 0;
    const pct = Math.round(progress * 100);
    progressFill.style.width = `${pct}%`;
    progressFill.classList.toggle("captured", isCaptured);
    progressLabel.textContent = `${pct}%`;

    // State-specific text and buttons
    switch (state) {
      case BOARDING_STATES.IDLE:
        statusText.textContent = "No boarding action in progress";
        btnBegin.disabled = false;
        btnCancel.disabled = true;
        break;

      case BOARDING_STATES.BOARDING:
        statusText.textContent = `Boarding ${bs?.target || "target"} -- ${pct}%`;
        btnBegin.disabled = true;
        btnCancel.disabled = false;
        this._updateResistance(bs?.resistance);
        break;

      case BOARDING_STATES.CAPTURED:
        statusText.textContent = "Target captured";
        capturedText.textContent = `${bs?.target || "TARGET"} CAPTURED`;
        btnBegin.disabled = true;
        btnCancel.disabled = true;
        break;

      case BOARDING_STATES.FAILED:
        statusText.textContent = bs?.failure_reason || "Boarding failed";
        failedText.textContent = `BOARDING FAILED: ${bs?.failure_reason || "unknown"}`;
        btnBegin.disabled = false;
        btnCancel.disabled = true;
        break;

      default:
        statusText.textContent = "Standby";
        btnBegin.disabled = false;
        btnCancel.disabled = true;
    }
  }

  _updateResistance(resistance) {
    const grid = this.shadowRoot.getElementById("resistance-grid");
    if (!grid || !resistance) {
      if (grid) grid.innerHTML = "";
      return;
    }

    const items = [
      { label: "DC Skill", value: resistance.damage_control_skill, suffix: "" },
      { label: "DC Penalty", value: resistance.damage_control_penalty, suffix: "", fmt: "pct" },
      { label: "Active Wpns", value: resistance.active_weapons, suffix: "" },
      { label: "Wpn Penalty", value: resistance.weapon_penalty, suffix: "", fmt: "pct" },
      { label: "Reactor Pen.", value: resistance.reactor_penalty, suffix: "", fmt: "pct" },
      { label: "Total Factor", value: resistance.total_factor, suffix: "", fmt: "pct" },
    ];

    grid.innerHTML = items
      .map((item) => {
        const val = item.value ?? "--";
        let display;
        if (item.fmt === "pct" && typeof val === "number") {
          display = `${Math.round(val * 100)}%`;
        } else {
          display = `${val}${item.suffix}`;
        }
        // Highlight high resistance factors in red, low in green
        let cls = "";
        if (item.label === "Total Factor" && typeof val === "number") {
          cls = val < 0.5 ? "high" : "low";
        }
        return `<div class="resistance-item">
          <span class="resistance-label">${item.label}</span>
          <span class="resistance-value ${cls}">${display}</span>
        </div>`;
      })
      .join("");
  }

  async _beginBoarding() {
    const targetId = this._selectedTargetId;
    if (!targetId) {
      this._showMessage("Select a target before beginning boarding", "error");
      return;
    }

    try {
      const response = await wsClient.sendShipCommand("begin_boarding", {
        target_ship_id: targetId,
      });
      if (response?.error || response?.ok === false) {
        this._showMessage(
          `Boarding error: ${response.message || response.error}`,
          "error"
        );
      } else {
        this._showMessage(`Boarding ${targetId} initiated`, "success");
      }
    } catch (error) {
      this._showMessage(`Boarding request failed: ${error.message}`, "error");
    }
  }

  async _cancelBoarding() {
    try {
      const response = await wsClient.sendShipCommand("cancel_boarding", {});
      if (response?.error || response?.ok === false) {
        this._showMessage(
          `Cancel error: ${response.message || response.error}`,
          "error"
        );
      } else {
        this._showMessage("Boarding cancelled", "success");
      }
    } catch (error) {
      this._showMessage(`Cancel failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("boarding-panel", BoardingPanel);
export { BoardingPanel };
