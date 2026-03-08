/**
 * Status Bar Component
 * Compact always-visible bar showing hull %, key subsystem icons, fuel gauge, ammo count.
 * Color-coded: green=nominal, yellow=impaired, red=critical.
 */

import { stateManager } from "../js/state-manager.js";

class StatusBar extends HTMLElement {
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
          background: var(--bg-panel, #12121a);
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          padding: 6px 12px;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.75rem;
        }

        .status-bar {
          display: flex;
          align-items: center;
          gap: 16px;
          flex-wrap: wrap;
        }

        .status-group {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .status-label {
          color: var(--text-dim, #555566);
          font-size: 0.65rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          font-weight: 600;
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          font-weight: 600;
        }

        .status-value.nominal { color: var(--status-nominal, #00ff88); }
        .status-value.warning { color: var(--status-warning, #ffaa00); }
        .status-value.critical { color: var(--status-critical, #ff4444); }
        .status-value.info { color: var(--status-info, #00aaff); }

        .mini-bar {
          width: 60px;
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          overflow: hidden;
        }

        .mini-bar-fill {
          height: 100%;
          transition: width 0.3s ease;
        }

        .mini-bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .mini-bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .mini-bar-fill.critical { background: var(--status-critical, #ff4444); }

        .separator {
          width: 1px;
          height: 16px;
          background: var(--border-default, #2a2a3a);
        }

        .subsystem-icons {
          display: flex;
          gap: 6px;
        }

        .subsystem-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          position: relative;
        }

        .subsystem-dot.online {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 4px var(--status-nominal, #00ff88);
        }

        .subsystem-dot.warning {
          background: var(--status-warning, #ffaa00);
          box-shadow: 0 0 4px var(--status-warning, #ffaa00);
        }

        .subsystem-dot.offline {
          background: var(--status-offline, #555566);
        }

        .subsystem-dot.error {
          background: var(--status-critical, #ff4444);
          box-shadow: 0 0 4px var(--status-critical, #ff4444);
        }

        .subsystem-dot[title] {
          cursor: help;
        }

        .empty-state {
          color: var(--text-dim, #555566);
          font-style: italic;
          font-size: 0.75rem;
        }

        @media (max-width: 768px) {
          .status-bar {
            gap: 10px;
            justify-content: center;
          }

          .status-label {
            font-size: 0.6rem;
          }

          .mini-bar {
            width: 40px;
          }
        }
      </style>

      <div class="status-bar" id="bar">
        <span class="empty-state">Awaiting ship data...</span>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const bar = this.shadowRoot.getElementById("bar");

    if (!ship || Object.keys(ship).length === 0) {
      bar.innerHTML = '<span class="empty-state">Awaiting ship data...</span>';
      return;
    }

    // Hull
    const hull = this._getHullPercent(ship);
    const hullClass = hull > 50 ? "nominal" : hull > 25 ? "warning" : "critical";

    // Fuel
    const fuel = this._getFuelPercent(ship);
    const fuelClass = fuel > 50 ? "nominal" : fuel > 20 ? "warning" : "critical";

    // Ammo
    const ammo = this._getAmmoSummary(ship);

    // Subsystems
    const systems = this._getSubsystems(ship);

    // Speed
    const nav = stateManager.getNavigation();
    const vel = nav.velocity || [0, 0, 0];
    const speed = Math.sqrt(vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2);

    bar.innerHTML = `
      <div class="status-group">
        <span class="status-label">HULL</span>
        <span class="status-value ${hullClass}">${hull.toFixed(0)}%</span>
        <div class="mini-bar">
          <div class="mini-bar-fill ${hullClass}" style="width: ${hull}%"></div>
        </div>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">SYS</span>
        <div class="subsystem-icons">
          ${systems.map(s =>
            `<div class="subsystem-dot ${s.status}" title="${s.name}: ${s.status.toUpperCase()}"></div>`
          ).join("")}
        </div>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">FUEL</span>
        <span class="status-value ${fuelClass}">${fuel.toFixed(0)}%</span>
        <div class="mini-bar">
          <div class="mini-bar-fill ${fuelClass}" style="width: ${fuel}%"></div>
        </div>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">AMMO</span>
        <span class="status-value ${ammo.cls}">${ammo.text}</span>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">VEL</span>
        <span class="status-value info">${this._formatSpeed(speed)}</span>
      </div>
    `;
  }

  _getHullPercent(ship) {
    let percent = ship.hull_percent;
    if (percent === undefined && ship.hull_integrity !== undefined && ship.max_hull_integrity) {
      percent = (ship.hull_integrity / ship.max_hull_integrity) * 100;
    }
    return percent ?? ship.hull ?? 100;
  }

  _getFuelPercent(ship) {
    const propulsion = ship.systems?.propulsion || {};
    const fuelMass = propulsion.fuel_level ?? ship.fuel_mass ?? ship.fuel ?? 0;
    const fuelCapacity = propulsion.max_fuel ?? ship.fuel_capacity ?? 10000;
    return fuelCapacity > 0 ? (fuelMass / fuelCapacity) * 100 : 0;
  }

  _getAmmoSummary(ship) {
    const weapons = ship.systems?.weapons || ship.weapons || {};
    const torpedoes = weapons.torpedoes || weapons.torpedo || ship.torpedoes || {};
    const pdc = weapons.pdc || weapons.point_defense || ship.pdc || {};

    const torpCount = torpedoes.loaded ?? torpedoes.count ?? torpedoes.ammo ?? 0;
    const torpMax = torpedoes.max ?? torpedoes.capacity ?? 12;
    const pdcCount = pdc.ammo ?? pdc.rounds ?? 0;
    const pdcMax = pdc.max ?? pdc.capacity ?? 1000;

    const torpPercent = torpMax > 0 ? (torpCount / torpMax) * 100 : 100;
    const pdcPercent = pdcMax > 0 ? (pdcCount / pdcMax) * 100 : 100;
    const minPercent = Math.min(torpPercent, pdcPercent);

    const cls = minPercent > 50 ? "nominal" : minPercent > 20 ? "warning" : "critical";

    return { text: `T:${torpCount} P:${pdcCount}`, cls };
  }

  _getSubsystems(ship) {
    const systemsStatus = ship.systems_status || ship.systems || {};
    const result = [];
    const priority = ["propulsion", "sensors", "weapons", "navigation", "power"];

    for (const key of priority) {
      const status = systemsStatus[key];
      if (status !== undefined) {
        result.push({
          name: key.charAt(0).toUpperCase() + key.slice(1),
          status: this._normalizeStatus(status)
        });
      }
    }

    // If none found from systems_status, use defaults
    if (result.length === 0) {
      for (const key of priority) {
        result.push({ name: key.charAt(0).toUpperCase() + key.slice(1), status: "online" });
      }
    }

    return result;
  }

  _normalizeStatus(status) {
    if (typeof status === "boolean") return status ? "online" : "offline";
    if (typeof status === "string") {
      const s = status.toLowerCase();
      if (["on", "active", "ready", "idle", "online"].includes(s)) return "online";
      if (["off", "inactive", "disabled", "offline"].includes(s)) return "offline";
      if (["warning", "degraded", "no_fuel"].includes(s)) return "warning";
      if (["error", "failed", "critical"].includes(s)) return "error";
      return "online";
    }
    if (typeof status === "object" && status !== null) {
      if (status.enabled === false) return "offline";
      if (status.status) {
        const s = String(status.status).toLowerCase();
        if (["error", "failed", "critical"].includes(s)) return "error";
        if (["warning", "degraded", "no_fuel"].includes(s)) return "warning";
        if (["offline", "off", "disabled"].includes(s)) return "offline";
      }
      return "online";
    }
    return "offline";
  }

  _formatSpeed(mps) {
    if (mps >= 1000) return `${(mps / 1000).toFixed(1)} km/s`;
    return `${mps.toFixed(0)} m/s`;
  }
}

customElements.define("status-bar", StatusBar);
export { StatusBar };
