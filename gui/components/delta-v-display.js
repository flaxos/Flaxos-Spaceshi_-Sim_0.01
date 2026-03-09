/**
 * Delta-V Display
 * Shows delta-V budget, fuel mass, burn time estimates, and mass breakdown.
 * Critical for Raw tier where the player needs precise maneuvering budget info.
 */

import { stateManager } from "../js/state-manager.js";

const G0 = 9.81; // standard gravity, m/s^2
const BINGO_THRESHOLD = 0.10; // 10% fuel triggers BINGO warning

class DeltaVDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
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

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          padding: 16px;
        }

        .section {
          margin-bottom: 16px;
        }

        .section:last-child {
          margin-bottom: 0;
        }

        .section-title {
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .readout-grid {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 4px 16px;
        }

        .readout-label {
          color: var(--text-dim, #555566);
        }

        .readout-value {
          color: var(--text-primary, #e0e0e0);
          text-align: right;
        }

        /* Large primary readout for delta-V */
        .primary-readout {
          text-align: center;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
          margin-bottom: 16px;
        }

        .primary-value {
          font-size: 1.8rem;
          font-weight: 700;
          color: var(--text-primary, #e0e0e0);
          line-height: 1.2;
        }

        .primary-unit {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-top: 2px;
        }

        .primary-label {
          font-size: 0.65rem;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-top: 4px;
        }

        /* Fuel bar */
        .fuel-bar-container {
          margin-bottom: 16px;
        }

        .fuel-bar-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 6px;
        }

        .fuel-bar {
          height: 20px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
          position: relative;
        }

        .fuel-fill {
          height: 100%;
          transition: width 0.3s ease, background-color 0.3s ease;
          border-radius: 4px;
        }

        .fuel-fill.green  { background: var(--status-nominal, #00ff88); }
        .fuel-fill.amber  { background: var(--status-warning, #ffaa00); }
        .fuel-fill.red    { background: var(--status-critical, #ff4444); }

        .fuel-text {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 0.75rem;
          color: var(--text-bright, #ffffff);
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
        }

        /* BINGO FUEL warning */
        .bingo-warning {
          padding: 8px 12px;
          background: rgba(255, 68, 68, 0.15);
          border: 1px solid var(--status-critical, #ff4444);
          border-radius: 6px;
          text-align: center;
          margin-bottom: 16px;
          animation: bingo-pulse 1.5s ease-in-out infinite;
        }

        .bingo-text {
          font-weight: 700;
          font-size: 0.85rem;
          color: var(--status-critical, #ff4444);
          letter-spacing: 2px;
        }

        @keyframes bingo-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        /* Two-column layout for thrust/accel */
        .dual-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }

        .stat-box {
          text-align: center;
          padding: 10px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }

        .stat-value {
          font-size: 1.1rem;
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        .stat-sub {
          font-size: 0.7rem;
          color: var(--status-info, #00aaff);
          margin-top: 2px;
        }

        .stat-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-top: 4px;
        }

        .separator {
          grid-column: span 2;
          border-top: 1px solid var(--border-default, #2a2a3a);
          margin: 4px 0;
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for propulsion data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for propulsion data...</div>';
      return;
    }

    const prop = ship.systems?.propulsion || {};
    const fuel = ship.fuel || {};

    // Resolve fuel values from multiple possible data paths
    const fuelMass = prop.fuel_mass ?? fuel.current ?? 0;
    const fuelCapacity = prop.fuel_capacity ?? fuel.capacity ?? 0;
    const fuelPct = fuelCapacity > 0 ? fuelMass / fuelCapacity : 0;

    const maxThrust = prop.max_thrust_n ?? prop.max_thrust ?? 0;
    const dryMass = prop.dry_mass ?? ship.mass ?? 0;
    const wetMass = dryMass + fuelMass;

    // Exhaust velocity: prefer direct, else derive from Isp
    const exhaustVelocity = prop.exhaust_velocity ?? (prop.isp ? prop.isp * G0 : 0);

    // Delta-V: use server value if available, otherwise Tsiolkovsky
    let deltaV = prop.delta_v ?? null;
    if (deltaV === null && exhaustVelocity > 0 && dryMass > 0 && wetMass > dryMass) {
      deltaV = exhaustVelocity * Math.log(wetMass / dryMass);
    }
    deltaV = deltaV ?? 0;

    // Acceleration: F = ma, report in m/s^2 and G
    const maxAccelMs2 = wetMass > 0 ? maxThrust / wetMass : 0;
    const maxAccelG = maxAccelMs2 / G0;

    // Current thrust accounting for throttle
    const throttle = prop.throttle ?? 0;
    const currentThrust = maxThrust * throttle;

    // Estimated burn time at current thrust
    // burn_time = fuel_mass / mass_flow_rate
    // mass_flow_rate = thrust / exhaust_velocity
    let burnTimeSeconds = null;
    if (currentThrust > 0 && exhaustVelocity > 0) {
      const massFlowRate = currentThrust / exhaustVelocity;
      burnTimeSeconds = massFlowRate > 0 ? fuelMass / massFlowRate : null;
    }

    // Fuel bar color class
    const fuelColor = fuelPct > 0.50 ? "green" : fuelPct > 0.25 ? "amber" : "red";
    const isBingo = fuelPct < BINGO_THRESHOLD && fuelCapacity > 0;

    content.innerHTML = `
      ${isBingo ? `
        <div class="bingo-warning">
          <div class="bingo-text">BINGO FUEL</div>
        </div>
      ` : ""}

      <div class="primary-readout">
        <div class="primary-value">${this._formatDeltaV(deltaV)}</div>
        <div class="primary-unit">m/s</div>
        <div class="primary-label">Delta-V Remaining</div>
      </div>

      <div class="fuel-bar-container">
        <div class="fuel-bar-header">
          <span class="section-title">Fuel</span>
          <span class="readout-value">${this._formatMass(fuelMass)}</span>
        </div>
        <div class="fuel-bar">
          <div class="fuel-fill ${fuelColor}" style="width: ${(fuelPct * 100).toFixed(1)}%"></div>
          <span class="fuel-text">${(fuelPct * 100).toFixed(1)}%</span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Thrust / Acceleration</div>
        <div class="dual-grid">
          <div class="stat-box">
            <div class="stat-value">${this._formatThrust(maxThrust)}</div>
            <div class="stat-label">Max Thrust</div>
          </div>
          <div class="stat-box">
            <div class="stat-value">${maxAccelMs2.toFixed(2)}</div>
            <div class="stat-sub">${maxAccelG.toFixed(3)} G</div>
            <div class="stat-label">Max Accel (m/s\u00B2)</div>
          </div>
        </div>
      </div>

      ${burnTimeSeconds !== null ? `
        <div class="section">
          <div class="section-title">Burn Time at Current Thrust</div>
          <div class="primary-readout" style="margin-bottom: 0;">
            <div class="stat-value" style="font-size: 1.2rem;">${this._formatDuration(burnTimeSeconds)}</div>
            <div class="primary-label">${(throttle * 100).toFixed(0)}% throttle</div>
          </div>
        </div>
      ` : ""}

      <div class="section">
        <div class="section-title">Mass Breakdown</div>
        <div class="readout-grid">
          <span class="readout-label">Dry Mass:</span>
          <span class="readout-value">${this._formatMass(dryMass)}</span>
          <span class="readout-label">Fuel Mass:</span>
          <span class="readout-value">${this._formatMass(fuelMass)}</span>
          <span class="readout-label">Wet Mass:</span>
          <span class="readout-value">${this._formatMass(wetMass)}</span>
          ${fuelCapacity > 0 ? `
            <span class="readout-label">Fuel Cap:</span>
            <span class="readout-value">${this._formatMass(fuelCapacity)}</span>
          ` : ""}
          ${exhaustVelocity > 0 ? `
            <span class="readout-label">V<sub>e</sub>:</span>
            <span class="readout-value">${this._formatVelocity(exhaustVelocity)}</span>
          ` : ""}
          ${prop.isp ? `
            <span class="readout-label">Isp:</span>
            <span class="readout-value">${prop.isp.toFixed(0)} s</span>
          ` : ""}
        </div>
      </div>
    `;
  }

  /**
   * Format delta-V as a large monospace readout.
   * Uses km/s if above 10,000 m/s for readability.
   */
  _formatDeltaV(ms) {
    if (ms >= 10000) {
      return (ms / 1000).toFixed(2);
    }
    return ms.toFixed(1);
  }

  /**
   * Format mass in kg or tonnes depending on magnitude.
   */
  _formatMass(kg) {
    if (kg >= 1000000) {
      return `${(kg / 1000).toFixed(1)} t`;
    }
    if (kg >= 1000) {
      return `${(kg / 1000).toFixed(2)} t`;
    }
    return `${kg.toFixed(1)} kg`;
  }

  /**
   * Format thrust in N or kN depending on magnitude.
   */
  _formatThrust(newtons) {
    if (newtons >= 1000000) {
      return `${(newtons / 1000000).toFixed(2)} MN`;
    }
    if (newtons >= 1000) {
      return `${(newtons / 1000).toFixed(1)} kN`;
    }
    return `${newtons.toFixed(1)} N`;
  }

  /**
   * Format velocity in m/s or km/s.
   */
  _formatVelocity(mps) {
    if (mps >= 1000) {
      return `${(mps / 1000).toFixed(2)} km/s`;
    }
    return `${mps.toFixed(1)} m/s`;
  }

  /**
   * Format duration as hours/minutes/seconds.
   */
  _formatDuration(seconds) {
    const totalSeconds = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}h ${minutes.toString().padStart(2, "0")}m ${secs.toString().padStart(2, "0")}s`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs.toString().padStart(2, "0")}s`;
    }
    return `${secs}s`;
  }
}

customElements.define("delta-v-display", DeltaVDisplay);
export { DeltaVDisplay };
