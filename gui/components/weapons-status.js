/**
 * Weapons Status Panel
 * Displays truth weapons (railguns, PDCs), legacy torpedoes, and fire control status.
 * Shows ammo counts, ammo mass, reload state, and mass impact prominently.
 */

import { stateManager } from "../js/state-manager.js";

class WeaponsStatus extends HTMLElement {
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
          font-size: 0.8rem;
          padding: 0;
        }

        .weapon-section {
          margin-bottom: 16px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          /* Domain-weapons left-border accent */
          border-left: 2px solid var(--domain-weapons, #cc4444);
          padding-left: 12px;
        }

        .weapon-section:last-child {
          margin-bottom: 0;
          padding-bottom: 0;
          border-bottom: none;
        }

        .weapon-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
        }

        .weapon-name {
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          text-transform: uppercase;
          font-size: 0.75rem;
          letter-spacing: 0.08em;
        }

        .weapon-status {
          font-size: 0.65rem;
          padding: 2px 8px;
          border-radius: 4px;
          text-transform: uppercase;
          font-weight: 600;
        }

        /* READY: glowing dot border instead of flat bg */
        .weapon-status.ready {
          background: transparent;
          color: var(--status-nominal, #00ff88);
          border: 1px solid var(--status-nominal, #00ff88);
          box-shadow: 0 0 6px rgba(0, 255, 136, 0.4);
        }

        .weapon-status.reloading {
          background: rgba(255, 170, 0, 0.15);
          color: var(--status-warning, #ffaa00);
          border: 1px solid rgba(255, 170, 0, 0.3);
          animation: pulse 1s ease-in-out infinite;
        }

        .weapon-status.firing {
          background: rgba(255, 68, 68, 0.2);
          color: var(--status-critical, #ff4444);
          animation: pulse 0.5s ease-in-out infinite;
        }

        .weapon-status.tracking {
          background: rgba(0, 170, 255, 0.15);
          color: var(--status-info, #00aaff);
          border: 1px solid rgba(0, 170, 255, 0.3);
        }

        .weapon-status.offline {
          background: rgba(85, 85, 102, 0.2);
          color: var(--text-dim, #555566);
        }

        /* EMPTY: irregular flicker using steps() timing */
        .weapon-status.empty {
          background: rgba(255, 68, 68, 0.15);
          color: var(--status-critical, #ff4444);
          border: 1px solid rgba(255, 68, 68, 0.3);
          animation: ammo-empty 1.8s steps(1) infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        /* Irregular flicker for empty weapons — not smooth, mechanical */
        @keyframes ammo-empty {
          0%, 89%, 91%, 100% { opacity: 1; }
          90%                 { opacity: 0.3; }
        }

        .ammo-bar {
          margin-bottom: 8px;
        }

        .ammo-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 4px;
          font-size: 0.75rem;
        }

        .ammo-label {
          color: var(--text-secondary, #888899);
        }

        .ammo-count {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }

        /* Current ammo in larger font, max in smaller */
        .ammo-current {
          font-size: 0.9rem;
          font-weight: 700;
        }

        .ammo-max {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
        }

        .ammo-count.critical {
          color: var(--status-critical, #ff4444);
        }

        .ammo-count.warning {
          color: var(--status-warning, #ffaa00);
        }

        .bar {
          height: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 6px;
          overflow: hidden;
        }

        .bar-fill {
          height: 100%;
          transition: width 0.3s ease;
        }

        .bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .bar-fill.critical { background: var(--status-critical, #ff4444); }

        .weapon-details {
          display: grid;
          gap: 4px;
          font-size: 0.75rem;
        }

        .detail-row {
          display: flex;
          justify-content: space-between;
        }

        .detail-label {
          color: var(--text-dim, #555566);
        }

        .detail-value {
          color: var(--text-secondary, #888899);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .detail-value.warning {
          color: var(--status-warning, #ffaa00);
        }

        .detail-value.critical {
          color: var(--status-critical, #ff4444);
        }

        .ammo-mass-summary {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
          margin-bottom: 16px;
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .ammo-mass-label {
          color: var(--text-dim, #555566);
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          font-weight: 600;
        }

        .ammo-mass-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--status-info, #00aaff);
          font-size: 0.85rem;
          font-weight: 600;
        }

        .fire-control {
          display: flex;
          gap: 8px;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }

        .fire-mode {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          border-radius: 6px;
          cursor: default;
        }

        .fire-mode.active {
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid var(--status-nominal, #00ff88);
        }

        .fire-mode.inactive {
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .mode-indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .mode-indicator.active {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 6px var(--status-nominal, #00ff88);
        }

        .mode-indicator.inactive {
          background: var(--status-offline, #555566);
        }

        .mode-label {
          font-size: 0.75rem;
          font-weight: 600;
        }

        .mode-label.active {
          color: var(--status-nominal, #00ff88);
        }

        .mode-label.inactive {
          color: var(--text-dim, #555566);
        }

        .reload-bar {
          margin-top: 4px;
        }

        .reload-bar .bar-fill {
          background: linear-gradient(
            90deg,
            var(--status-warning, #ffaa00) 0%,
            rgba(255, 170, 0, 0.6) 100%
          );
          transition: width 0.3s linear;
          box-shadow: 0 0 4px rgba(255, 170, 0, 0.3);
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for weapons data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const weapons = stateManager.getWeapons();
    const combat = stateManager.getCombat();
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for weapons data...</div>';
      return;
    }

    // Get truth weapons from combat system or weapons telemetry
    const truthWeapons = weapons?.truth_weapons || combat?.truth_weapons || {};
    const totalAmmoMass = weapons?.total_ammo_mass ?? combat?.total_ammo_mass ?? 0;

    // Get legacy weapon data
    const torpedoes = this._getTorpedoData(weapons, ship);
    const fireControl = this._getFireControlMode(weapons, ship);

    // Build truth weapon sections
    let truthWeaponHtml = "";
    const railguns = [];
    const pdcs = [];

    for (const [mountId, wState] of Object.entries(truthWeapons)) {
      if (mountId.startsWith("railgun")) {
        railguns.push({ mountId, ...wState });
      } else if (mountId.startsWith("pdc")) {
        pdcs.push({ mountId, ...wState });
      }
    }

    if (railguns.length > 0) {
      truthWeaponHtml += railguns.map(w => this._renderTruthWeapon(w)).join("");
    }
    if (pdcs.length > 0) {
      truthWeaponHtml += pdcs.map(w => this._renderTruthWeapon(w)).join("");
    }

    // Ammo mass summary
    const ammoMassHtml = totalAmmoMass > 0 ? `
      <div class="ammo-mass-summary">
        <span class="ammo-mass-label">Total Ammo Mass</span>
        <span class="ammo-mass-value">${totalAmmoMass.toFixed(1)} kg</span>
      </div>
    ` : "";

    content.innerHTML = `
      ${ammoMassHtml}
      ${truthWeaponHtml}
      ${torpedoes.max > 0 ? this._renderLegacyWeapon("TORPEDOES", torpedoes) : ""}
      ${this._renderFireControl(fireControl)}
    `;
  }

  _renderTruthWeapon(w) {
    const ammo = w.ammo ?? 0;
    const capacity = w.ammo_capacity ?? 0;
    const percent = capacity > 0 ? (ammo / capacity) * 100 : 0;
    const barClass = percent > 50 ? "nominal" : percent > 20 ? "warning" : "critical";
    const countClass = percent > 20 ? "" : percent > 0 ? "warning" : "critical";

    let statusClass = "ready";
    let statusText = "READY";
    if (ammo === 0) {
      statusClass = "empty";
      statusText = "EMPTY";
    } else if (w.reloading) {
      statusClass = "reloading";
      statusText = "RELOADING";
    } else if (!w.enabled) {
      statusClass = "offline";
      statusText = "OFFLINE";
    } else if (w.solution?.ready_to_fire) {
      statusClass = "firing";
      statusText = "SOLUTION";
    } else if (w.solution?.tracking) {
      statusClass = "tracking";
      statusText = "TRACKING";
    }

    const ammoMass = w.ammo_mass ?? (ammo * (w.mass_per_round || 0));
    const massPerRound = w.mass_per_round || 0;

    let detailsHtml = `
      <div class="weapon-details">
        <div class="detail-row">
          <span class="detail-label">Ammo Mass</span>
          <span class="detail-value">${ammoMass.toFixed(1)} kg</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Per Round</span>
          <span class="detail-value">${massPerRound >= 1 ? massPerRound.toFixed(1) + " kg" : (massPerRound * 1000).toFixed(0) + " g"}</span>
        </div>
    `;

    if (w.solution && w.solution.valid) {
      const range = w.solution.range || 0;
      const rangeKm = (range / 1000).toFixed(1);
      detailsHtml += `
        <div class="detail-row">
          <span class="detail-label">Range</span>
          <span class="detail-value">${rangeKm} km</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Hit Prob</span>
          <span class="detail-value">${(w.solution.hit_probability * 100).toFixed(0)}%</span>
        </div>
      `;
    }

    detailsHtml += "</div>";

    // Reload progress bar
    let reloadHtml = "";
    if (w.reloading) {
      const reloadPct = (w.reload_progress || 0) * 100;
      reloadHtml = `
        <div class="reload-bar">
          <div class="ammo-header">
            <span class="ammo-label">Reload</span>
            <span class="ammo-count warning">${reloadPct.toFixed(0)}%</span>
          </div>
          <div class="bar">
            <div class="bar-fill warning" style="width: ${reloadPct}%"></div>
          </div>
        </div>
      `;
    }

    return `
      <div class="weapon-section">
        <div class="weapon-header">
          <span class="weapon-name">${w.name || w.mountId}</span>
          <span class="weapon-status ${statusClass}">${statusText}</span>
        </div>
        <div class="ammo-bar">
          <div class="ammo-header">
            <span class="ammo-label">Ammo</span>
            <span class="ammo-count ${countClass}"><span class="ammo-current">${ammo}</span><span class="ammo-max">/${capacity}</span></span>
          </div>
          <div class="bar">
            <div class="bar-fill ${barClass}" style="width: ${percent}%"></div>
          </div>
        </div>
        ${reloadHtml}
        ${detailsHtml}
      </div>
    `;
  }

  _getTorpedoData(weapons, ship) {
    const torpedoData = weapons.torpedoes || weapons.torpedo || ship.torpedoes || {};
    // Also check legacy weapons list
    const legacyWeapons = weapons.weapons || [];
    if (Array.isArray(legacyWeapons)) {
      const torpedo = legacyWeapons.find(w => (w.name || "").toLowerCase().includes("torpedo"));
      if (torpedo) {
        return {
          loaded: torpedo.ammo ?? 0,
          max: torpedo.ammo_capacity ?? torpedo.ammo ?? 0,
          status: torpedo.can_fire ? "ready" : "reloading",
          inFlight: 0,
          reloadTime: null,
        };
      }
    }
    return {
      loaded: torpedoData.loaded ?? torpedoData.count ?? torpedoData.ammo ?? 0,
      max: torpedoData.max ?? torpedoData.capacity ?? 0,
      status: torpedoData.status || "ready",
      inFlight: torpedoData.in_flight ?? torpedoData.active ?? 0,
      reloadTime: torpedoData.reload_time ?? null
    };
  }

  _getFireControlMode(weapons, ship) {
    const mode = weapons.fire_control_mode || weapons.fire_mode ||
                 ship.fire_control || ship.weapon_mode || "hold";
    return {
      weaponsFree: mode === "free" || mode === "weapons_free" || mode === "auto",
      weaponsHold: mode === "hold" || mode === "weapons_hold" || mode === "manual"
    };
  }

  _renderLegacyWeapon(name, data) {
    const statusClass = this._getStatusClass(data.status, data.loaded, data.ammo);
    const percent = data.max > 0 ?
      ((data.loaded ?? data.ammo ?? 0) / data.max) * 100 : 0;
    const barClass = percent > 50 ? "nominal" : percent > 20 ? "warning" : "critical";

    let detailsHtml = "";

    if (data.inFlight !== undefined) {
      detailsHtml = `
        <div class="weapon-details">
          <div class="detail-row">
            <span class="detail-label">In Flight</span>
            <span class="detail-value">${data.inFlight}</span>
          </div>
          ${data.reloadTime ? `
            <div class="detail-row">
              <span class="detail-label">Reload</span>
              <span class="detail-value">${data.reloadTime}s</span>
            </div>
          ` : ''}
        </div>
      `;
    }

    const current = data.loaded ?? data.ammo ?? 0;

    return `
      <div class="weapon-section">
        <div class="weapon-header">
          <span class="weapon-name">${name}</span>
          <span class="weapon-status ${statusClass}">${data.status.toUpperCase()}</span>
        </div>
        <div class="ammo-bar">
          <div class="ammo-header">
            <span class="ammo-label">${data.loaded !== undefined ? 'Loaded' : 'Ammo'}</span>
            <span class="ammo-count"><span class="ammo-current">${current}</span><span class="ammo-max">/${data.max}</span></span>
          </div>
          <div class="bar">
            <div class="bar-fill ${barClass}" style="width: ${percent}%"></div>
          </div>
        </div>
        ${detailsHtml}
      </div>
    `;
  }

  _renderFireControl(fireControl) {
    return `
      <div class="weapon-section">
        <div class="weapon-header">
          <span class="weapon-name">FIRE CONTROL</span>
        </div>
        <div class="fire-control">
          <div class="fire-mode ${fireControl.weaponsFree ? 'active' : 'inactive'}">
            <span class="mode-indicator ${fireControl.weaponsFree ? 'active' : 'inactive'}"></span>
            <span class="mode-label ${fireControl.weaponsFree ? 'active' : 'inactive'}">WEAPONS FREE</span>
          </div>
          <div class="fire-mode ${fireControl.weaponsHold ? 'active' : 'inactive'}">
            <span class="mode-indicator ${fireControl.weaponsHold ? 'active' : 'inactive'}"></span>
            <span class="mode-label ${fireControl.weaponsHold ? 'active' : 'inactive'}">WEAPONS HOLD</span>
          </div>
        </div>
      </div>
    `;
  }

  _getStatusClass(status, loaded, ammo) {
    const count = loaded ?? ammo ?? 0;
    if (count === 0) return "empty";

    const s = (status || "").toLowerCase();
    if (s === "ready" || s === "online") return "ready";
    if (s === "reloading" || s === "loading") return "reloading";
    if (s === "firing" || s === "active") return "firing";
    if (s === "tracking") return "tracking";
    if (s === "offline" || s === "disabled") return "offline";
    return "ready";
  }
}

customElements.define("weapons-status", WeaponsStatus);
export { WeaponsStatus };
