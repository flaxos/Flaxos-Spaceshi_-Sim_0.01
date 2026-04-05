/**
 * Engineering Control Panel
 * Provides interactive controls for the Engineering station:
 * - Reactor output adjustment
 * - Drive throttle limit
 * - Radiator management (deploy/retract, priority mode)
 * - Fuel monitor (level, burn rate, delta-v, time to empty)
 * - Emergency coolant vent (confirmation required)
 *
 * Tier-aware rendering:
 * - MANUAL: Raw kW/Kelvin/kg values, manual radiator toggle, drive throttle fraction
 * - RAW:    Full engineering dashboard with all details and repair queue
 * - ARCADE: Simplified %, "hours of burn", one-click emergency vent, repair dropdown
 * - CPU-ASSIST: Auto-engineering proposals (approve/deny), minimal manual controls
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";
import { getProposalCSS } from "../js/proposal-styles.js";

class EngineeringControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tierHandler = null;
    this._ventConfirmPending = false;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    // Listen for tier changes — same pattern as flight-computer-panel
    this._tierHandler = () => this._updateDisplay();
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
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

        /* --- Auto-Engineering panel (CPU-ASSIST) --- */
        .auto-eng-panel {
          border: 1px solid rgba(192, 160, 255, 0.3);
          border-radius: 4px;
          padding: 8px;
          margin: 0 0 16px 0;
          background: rgba(192, 160, 255, 0.05);
        }

        .auto-eng-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 6px;
        }

        .auto-eng-title {
          color: #c0a0ff;
          font-size: 0.7rem;
          font-weight: 600;
          letter-spacing: 0.5px;
        }

        .auto-eng-toggle {
          background: rgba(192, 160, 255, 0.15);
          color: #c0a0ff;
          border: 1px solid rgba(192, 160, 255, 0.3);
          padding: 2px 10px;
          border-radius: 3px;
          cursor: pointer;
          font-size: 0.65rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          transition: all 0.15s ease;
        }

        .auto-eng-toggle:hover {
          background: rgba(192, 160, 255, 0.25);
        }

        .auto-eng-toggle.enabled {
          background: rgba(0, 255, 136, 0.15);
          color: #00ff88;
          border-color: rgba(0, 255, 136, 0.3);
        }

        .auto-eng-empty {
          color: var(--text-dim, #555566);
          font-size: 0.65rem;
        }

        /* Proposal cards — shared styles from proposal-styles.js */
        ${getProposalCSS()}

        /* --- Repair queue (RAW/ARCADE) --- */
        .repair-queue {
          margin-top: 8px;
        }

        .repair-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          margin-bottom: 3px;
          font-size: 0.7rem;
        }

        .repair-item-name {
          color: var(--text-primary, #e0e0e0);
        }

        .repair-item-time {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--status-warning, #ffaa00);
          font-size: 0.65rem;
        }

        .repair-empty {
          color: var(--text-dim, #555566);
          font-size: 0.65rem;
          font-style: italic;
          padding: 4px 0;
        }

        /* Repair priority dropdown (arcade) */
        .repair-dropdown {
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          padding: 4px 8px;
          cursor: pointer;
          width: 100%;
          margin-top: 6px;
        }

        /* CPU-ASSIST summary card */
        .cpu-summary-card {
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          margin-bottom: 12px;
        }

        .cpu-summary-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 3px 0;
          font-size: 0.75rem;
        }

        .cpu-summary-label {
          color: var(--text-secondary, #888899);
        }

        .cpu-summary-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-weight: 600;
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

  /** Get the current control tier. */
  _getTier() {
    return window.controlTier || "raw";
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

    const tier = this._getTier();

    switch (tier) {
      case "manual":
        this._renderManual(container, ship);
        break;
      case "arcade":
        this._renderArcade(container, ship);
        break;
      case "cpu-assist":
        this._renderCpuAssist(container, ship);
        break;
      default: // "raw"
        this._renderRaw(container, ship);
        break;
    }
  }

  // =========================================================================
  // MANUAL tier: Raw engineering values in physical units
  // =========================================================================
  _renderManual(container, ship) {
    const eng = ship.engineering || {};
    const propulsion = ship.systems?.propulsion || {};
    const thermal = ship.thermal || {};

    // Reactor output in kW (not %)
    const reactorFraction = eng.reactor_output ?? (eng.reactor_percent != null ? eng.reactor_percent / 100 : 1.0);
    const maxPowerKw = eng.max_power_kw ?? 1000;
    const reactorKw = reactorFraction * maxPowerKw;
    const reactorClass = reactorFraction > 0.95 ? "critical" : reactorFraction > 0.8 ? "warning" : "nominal";

    // Temperature in Kelvin
    const hullTemp = thermal.hull_temperature ?? 0;
    const maxTemp = thermal.max_temperature ?? 500;
    const tempClass = hullTemp > maxTemp * 0.9 ? "critical" : hullTemp > maxTemp * 0.7 ? "warning" : "nominal";

    // Radiators: deploy/retract toggle
    const radDeployed = eng.radiators_deployed ?? true;

    // Fuel mass in kg
    const fuelLevel = propulsion.fuel_level ?? propulsion.fuel ?? 0;
    const maxFuel = propulsion.max_fuel ?? 100;

    // Drive throttle limit as fraction (0.0-1.0)
    const driveLimit = eng.drive_limit ?? (eng.drive_limit_percent != null ? eng.drive_limit_percent / 100 : 1.0);
    const actualThrottle = propulsion.throttle ?? 0;

    let html = "";

    // --- Reactor: raw kW ---
    html += '<div class="section">';
    html += '<div class="section-title">Reactor Output</div>';
    html += `
      <div class="status-row">
        <span class="readout-large ${reactorClass}">${reactorKw.toFixed(0)}</span>
        <span class="readout-unit">kW</span>
      </div>
      <div class="indicator-bar">
        <div class="indicator-fill ${reactorClass}" style="width: ${Math.min(reactorFraction * 100, 100)}%"></div>
      </div>
      <div class="slider-control">
        <input type="range" id="reactor-slider" min="0" max="100" step="5" value="${Math.round(reactorFraction * 100)}">
        <span class="slider-value" id="reactor-slider-value">${reactorKw.toFixed(0)} kW</span>
      </div>
    `;
    html += "</div>";

    // --- Hull Temperature in Kelvin ---
    html += '<div class="section">';
    html += '<div class="section-title">Hull Temperature</div>';
    html += `
      <div class="status-row">
        <span class="readout-large ${tempClass}">${hullTemp.toFixed(1)}</span>
        <span class="readout-unit">K</span>
      </div>
      <div class="status-row">
        <span class="status-label">Max Rated</span>
        <span class="status-value">${maxTemp.toFixed(0)} K</span>
      </div>
    `;
    html += "</div>";

    // --- Radiator toggle ---
    html += '<div class="section">';
    html += '<div class="section-title">Radiators</div>';
    html += `
      <div class="status-row">
        <span class="status-label">Status</span>
        <span class="status-value ${radDeployed ? 'nominal' : 'warning'}">${radDeployed ? "DEPLOYED" : "RETRACTED"}</span>
      </div>
      <div class="radiator-controls">
        <button class="eng-btn ${radDeployed ? 'active' : ''}" id="btn-rad-toggle">
          ${radDeployed ? "RETRACT" : "DEPLOY"}
        </button>
      </div>
    `;
    html += "</div>";

    // --- Fuel mass in kg ---
    html += '<div class="section">';
    html += '<div class="section-title">Fuel Mass</div>';
    html += `
      <div class="status-row">
        <span class="readout-large">${fuelLevel.toFixed(1)}</span>
        <span class="readout-unit">kg</span>
      </div>
      <div class="status-row">
        <span class="status-label">Max Capacity</span>
        <span class="status-value">${maxFuel.toFixed(1)} kg</span>
      </div>
    `;
    html += "</div>";

    // --- Drive throttle limit as fraction ---
    html += '<div class="section">';
    html += '<div class="section-title">Drive Throttle Limit</div>';
    html += `
      <div class="status-row">
        <span class="status-label">Limit</span>
        <span class="status-value info">${driveLimit.toFixed(2)}</span>
      </div>
      <div class="status-row">
        <span class="status-label">Actual</span>
        <span class="status-value ${actualThrottle > 0.8 ? 'warning' : 'nominal'}">${actualThrottle.toFixed(2)}</span>
      </div>
      <div class="dual-bar">
        <div class="dual-bar-fill limit" style="width: ${Math.min(driveLimit * 100, 100)}%"></div>
        <div class="dual-bar-fill actual" style="width: ${Math.min(actualThrottle * 100, 100)}%"></div>
      </div>
      <div class="slider-control">
        <input type="range" id="drive-slider" min="0" max="100" step="5" value="${Math.round(driveLimit * 100)}">
        <span class="slider-value" id="drive-slider-value">${driveLimit.toFixed(2)}</span>
      </div>
    `;
    html += "</div>";

    container.innerHTML = html;
    this._attachManualListeners(eng, radDeployed, maxPowerKw);
  }

  _attachManualListeners(eng, radDeployed, maxPowerKw) {
    const reactorSlider = this.shadowRoot.getElementById("reactor-slider");
    const reactorValue = this.shadowRoot.getElementById("reactor-slider-value");
    if (reactorSlider) {
      reactorSlider.addEventListener("input", (e) => {
        const kw = (parseInt(e.target.value, 10) / 100) * maxPowerKw;
        if (reactorValue) reactorValue.textContent = kw.toFixed(0) + " kW";
      });
      reactorSlider.addEventListener("change", (e) => {
        this._sendCommand("set_reactor_output", { output: parseInt(e.target.value, 10) });
      });
    }

    const driveSlider = this.shadowRoot.getElementById("drive-slider");
    const driveValue = this.shadowRoot.getElementById("drive-slider-value");
    if (driveSlider) {
      driveSlider.addEventListener("input", (e) => {
        if (driveValue) driveValue.textContent = (parseInt(e.target.value, 10) / 100).toFixed(2);
      });
      driveSlider.addEventListener("change", (e) => {
        this._sendCommand("throttle_drive", { limit: parseInt(e.target.value, 10) });
      });
    }

    const btnRadToggle = this.shadowRoot.getElementById("btn-rad-toggle");
    if (btnRadToggle) {
      btnRadToggle.addEventListener("click", () => {
        this._sendCommand("manage_radiators", {
          deployed: !radDeployed,
          priority: eng.radiator_priority || "balanced",
        });
      });
    }
  }

  // =========================================================================
  // RAW tier: Full engineering dashboard (all details, repair queue)
  // =========================================================================
  _renderRaw(container, ship) {
    const eng = ship.engineering || {};
    const propulsion = ship.systems?.propulsion || {};
    const thermal = ship.thermal || {};

    const reactorOutput = eng.reactor_percent ?? ((eng.reactor_output ?? 1.0) * 100);
    const reactorClass = reactorOutput > 95 ? "critical" : reactorOutput > 80 ? "warning" : "nominal";
    const driveLimit = eng.drive_limit_percent ?? ((eng.drive_limit ?? 1.0) * 100);
    const actualThrottle = propulsion.throttle ?? 0;
    const actualThrottlePct = (actualThrottle * 100).toFixed(0);
    const radDeployed = eng.radiators_deployed ?? true;
    const radPriority = eng.radiator_priority || "balanced";
    const radEfficiency = thermal.radiator_factor ?? 1;

    const fuelLevel = propulsion.fuel_level ?? propulsion.fuel ?? 0;
    const maxFuel = propulsion.max_fuel ?? 100;
    const fuelPercent = propulsion.fuel_percent ?? (maxFuel > 0 ? (fuelLevel / maxFuel) * 100 : 0);
    const burnRate = eng.fuel_burn_rate ?? propulsion.fuel_consumption ?? 0;
    const deltaV = ship.delta_v_remaining ?? propulsion.delta_v ?? 0;
    const timeToEmpty = burnRate > 0 ? (fuelLevel / burnRate) : Infinity;
    const fuelClass = fuelPercent > 50 ? "nominal" : fuelPercent > 20 ? "warning" : "critical";

    const ventAvailable = eng.emergency_vent_available ?? false;
    const ventActive = eng.emergency_vent_active ?? false;
    const ventRemaining = eng.emergency_vent_remaining ?? 0;
    const ventRate = eng.vent_rate ?? 0;

    // Repair queue data
    const repairQueue = eng.repair_queue || ship.repair_queue || [];

    let html = "";

    // --- Reactor Output ---
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

    // --- Drive Limit ---
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

    // --- Radiators (full detail) ---
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
      <div class="status-row">
        <span class="status-label">Efficiency</span>
        <span class="status-value ${radEfficiency < 0.5 ? 'warning' : ''}">${(radEfficiency * 100).toFixed(0)}%</span>
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

    // --- Fuel (full detail) ---
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

    // --- Repair Queue (RAW: full with time estimates) ---
    html += '<div class="section">';
    html += '<div class="section-title">Repair Queue</div>';
    html += '<div class="repair-queue">';
    if (repairQueue.length === 0) {
      html += '<div class="repair-empty">No repairs in progress</div>';
    } else {
      repairQueue.forEach(item => {
        const name = item.system || item.name || "Unknown";
        const timeLeft = item.time_remaining ?? item.eta ?? 0;
        html += `
          <div class="repair-item">
            <span class="repair-item-name">${name}</span>
            <span class="repair-item-time">${this._formatTime(timeLeft)}</span>
          </div>
        `;
      });
    }
    html += "</div></div>";

    // --- Emergency Vent ---
    html += this._renderVentSection(ventAvailable, ventActive, ventRemaining, ventRate);

    container.innerHTML = html;
    this._attachRawListeners(eng, propulsion, radDeployed, radPriority, ventAvailable, ventActive);
  }

  _attachRawListeners(eng, propulsion, radDeployed, radPriority, ventAvailable, ventActive) {
    const reactorSlider = this.shadowRoot.getElementById("reactor-slider");
    const reactorValue = this.shadowRoot.getElementById("reactor-slider-value");
    if (reactorSlider) {
      reactorSlider.addEventListener("input", (e) => {
        if (reactorValue) reactorValue.textContent = e.target.value + "%";
      });
      reactorSlider.addEventListener("change", (e) => {
        this._sendCommand("set_reactor_output", { output: parseInt(e.target.value, 10) });
      });
    }

    const driveSlider = this.shadowRoot.getElementById("drive-slider");
    const driveValue = this.shadowRoot.getElementById("drive-slider-value");
    if (driveSlider) {
      driveSlider.addEventListener("input", (e) => {
        if (driveValue) driveValue.textContent = e.target.value + "%";
      });
      driveSlider.addEventListener("change", (e) => {
        this._sendCommand("throttle_drive", { limit: parseInt(e.target.value, 10) });
      });
    }

    const btnRadToggle = this.shadowRoot.getElementById("btn-rad-toggle");
    if (btnRadToggle) {
      btnRadToggle.addEventListener("click", () => {
        this._sendCommand("manage_radiators", {
          deployed: !radDeployed,
          priority: radPriority,
        });
      });
    }

    this.shadowRoot.querySelectorAll("[data-priority]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        this._sendCommand("manage_radiators", {
          deployed: radDeployed,
          priority: e.currentTarget.dataset.priority,
        });
      });
    });

    this._attachVentListeners(ventAvailable, ventActive);
  }

  // =========================================================================
  // ARCADE tier: Simplified engineering with % values and one-click actions
  // =========================================================================
  _renderArcade(container, ship) {
    const eng = ship.engineering || {};
    const propulsion = ship.systems?.propulsion || {};
    const thermal = ship.thermal || {};

    // Reactor as %
    const reactorOutput = eng.reactor_percent ?? ((eng.reactor_output ?? 1.0) * 100);
    const reactorClass = reactorOutput > 95 ? "critical" : reactorOutput > 80 ? "warning" : "nominal";

    // Thermal margin: "% to overheat"
    const hullTemp = thermal.hull_temperature ?? 0;
    const maxTemp = thermal.max_temperature ?? 500;
    const thermalPercent = maxTemp > 0 ? (hullTemp / maxTemp) * 100 : 0;
    const marginPct = Math.max(0, 100 - thermalPercent);
    const thermalClass = marginPct < 10 ? "critical" : marginPct < 30 ? "warning" : "nominal";

    // Fuel budget in hours at current burn rate
    const fuelLevel = propulsion.fuel_level ?? propulsion.fuel ?? 0;
    const burnRate = eng.fuel_burn_rate ?? propulsion.fuel_consumption ?? 0;
    const fuelPercent = propulsion.fuel_percent ?? ((propulsion.max_fuel ?? 100) > 0 ? (fuelLevel / (propulsion.max_fuel ?? 100)) * 100 : 0);
    const burnHours = burnRate > 0 ? (fuelLevel / burnRate) / 3600 : Infinity;
    const fuelClass = fuelPercent > 50 ? "nominal" : fuelPercent > 20 ? "warning" : "critical";

    // Vent
    const ventAvailable = eng.emergency_vent_available ?? false;
    const ventActive = eng.emergency_vent_active ?? false;
    const ventRemaining = eng.emergency_vent_remaining ?? 0;
    const ventRate = eng.vent_rate ?? 0;

    // Repair queue
    const repairQueue = eng.repair_queue || ship.repair_queue || [];

    let html = "";

    // --- Reactor Output (%) ---
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

    // --- Thermal Margin ---
    html += '<div class="section">';
    html += '<div class="section-title">Thermal Margin</div>';
    html += `
      <div class="status-row">
        <span class="status-label">Margin to Overheat</span>
        <span class="status-value ${thermalClass}">${marginPct.toFixed(0)}%</span>
      </div>
      <div class="indicator-bar">
        <div class="indicator-fill ${thermalClass}" style="width: ${Math.min(marginPct, 100)}%"></div>
      </div>
    `;
    // Time to overheat countdown (if temperature is rising)
    const netHeat = thermal.net_heat_rate ?? 0;
    if (netHeat > 0 && hullTemp < maxTemp) {
      const secToOverheat = (maxTemp - hullTemp) / (netHeat * 0.001);
      html += `
        <div class="status-row">
          <span class="status-label">Time to Overheat</span>
          <span class="status-value critical">${this._formatTime(secToOverheat)}</span>
        </div>
      `;
    }
    html += "</div>";

    // --- Fuel Budget ---
    html += '<div class="section">';
    html += '<div class="section-title">Fuel Budget</div>';
    html += `
      <div class="status-row">
        <span class="status-label">Fuel Level</span>
        <span class="status-value ${fuelClass}">${fuelPercent.toFixed(0)}%</span>
      </div>
      <div class="fuel-bar-container">
        <div class="fuel-bar">
          <div class="fuel-bar-fill ${fuelClass}" style="width: ${Math.min(fuelPercent, 100)}%"></div>
        </div>
      </div>
      <div class="status-row">
        <span class="status-label">Burn Time</span>
        <span class="status-value ${burnHours < 0.5 ? 'critical' : burnHours < 2 ? 'warning' : ''}">${
          isFinite(burnHours) ? (burnHours >= 1 ? burnHours.toFixed(1) + " hours" : this._formatTime(burnHours * 3600)) : "IDLE"
        }</span>
      </div>
    `;
    html += "</div>";

    // --- Repair Priority (dropdown) ---
    html += '<div class="section">';
    html += '<div class="section-title">Repair Priority</div>';
    if (repairQueue.length === 0) {
      html += '<div class="repair-empty">No repairs needed</div>';
    } else {
      html += '<select class="repair-dropdown" id="repair-priority-select">';
      repairQueue.forEach((item, i) => {
        const name = item.system || item.name || "Unknown";
        html += `<option value="${i}">${name}</option>`;
      });
      html += '</select>';
      const topItem = repairQueue[0];
      const topTime = topItem?.time_remaining ?? topItem?.eta ?? 0;
      html += `
        <div class="status-row" style="margin-top: 6px;">
          <span class="status-label">Current Repair ETA</span>
          <span class="status-value warning">${this._formatTime(topTime)}</span>
        </div>
      `;
    }
    html += "</div>";

    // --- Emergency Vent (one-click in arcade) ---
    html += this._renderVentSection(ventAvailable, ventActive, ventRemaining, ventRate);

    container.innerHTML = html;
    this._attachArcadeListeners(eng, ventAvailable, ventActive);
  }

  _attachArcadeListeners(eng, ventAvailable, ventActive) {
    const reactorSlider = this.shadowRoot.getElementById("reactor-slider");
    const reactorValue = this.shadowRoot.getElementById("reactor-slider-value");
    if (reactorSlider) {
      reactorSlider.addEventListener("input", (e) => {
        if (reactorValue) reactorValue.textContent = e.target.value + "%";
      });
      reactorSlider.addEventListener("change", (e) => {
        this._sendCommand("set_reactor_output", { output: parseInt(e.target.value, 10) });
      });
    }

    const repairSelect = this.shadowRoot.getElementById("repair-priority-select");
    if (repairSelect) {
      repairSelect.addEventListener("change", (e) => {
        this._sendCommand("set_repair_priority", { index: parseInt(e.target.value, 10) });
      });
    }

    this._attachVentListeners(ventAvailable, ventActive);
  }

  // =========================================================================
  // CPU-ASSIST tier: Auto-engineering hero + minimal manual controls
  // =========================================================================
  _renderCpuAssist(container, ship) {
    const eng = ship.engineering || {};
    const propulsion = ship.systems?.propulsion || {};
    const thermal = ship.thermal || {};
    const autoEng = ship.auto_engineering || {};

    const reactorOutput = eng.reactor_percent ?? ((eng.reactor_output ?? 1.0) * 100);
    const fuelLevel = propulsion.fuel_level ?? propulsion.fuel ?? 0;
    const maxFuel = propulsion.max_fuel ?? 100;
    const fuelPercent = propulsion.fuel_percent ?? (maxFuel > 0 ? (fuelLevel / maxFuel) * 100 : 0);
    const hullTemp = thermal.hull_temperature ?? 0;
    const maxTemp = thermal.max_temperature ?? 500;
    const thermalPercent = maxTemp > 0 ? (hullTemp / maxTemp) * 100 : 0;
    const ventAvailable = eng.emergency_vent_available ?? false;
    const ventActive = eng.emergency_vent_active ?? false;
    const ventRemaining = eng.emergency_vent_remaining ?? 0;
    const ventRate = eng.vent_rate ?? 0;

    let html = "";

    // --- Auto-Engineering panel (HERO) ---
    const proposals = autoEng.proposals || [];
    html += '<div class="auto-eng-panel">';
    html += '<div class="auto-eng-header">';
    html += '<span class="auto-eng-title">AUTO ENGINEERING</span>';
    html += `<button class="auto-eng-toggle ${autoEng.enabled ? 'enabled' : ''}" id="auto-eng-toggle">
      ${autoEng.enabled ? "DISABLE" : "ENABLE"}
    </button>`;
    html += '</div>';
    html += '<div id="eng-proposals" class="proposals-container">';
    if (proposals.length === 0) {
      html += '<div class="no-proposals">No pending proposals</div>';
    } else {
      proposals.forEach(p => {
        const confidence = p.confidence ?? 0;
        const remaining = Math.max(0, p.time_remaining || 0);
        const total = p.total_time || 30;
        const timerPct = Math.min(100, (remaining / total) * 100);
        const isUrgent = confidence > 0.8 || remaining < 5;
        const urgentClass = isUrgent ? " urgent" : "";
        html += `
          <div class="proposal-card${urgentClass}">
            <div class="proposal-header">
              <span class="proposal-action">${p.description || p.action}</span>
              ${confidence > 0 ? `<span class="proposal-confidence">${(confidence * 100).toFixed(0)}%</span>` : ""}
            </div>
            ${remaining > 0 ? `<div class="proposal-timer"><div class="proposal-timer-fill" style="width:${timerPct}%"></div></div>` : ""}
            <div class="proposal-actions">
              <button class="proposal-approve" data-approve="${p.id}">APPROVE</button>
              <button class="proposal-deny" data-deny="${p.id}">DENY</button>
            </div>
          </div>
        `;
      });
    }
    html += '</div></div>';

    // --- Summary card: compact overview of ship engineering state ---
    html += '<div class="cpu-summary-card">';
    html += `
      <div class="cpu-summary-row">
        <span class="cpu-summary-label">Reactor</span>
        <span class="cpu-summary-value ${reactorOutput > 95 ? 'critical' : reactorOutput > 80 ? 'warning' : 'nominal'}">${reactorOutput.toFixed(0)}%</span>
      </div>
      <div class="cpu-summary-row">
        <span class="cpu-summary-label">Thermal Load</span>
        <span class="cpu-summary-value ${thermalPercent > 90 ? 'critical' : thermalPercent > 70 ? 'warning' : 'nominal'}">${thermalPercent.toFixed(0)}%</span>
      </div>
      <div class="cpu-summary-row">
        <span class="cpu-summary-label">Fuel</span>
        <span class="cpu-summary-value ${fuelPercent < 20 ? 'critical' : fuelPercent < 50 ? 'warning' : 'nominal'}">${fuelPercent.toFixed(0)}%</span>
      </div>
    `;
    html += '</div>';

    // --- Emergency vent (still available as safety override) ---
    html += this._renderVentSection(ventAvailable, ventActive, ventRemaining, ventRate);

    container.innerHTML = html;
    this._attachCpuAssistListeners(ventAvailable, ventActive);
  }

  _attachCpuAssistListeners(ventAvailable, ventActive) {
    // Auto-engineering toggle
    const toggle = this.shadowRoot.getElementById("auto-eng-toggle");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const ship = stateManager.getShipState();
        const cmd = ship?.auto_engineering?.enabled ? "disable_auto_engineering" : "enable_auto_engineering";
        wsClient.sendShipCommand(cmd, {});
      });
    }

    // Proposal approve/deny buttons (delegated)
    const proposals = this.shadowRoot.getElementById("eng-proposals");
    if (proposals) {
      proposals.addEventListener("click", (e) => {
        const approveBtn = e.target.closest(".proposal-approve");
        const denyBtn = e.target.closest(".proposal-deny");
        if (approveBtn) wsClient.sendShipCommand("approve_engineering", { proposal_id: approveBtn.dataset.approve });
        if (denyBtn) wsClient.sendShipCommand("deny_engineering", { proposal_id: denyBtn.dataset.deny });
      });
    }

    this._attachVentListeners(ventAvailable, ventActive);
  }

  // =========================================================================
  // Shared: emergency vent section (used by all tiers)
  // =========================================================================
  _renderVentSection(ventAvailable, ventActive, ventRemaining, ventRate) {
    let html = '<div class="section">';
    html += '<div class="section-title">Emergency Coolant Vent</div>';

    if (ventActive) {
      html += `
        <button class="vent-btn active" id="btn-vent" disabled>VENTING COOLANT</button>
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
        <button class="vent-btn" id="btn-vent" disabled>EMERGENCY VENT</button>
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
        <button class="vent-btn ${ventDisabled ? 'disabled' : ''}" id="btn-vent">EMERGENCY VENT</button>
        <div class="status-row">
          <span class="status-label">Status</span>
          <span class="status-value ${ventAvailable ? 'nominal' : 'critical'}">${ventAvailable ? "AVAILABLE" : "DEPLETED"}</span>
        </div>
      `;
    }

    html += "</div>";
    return html;
  }

  _attachVentListeners(ventAvailable, ventActive) {
    const btnVent = this.shadowRoot.getElementById("btn-vent");
    if (btnVent && !ventActive) {
      btnVent.addEventListener("click", () => {
        if (!ventAvailable) return;
        this._ventConfirmPending = true;
        this._updateDisplay();
      });
    }

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
  }

  // =========================================================================
  // Formatting helpers
  // =========================================================================

  _formatDeltaV(dv) {
    if (dv >= 1000) return (dv / 1000).toFixed(2) + " km/s";
    return dv.toFixed(1) + " m/s";
  }

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

  _formatWatts(w) {
    const abs = Math.abs(w);
    const sign = w < 0 ? "-" : "";
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)} MW`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)} kW`;
    return `${sign}${abs.toFixed(0)} W`;
  }
}

customElements.define("engineering-control-panel", EngineeringControlPanel);
export { EngineeringControlPanel };
