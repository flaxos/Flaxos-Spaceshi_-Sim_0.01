/**
 * Ship Status Panel
 * Displays hull, fuel, power, systems status
 */

import { stateManager } from "../js/state-manager.js";

class ShipStatus extends HTMLElement {
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
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.85rem;
          padding: 16px;
        }

        .section {
          margin-bottom: 16px;
        }

        .section:last-child {
          margin-bottom: 0;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .bar-container {
          margin-bottom: 12px;
        }

        .bar-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 4px;
        }

        .bar-label {
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
        }

        .bar-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .bar {
          height: 16px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
          position: relative;
        }

        .bar-fill {
          height: 100%;
          transition: width 0.3s ease, background 0.3s ease;
        }

        .bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .bar-fill.critical { background: var(--status-critical, #ff4444); }

        .bar-text {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-bright, #ffffff);
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
        }

        .systems-grid {
          display: grid;
          gap: 8px;
        }

        .system-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
        }

        .system-indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .system-indicator.online {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 6px var(--status-nominal, #00ff88);
        }

        .system-indicator.offline {
          background: var(--status-offline, #555566);
        }

        .system-indicator.warning {
          background: var(--status-warning, #ffaa00);
          box-shadow: 0 0 6px var(--status-warning, #ffaa00);
        }

        .system-indicator.error {
          background: var(--status-critical, #ff4444);
          box-shadow: 0 0 6px var(--status-critical, #ff4444);
        }

        .system-name {
          flex: 1;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
        }

        .system-status {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          text-transform: uppercase;
        }

        .system-status.online { color: var(--status-nominal, #00ff88); }
        .system-status.offline { color: var(--text-dim, #555566); }
        .system-status.warning { color: var(--status-warning, #ffaa00); }
        .system-status.error { color: var(--status-critical, #ff4444); }

        .stats-row {
          display: flex;
          justify-content: space-between;
          padding: 8px 0;
          border-top: 1px solid var(--border-default, #2a2a3a);
          margin-top: 8px;
        }

        .stat {
          text-align: center;
        }

        .stat-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.9rem;
          color: var(--text-primary, #e0e0e0);
        }

        .stat-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for ship data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for ship data...</div>';
      return;
    }

    // Extract values
    const hull = this._getHull(ship);
    const fuel = this._getFuel(ship);
    const power = this._getPower(ship);
    const systems = this._getSystems(ship);
    const mass = ship.mass || 0;
    const deltaV = ship.delta_v || ship.deltaV || 0;

    content.innerHTML = `
      <div class="section">
        ${this._renderBar("HULL", hull.percent, hull.text)}
        ${this._renderBar("FUEL", fuel.percent, fuel.text)}
        ${this._renderBar("POWER", power.percent, power.text)}
      </div>

      <div class="section">
        <div class="section-title">Systems</div>
        <div class="systems-grid">
          ${systems.map(s => this._renderSystem(s)).join("")}
        </div>
      </div>

      <div class="stats-row">
        <div class="stat">
          <div class="stat-value">${this._formatNumber(mass)} kg</div>
          <div class="stat-label">Mass</div>
        </div>
        <div class="stat">
          <div class="stat-value">${this._formatNumber(deltaV)} m/s</div>
          <div class="stat-label">Δv Remaining</div>
        </div>
      </div>
    `;
  }

  _getHull(ship) {
    // Server provides hull_percent directly, or we can calculate from hull_integrity
    let percent = ship.hull_percent;
    if (percent === undefined && ship.hull_integrity !== undefined && ship.max_hull_integrity) {
      percent = (ship.hull_integrity / ship.max_hull_integrity) * 100;
    }
    percent = percent ?? ship.hull ?? 100;
    return {
      percent,
      text: `${percent.toFixed(0)}%`
    };
  }

  _getFuel(ship) {
    // Try systems.propulsion first
    const propulsion = ship.systems?.propulsion || {};
    const fuelMass = propulsion.fuel_level ?? ship.fuel_mass ?? ship.fuel ?? 0;
    const fuelCapacity = propulsion.max_fuel ?? ship.fuel_capacity ?? 10000;
    const percent = fuelCapacity > 0 ? (fuelMass / fuelCapacity) * 100 : 0;
    return {
      percent,
      text: `${percent.toFixed(0)}%  ${this._formatNumber(fuelMass)} kg`
    };
  }

  _getPower(ship) {
    // Try systems.power first
    const powerSystem = ship.systems?.power || ship.power_system || {};
    const reactorOutput = powerSystem.reactor_output ?? powerSystem.output ?? 0;
    const maxOutput = powerSystem.max_output ?? powerSystem.max_reactor_output ?? 1000;
    const percent = maxOutput > 0 ? (reactorOutput / maxOutput) * 100 : (ship.power_level ?? 100);
    return {
      percent,
      text: `${percent.toFixed(0)}%`
    };
  }

  _getSystems(ship) {
    const systemsStatus = ship.systems_status || ship.systems || {};
    const defaultSystems = ["Propulsion", "Sensors", "Weapons", "Navigation", "Comms"];

    const systems = [];

    // Use provided systems or defaults
    if (Object.keys(systemsStatus).length > 0) {
      for (const [name, status] of Object.entries(systemsStatus)) {
        systems.push({
          name: this._formatSystemName(name),
          status: this._normalizeStatus(status)
        });
      }
    } else {
      // Fallback to checking individual system properties
      for (const name of defaultSystems) {
        const key = name.toLowerCase();
        const system = ship[key] || ship[`${key}_system`];
        systems.push({
          name,
          status: system?.enabled !== false ? "online" : "offline"
        });
      }
    }

    return systems;
  }

  _formatSystemName(name) {
    return name
      .replace(/_/g, " ")
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  _normalizeStatus(status) {
    if (typeof status === "boolean") {
      return status ? "online" : "offline";
    }
    if (typeof status === "string") {
      const s = status.toLowerCase();
      if (s === "on" || s === "active" || s === "ready" || s === "idle" || s === "online") return "online";
      if (s === "off" || s === "inactive" || s === "disabled" || s === "offline") return "offline";
      if (s === "warning" || s === "degraded" || s === "no_fuel") return "warning";
      if (s === "error" || s === "failed" || s === "critical") return "error";
      // Unknown string status - assume online if not clearly offline
      return "online";
    }
    if (typeof status === "object" && status !== null) {
      // Check if system is enabled
      if (status.enabled === false) return "offline";
      // Check status string within the object
      if (status.status) {
        const s = String(status.status).toLowerCase();
        if (s === "error" || s === "failed" || s === "critical") return "error";
        if (s === "warning" || s === "degraded" || s === "no_fuel") return "warning";
        if (s === "offline" || s === "off" || s === "disabled") return "offline";
      }
      return "online";
    }
    return "offline";
  }

  _renderBar(label, percent, text) {
    const statusClass = percent > 50 ? "nominal" : percent > 25 ? "warning" : "critical";
    return `
      <div class="bar-container">
        <div class="bar-header">
          <span class="bar-label">${label}</span>
          <span class="bar-value">${text}</span>
        </div>
        <div class="bar">
          <div class="bar-fill ${statusClass}" style="width: ${Math.min(100, Math.max(0, percent))}%"></div>
        </div>
      </div>
    `;
  }

  _renderSystem(system) {
    return `
      <div class="system-row">
        <div class="system-indicator ${system.status}"></div>
        <span class="system-name">${system.name}</span>
        <span class="system-status ${system.status}">${system.status}</span>
      </div>
    `;
  }

  _formatNumber(num) {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + "M";
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + "k";
    }
    return num.toFixed(0);
  }
}

customElements.define("ship-status", ShipStatus);
export { ShipStatus };
