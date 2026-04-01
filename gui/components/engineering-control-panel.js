/**
 * Engineering Control Panel
 * Provides interactive controls for the Engineering station:
 * - Reactor output adjustment
 * - Drive throttle limit
 * - Radiator management (deploy/retract, priority mode)
 * - Fuel monitor (level, burn rate, delta-v, time to empty)
 * - Emergency coolant vent (confirmation required)
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

class EngineeringControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._ventConfirmPending = false;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
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

  async _sendCommand(cmd, args = {}) {
    return wsClient.sendShipCommand(cmd, args);
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 12px;
        }

        .section {
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--status-info, #00aaff);
          margin-bottom: 8px;
          padding-bottom: 4px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .status-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 0;
          font-size: 0.75rem;
        }

        .status-label {
          color: var(--text-secondary, #888899);
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
        }

        .status-value.nominal {
          color: var(--status-nominal, #00ff88);
        }

        .status-value.warning {
          color: var(--status-warning, #ffaa00);
        }

        .status-value.critical {
          color: var(--status-critical, #ff4444);
        }

        .status-value.info {
          color: var(--status-info, #00aaff);
        }

        /* Large readout for headline values */
        .readout-large {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.4rem;
          font-weight: 700;
          line-height: 1;
        }

        .readout-unit {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
          margin-left: 2px;
        }

        /* Slider controls */
        .slider-control {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 8px;
        }

        .slider-control input[type="range"] {
          flex: 1;
          -webkit-appearance: none;
          appearance: none;
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          outline: none;
        }

        .slider-control input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: var(--status-info, #00aaff);
          cursor: pointer;
          border: 2px solid var(--bg-panel, #12121a);
          box-shadow: 0 0 4px rgba(0, 170, 255, 0.4);
        }

        .slider-control input[type="range"]::-moz-range-thumb {
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: var(--status-info, #00aaff);
          cursor: pointer;
          border: 2px solid var(--bg-panel, #12121a);
          box-shadow: 0 0 4px rgba(0, 170, 255, 0.4);
        }

        .slider-control input[type="range"]::-webkit-slider-runnable-track {
          height: 6px;
          border-radius: 3px;
        }

        .slider-control input[type="range"]::-moz-range-track {
          height: 6px;
          border-radius: 3px;
          background: var(--bg-input, #1a1a24);
        }

        .slider-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          min-width: 36px;
          text-align: right;
        }

        /* Indicator bar for reactor/drive */
        .indicator-bar {
          height: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
          margin-top: 6px;
        }

        .indicator-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s ease, background 0.3s ease;
        }

        .indicator-fill.nominal {
          background: var(--status-nominal, #00ff88);
        }

        .indicator-fill.warning {
          background: var(--status-warning, #ffaa00);
        }

        .indicator-fill.critical {
          background: var(--status-critical, #ff4444);
        }

        /* Dual-bar overlay for throttle vs limit */
        .dual-bar {
          position: relative;
          height: 10px;
          background: var(--bg-input, #1a1a24);
          border-radius: 5px;
          overflow: hidden;
          margin-top: 6px;
        }

        .dual-bar-fill {
          position: absolute;
          top: 0;
          left: 0;
          height: 100%;
          border-radius: 5px;
          transition: width 0.3s ease;
        }

        .dual-bar-fill.limit {
          background: rgba(0, 170, 255, 0.2);
          border-right: 2px solid var(--status-info, #00aaff);
        }

        .dual-bar-fill.actual {
          background: var(--status-nominal, #00ff88);
          opacity: 0.8;
        }

        .dual-bar-legend {
          display: flex;
          gap: 12px;
          margin-top: 4px;
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
        }

        .legend-swatch {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 2px;
          margin-right: 3px;
          vertical-align: middle;
        }

        .legend-swatch.actual {
          background: var(--status-nominal, #00ff88);
        }

        .legend-swatch.limit {
          background: var(--status-info, #00aaff);
        }

        /* Button styles */
        .eng-btn {
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid rgba(0, 170, 255, 0.3);
          border-radius: 4px;
          color: var(--status-info, #00aaff);
          padding: 8px 10px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          cursor: pointer;
          text-transform: uppercase;
          transition: all 0.15s ease;
          text-align: center;
          min-height: 36px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 2px;
        }

        .eng-btn:hover {
          background: rgba(0, 170, 255, 0.2);
          border-color: var(--status-info, #00aaff);
        }

        .eng-btn.active {
          background: rgba(0, 255, 136, 0.15);
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .eng-btn.disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        /* Radiator controls layout */
        .radiator-controls {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
          margin-top: 8px;
        }

        .radiator-controls .eng-btn.full-width {
          grid-column: 1 / -1;
        }

        /* Priority mode selector */
        .priority-selector {
          display: flex;
          gap: 4px;
          margin-top: 8px;
        }

        .priority-btn {
          flex: 1;
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-dim, #555566);
          padding: 6px 8px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          cursor: pointer;
          text-transform: uppercase;
          transition: all 0.15s ease;
          text-align: center;
        }

        .priority-btn:hover {
          border-color: var(--status-info, #00aaff);
          color: var(--text-secondary, #888899);
        }

        .priority-btn.selected {
          background: rgba(0, 170, 255, 0.15);
          border-color: var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        /* Fuel progress bar */
        .fuel-bar-container {
          margin-top: 6px;
        }

        .fuel-bar-labels {
          display: flex;
          justify-content: space-between;
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          margin-bottom: 2px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .fuel-bar {
          height: 10px;
          background: var(--bg-input, #1a1a24);
          border-radius: 5px;
          overflow: hidden;
        }

        .fuel-bar-fill {
          height: 100%;
          border-radius: 5px;
          transition: width 0.4s ease, background 0.4s ease;
        }

        .fuel-bar-fill.nominal {
          background: var(--status-nominal, #00ff88);
        }

        .fuel-bar-fill.warning {
          background: var(--status-warning, #ffaa00);
        }

        .fuel-bar-fill.critical {
          background: var(--status-critical, #ff4444);
        }

        /* Emergency vent button */
        .vent-btn {
          background: rgba(255, 68, 68, 0.15);
          border: 1px solid rgba(255, 68, 68, 0.4);
          border-radius: 4px;
          color: var(--status-critical, #ff4444);
          padding: 12px 16px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          font-weight: 700;
          cursor: pointer;
          text-transform: uppercase;
          letter-spacing: 1px;
          transition: all 0.15s ease;
          width: 100%;
          min-height: 48px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }

        .vent-btn:hover {
          background: rgba(255, 68, 68, 0.3);
          border-color: var(--status-critical, #ff4444);
          box-shadow: 0 0 12px rgba(255, 68, 68, 0.2);
        }

        .vent-btn.active {
          background: rgba(255, 68, 68, 0.4);
          border-color: var(--status-critical, #ff4444);
          animation: vent-pulse 0.8s ease-in-out infinite;
        }

        .vent-btn.disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }

        .vent-btn.disabled:hover {
          background: rgba(255, 68, 68, 0.15);
          border-color: rgba(255, 68, 68, 0.4);
          box-shadow: none;
        }

        @keyframes vent-pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 12px rgba(255, 68, 68, 0.3); }
          50% { opacity: 0.7; box-shadow: 0 0 20px rgba(255, 68, 68, 0.5); }
        }

        /* Confirm dialog overlay */
        .confirm-overlay {
          position: relative;
          margin-top: 8px;
          padding: 12px;
          background: rgba(255, 68, 68, 0.08);
          border: 1px solid rgba(255, 68, 68, 0.3);
          border-radius: 6px;
        }

        .confirm-text {
          font-size: 0.7rem;
          color: var(--status-warning, #ffaa00);
          margin-bottom: 8px;
          text-align: center;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .confirm-actions {
          display: flex;
          gap: 8px;
        }

        .confirm-yes {
          flex: 1;
          background: rgba(255, 68, 68, 0.2);
          border: 1px solid var(--status-critical, #ff4444);
          border-radius: 4px;
          color: var(--status-critical, #ff4444);
          padding: 8px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 700;
          cursor: pointer;
          text-transform: uppercase;
          transition: all 0.15s ease;
        }

        .confirm-yes:hover {
          background: rgba(255, 68, 68, 0.35);
        }

        .confirm-no {
          flex: 1;
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          padding: 8px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          cursor: pointer;
          text-transform: uppercase;
          transition: all 0.15s ease;
        }

        .confirm-no:hover {
          border-color: var(--text-secondary, #888899);
        }

        /* Vent active status */
        .vent-active-info {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 10px;
          margin-top: 8px;
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid rgba(255, 68, 68, 0.3);
          border-radius: 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          color: var(--status-critical, #ff4444);
        }

        .vent-remaining-bar {
          height: 4px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 2px;
          overflow: hidden;
          margin-top: 6px;
        }

        .vent-remaining-fill {
          height: 100%;
          background: var(--status-critical, #ff4444);
          border-radius: 2px;
          transition: width 0.3s ease;
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 16px;
          font-style: italic;
        }

        @media (max-width: 768px) {
          .readout-large {
            font-size: 1.1rem;
          }
          .radiator-controls {
            grid-template-columns: 1fr;
          }
        }
      </style>

      <div id="eng-content">
        <div class="empty-state">Engineering systems not available</div>
      </div>
    `;
  }

  _updateDisplay() {
    const state = stateManager.getState();
    const ship = stateManager.getShipState();
    const container = this.shadowRoot.getElementById("eng-content");

    if (!ship || !container) {
      if (container) {
        container.innerHTML = '<div class="empty-state">Engineering systems not available</div>';
      }
      return;
    }

    const eng = ship.engineering || {};
    const propulsion = ship.systems?.propulsion || {};
    const thermal = ship.thermal || {};

    // Reactor output (use percent field, or convert fraction to percent)
    const reactorOutput = eng.reactor_percent ?? ((eng.reactor_output ?? 1.0) * 100);
    const reactorClass = reactorOutput > 95 ? "critical" : reactorOutput > 80 ? "warning" : "nominal";

    // Drive limit (use percent field, or convert fraction to percent)
    const driveLimit = eng.drive_limit_percent ?? ((eng.drive_limit ?? 1.0) * 100);
    const actualThrottle = propulsion.throttle ?? 0;
    const actualThrottlePct = (actualThrottle * 100).toFixed(0);

    // Radiators
    const radDeployed = eng.radiators_deployed ?? true;
    const radPriority = eng.radiator_priority || "balanced";

    // Fuel
    const fuelLevel = propulsion.fuel_level ?? propulsion.fuel ?? 0;
    const maxFuel = propulsion.max_fuel ?? 100;
    const fuelPercent = propulsion.fuel_percent ?? (maxFuel > 0 ? (fuelLevel / maxFuel) * 100 : 0);
    const burnRate = eng.fuel_burn_rate ?? propulsion.fuel_consumption ?? 0;
    const deltaV = ship.delta_v_remaining ?? propulsion.delta_v ?? 0;
    const timeToEmpty = burnRate > 0 ? (fuelLevel / burnRate) : Infinity;
    const fuelClass = fuelPercent > 50 ? "nominal" : fuelPercent > 20 ? "warning" : "critical";

    // Emergency vent
    const ventAvailable = eng.emergency_vent_available ?? false;
    const ventActive = eng.emergency_vent_active ?? false;
    const ventRemaining = eng.emergency_vent_remaining ?? 0;
    const ventRate = eng.vent_rate ?? 0;

    let html = "";

    // --- Reactor Output Section ---
    html += '<div class="section">';
    html += '<div class="section-title">Reactor Output</div>';
    html += `
      <div class="status-row">
        <span class="readout-large ${reactorClass}">${reactorOutput.toFixed(0)}</span>
        <span class="readout-unit">%</span>
      </div>
      <div class="indicator-bar">
        <div class="indicator-fill ${reactorClass}" style="width: ${Math.min(reactorOutput, 100)}%"></div>
      </div>
      <div class="slider-control">
        <input type="range" id="reactor-slider" min="0" max="100" step="5" value="${reactorOutput}">
        <span class="slider-value" id="reactor-slider-value">${reactorOutput.toFixed(0)}%</span>
      </div>
    `;
    html += "</div>";

    // --- Drive Limit Section ---
    html += '<div class="section">';
    html += '<div class="section-title">Drive Throttle Limit</div>';
    html += `
      <div class="status-row">
        <span class="status-label">Limit</span>
        <span class="status-value info">${driveLimit.toFixed(0)}%</span>
      </div>
      <div class="status-row">
        <span class="status-label">Actual Throttle</span>
        <span class="status-value ${actualThrottle > 0.8 ? 'warning' : 'nominal'}">${actualThrottlePct}%</span>
      </div>
      <div class="dual-bar">
        <div class="dual-bar-fill limit" style="width: ${Math.min(driveLimit, 100)}%"></div>
        <div class="dual-bar-fill actual" style="width: ${Math.min(actualThrottle * 100, 100)}%"></div>
      </div>
      <div class="dual-bar-legend">
        <span><span class="legend-swatch actual"></span>Actual</span>
        <span><span class="legend-swatch limit"></span>Limit</span>
      </div>
      <div class="slider-control">
        <input type="range" id="drive-slider" min="0" max="100" step="5" value="${driveLimit}">
        <span class="slider-value" id="drive-slider-value">${driveLimit.toFixed(0)}%</span>
      </div>
    `;
    html += "</div>";

    // --- Radiator Management Section ---
    html += '<div class="section">';
    html += '<div class="section-title">Radiator Management</div>';
    html += `
      <div class="status-row">
        <span class="status-label">Radiators</span>
        <span class="status-value ${radDeployed ? 'nominal' : 'warning'}">${radDeployed ? "DEPLOYED" : "RETRACTED"}</span>
      </div>
      <div class="status-row">
        <span class="status-label">Priority</span>
        <span class="status-value info">${radPriority.toUpperCase()}</span>
      </div>
      <div class="radiator-controls">
        <button class="eng-btn ${radDeployed ? 'active' : ''}" id="btn-rad-toggle">
          ${radDeployed ? "RETRACT" : "DEPLOY"}
          <span style="font-size: 0.6rem; opacity: 0.7">${radDeployed ? "stow panels" : "extend panels"}</span>
        </button>
      </div>
      <div class="priority-selector">
        <button class="priority-btn ${radPriority === 'balanced' ? 'selected' : ''}"
                data-priority="balanced">Balanced</button>
        <button class="priority-btn ${radPriority === 'cooling' ? 'selected' : ''}"
                data-priority="cooling">Cooling</button>
        <button class="priority-btn ${radPriority === 'stealth' ? 'selected' : ''}"
                data-priority="stealth">Stealth</button>
      </div>
    `;
    html += "</div>";

    // --- Fuel Monitor Section ---
    html += '<div class="section">';
    html += '<div class="section-title">Fuel Monitor</div>';
    html += `
      <div class="status-row">
        <span class="status-label">Fuel Level</span>
        <span class="status-value ${fuelClass}">${fuelLevel.toFixed(1)} / ${maxFuel.toFixed(1)} kg</span>
      </div>
      <div class="fuel-bar-container">
        <div class="fuel-bar-labels">
          <span>0%</span>
          <span>${fuelPercent.toFixed(1)}%</span>
          <span>100%</span>
        </div>
        <div class="fuel-bar">
          <div class="fuel-bar-fill ${fuelClass}" style="width: ${Math.min(fuelPercent, 100)}%"></div>
        </div>
      </div>
      <div class="status-row">
        <span class="status-label">Burn Rate</span>
        <span class="status-value">${burnRate > 0 ? burnRate.toFixed(2) + " kg/s" : "IDLE"}</span>
      </div>
      <div class="status-row">
        <span class="status-label">Delta-V Remaining</span>
        <span class="status-value ${deltaV < 100 ? 'warning' : ''}">${this._formatDeltaV(deltaV)}</span>
      </div>
      <div class="status-row">
        <span class="status-label">Est. Time to Empty</span>
        <span class="status-value ${timeToEmpty < 60 ? 'critical' : timeToEmpty < 300 ? 'warning' : ''}">${this._formatTime(timeToEmpty)}</span>
      </div>
    `;
    html += "</div>";

    // --- Emergency Vent Section ---
    html += '<div class="section">';
    html += '<div class="section-title">Emergency Coolant Vent</div>';

    if (ventActive) {
      html += `
        <button class="vent-btn active" id="btn-vent" disabled>
          VENTING COOLANT
        </button>
        <div class="vent-active-info">
          <span>Remaining</span>
          <span>${ventRemaining.toFixed(1)}s</span>
        </div>
        <div class="vent-remaining-bar">
          <div class="vent-remaining-fill" style="width: ${ventRemaining > 0 ? Math.min((ventRemaining / 30) * 100, 100) : 0}%"></div>
        </div>
        <div class="status-row">
          <span class="status-label">Vent Rate</span>
          <span class="status-value critical">${this._formatWatts(ventRate)}</span>
        </div>
      `;
    } else if (this._ventConfirmPending) {
      html += `
        <button class="vent-btn" id="btn-vent" disabled>
          EMERGENCY VENT
        </button>
        <div class="confirm-overlay">
          <div class="confirm-text">Confirm emergency coolant vent?</div>
          <div class="confirm-actions">
            <button class="confirm-yes" id="btn-vent-confirm">Confirm Vent</button>
            <button class="confirm-no" id="btn-vent-cancel">Cancel</button>
          </div>
        </div>
      `;
    } else {
      const ventDisabled = !ventAvailable;
      html += `
        <button class="vent-btn ${ventDisabled ? 'disabled' : ''}" id="btn-vent">
          EMERGENCY VENT
        </button>
        <div class="status-row">
          <span class="status-label">Status</span>
          <span class="status-value ${ventAvailable ? 'nominal' : 'critical'}">${ventAvailable ? "AVAILABLE" : "DEPLETED"}</span>
        </div>
      `;
    }

    html += "</div>";

    container.innerHTML = html;

    // Attach event listeners after DOM update
    this._attachListeners(eng, propulsion, radDeployed, radPriority, ventAvailable, ventActive);
  }

  _attachListeners(eng, propulsion, radDeployed, radPriority, ventAvailable, ventActive) {
    // Reactor slider
    const reactorSlider = this.shadowRoot.getElementById("reactor-slider");
    const reactorValue = this.shadowRoot.getElementById("reactor-slider-value");
    if (reactorSlider) {
      reactorSlider.addEventListener("input", (e) => {
        if (reactorValue) {
          reactorValue.textContent = e.target.value + "%";
        }
      });
      reactorSlider.addEventListener("change", (e) => {
        this._sendCommand("set_reactor_output", { output: parseInt(e.target.value, 10) });
      });
    }

    // Drive limit slider
    const driveSlider = this.shadowRoot.getElementById("drive-slider");
    const driveValue = this.shadowRoot.getElementById("drive-slider-value");
    if (driveSlider) {
      driveSlider.addEventListener("input", (e) => {
        if (driveValue) {
          driveValue.textContent = e.target.value + "%";
        }
      });
      driveSlider.addEventListener("change", (e) => {
        this._sendCommand("throttle_drive", { limit: parseInt(e.target.value, 10) });
      });
    }

    // Radiator deploy/retract toggle
    const btnRadToggle = this.shadowRoot.getElementById("btn-rad-toggle");
    if (btnRadToggle) {
      btnRadToggle.addEventListener("click", () => {
        this._sendCommand("manage_radiators", {
          deployed: !radDeployed,
          priority: radPriority,
        });
      });
    }

    // Radiator priority buttons
    this.shadowRoot.querySelectorAll("[data-priority]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const priority = e.currentTarget.dataset.priority;
        this._sendCommand("manage_radiators", {
          deployed: radDeployed,
          priority: priority,
        });
      });
    });

    // Emergency vent button
    const btnVent = this.shadowRoot.getElementById("btn-vent");
    if (btnVent && !ventActive) {
      btnVent.addEventListener("click", () => {
        if (!ventAvailable) return;
        this._ventConfirmPending = true;
        this._updateDisplay();
      });
    }

    // Vent confirm/cancel buttons
    const btnConfirm = this.shadowRoot.getElementById("btn-vent-confirm");
    const btnCancel = this.shadowRoot.getElementById("btn-vent-cancel");

    if (btnConfirm) {
      btnConfirm.addEventListener("click", () => {
        this._ventConfirmPending = false;
        this._sendCommand("emergency_vent", { confirm: true });
      });
    }

    if (btnCancel) {
      btnCancel.addEventListener("click", () => {
        this._ventConfirmPending = false;
        this._updateDisplay();
      });
    }

    this._updateAutoEngPanel();
  }

  /**
   * Format delta-v values with appropriate units.
   */
  _formatDeltaV(dv) {
    if (dv >= 1000) return (dv / 1000).toFixed(2) + " km/s";
    return dv.toFixed(1) + " m/s";
  }

  /**
   * Format time in seconds to human-readable duration.
   */
  _formatTime(seconds) {
    if (!isFinite(seconds) || seconds <= 0) return "--:--";
    if (seconds >= 3600) {
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      return `${h}h ${m.toString().padStart(2, "0")}m`;
    }
    if (seconds >= 60) {
      const m = Math.floor(seconds / 60);
      const s = Math.floor(seconds % 60);
      return `${m}m ${s.toString().padStart(2, "0")}s`;
    }
    return seconds.toFixed(0) + "s";
  }

  /**
   * Format watts with kW / MW suffixes.
   */
  _formatWatts(w) {
    const abs = Math.abs(w);
    const sign = w < 0 ? "-" : "";
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)} MW`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)} kW`;
    return `${sign}${abs.toFixed(0)} W`;
  }

  // --- Auto-Engineering (CPU-ASSIST tier) ---
  _updateAutoEngPanel() {
    let panel = this.shadowRoot.getElementById("auto-eng-panel");
    const tier = window.controlTier || "raw";
    if (tier !== "cpu-assist") {
      if (panel) panel.style.display = "none";
      return;
    }
    if (!panel) {
      // Create the panel on first cpu-assist render
      panel = document.createElement("div");
      panel.id = "auto-eng-panel";
      panel.style.cssText = "border:1px solid rgba(192,160,255,0.3);border-radius:4px;padding:8px;margin:8px 0;background:rgba(192,160,255,0.05);";
      panel.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <span style="color:#c0a0ff;font-size:0.7rem;font-weight:600;letter-spacing:0.5px;">AUTO ENGINEERING</span>
          <button id="auto-eng-toggle" style="background:rgba(192,160,255,0.15);color:#c0a0ff;border:1px solid rgba(192,160,255,0.3);padding:2px 10px;border-radius:3px;cursor:pointer;font-size:0.65rem;">ENABLE</button>
        </div>
        <div id="eng-proposals"></div>`;
      const content = this.shadowRoot.getElementById("eng-content");
      if (content) content.prepend(panel);
      panel.querySelector("#auto-eng-toggle").addEventListener("click", () => {
        const ship = stateManager.getShipState();
        const cmd = ship?.auto_engineering?.enabled ? "disable_auto_engineering" : "enable_auto_engineering";
        wsClient.sendShipCommand(cmd, {});
      });
      panel.querySelector("#eng-proposals").addEventListener("click", (e) => {
        const a = e.target.closest("[data-approve]");
        const d = e.target.closest("[data-deny]");
        if (a) wsClient.sendShipCommand("approve_engineering", { proposal_id: a.dataset.approve });
        if (d) wsClient.sendShipCommand("deny_engineering", { proposal_id: d.dataset.deny });
      });
    }
    panel.style.display = "block";
    const ship = stateManager.getShipState();
    const st = ship?.auto_engineering || {};
    const toggle = panel.querySelector("#auto-eng-toggle");
    toggle.textContent = st.enabled ? "DISABLE" : "ENABLE";
    toggle.style.background = st.enabled ? "rgba(0,255,136,0.15)" : "rgba(192,160,255,0.15)";
    const proposals = st.proposals || [];
    const pc = panel.querySelector("#eng-proposals");
    if (proposals.length === 0) {
      pc.innerHTML = '<div style="color:var(--text-dim);font-size:0.65rem;">No pending proposals</div>';
    } else {
      pc.innerHTML = proposals.map(p => `<div style="background:var(--bg-input);border:1px solid var(--border-default);border-radius:4px;padding:5px 8px;margin:3px 0;font-size:0.65rem;">
        <div style="color:var(--text-primary);margin-bottom:3px;">${p.description || p.action}</div>
        <button data-approve="${p.id}" style="background:rgba(0,255,136,0.15);color:#00ff88;border:1px solid rgba(0,255,136,0.3);padding:1px 8px;border-radius:3px;cursor:pointer;font-size:0.6rem;margin-right:3px;">APPROVE</button>
        <button data-deny="${p.id}" style="background:rgba(255,68,68,0.15);color:#ff4444;border:1px solid rgba(255,68,68,0.3);padding:1px 8px;border-radius:3px;cursor:pointer;font-size:0.6rem;">DENY</button>
      </div>`).join('');
    }
  }
}

customElements.define("engineering-control-panel", EngineeringControlPanel);
export { EngineeringControlPanel };
