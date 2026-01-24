/**
 * Weapons Status Panel
 * Displays torpedoes, PDC, fire control status
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
          padding: 16px;
        }

        .weapon-section {
          margin-bottom: 16px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
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
        }

        .weapon-status {
          font-size: 0.7rem;
          padding: 2px 8px;
          border-radius: 4px;
          text-transform: uppercase;
          font-weight: 600;
        }

        .weapon-status.ready {
          background: rgba(0, 255, 136, 0.2);
          color: var(--status-nominal, #00ff88);
        }

        .weapon-status.reloading {
          background: rgba(255, 170, 0, 0.2);
          color: var(--status-warning, #ffaa00);
        }

        .weapon-status.firing {
          background: rgba(255, 68, 68, 0.2);
          color: var(--status-critical, #ff4444);
          animation: pulse 0.5s ease-in-out infinite;
        }

        .weapon-status.tracking {
          background: rgba(0, 170, 255, 0.2);
          color: var(--status-info, #00aaff);
        }

        .weapon-status.offline {
          background: rgba(85, 85, 102, 0.2);
          color: var(--text-dim, #555566);
        }

        .weapon-status.empty {
          background: rgba(255, 68, 68, 0.2);
          color: var(--status-critical, #ff4444);
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
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
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for weapons data...</div>';
      return;
    }

    // Extract weapons data - handle various structures
    const torpedoes = this._getTorpedoData(weapons, ship);
    const pdc = this._getPDCData(weapons, ship);
    const fireControl = this._getFireControlMode(weapons, ship);

    content.innerHTML = `
      ${this._renderWeaponSection("TORPEDOES", torpedoes)}
      ${this._renderWeaponSection("PDC (Point Defense)", pdc)}
      ${this._renderFireControl(fireControl)}
    `;
  }

  _getTorpedoData(weapons, ship) {
    const torpedoData = weapons.torpedoes || weapons.torpedo || ship.torpedoes || {};
    return {
      loaded: torpedoData.loaded ?? torpedoData.count ?? torpedoData.ammo ?? 10,
      max: torpedoData.max ?? torpedoData.capacity ?? 12,
      status: torpedoData.status || "ready",
      inFlight: torpedoData.in_flight ?? torpedoData.active ?? 0,
      reloadTime: torpedoData.reload_time ?? null
    };
  }

  _getPDCData(weapons, ship) {
    const pdcData = weapons.pdc || weapons.point_defense || ship.pdc || {};
    return {
      ammo: pdcData.ammo ?? pdcData.rounds ?? 980,
      max: pdcData.max ?? pdcData.capacity ?? 1000,
      status: pdcData.status || "ready",
      targetsEngaged: pdcData.targets_engaged ?? pdcData.tracking ?? 0,
      tracking: pdcData.tracking_count ?? pdcData.targets ?? 0
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

  _renderWeaponSection(name, data) {
    const statusClass = this._getStatusClass(data.status, data.loaded, data.ammo);
    const percent = data.max > 0 ?
      ((data.loaded ?? data.ammo ?? 0) / data.max) * 100 : 0;
    const barClass = percent > 50 ? "nominal" : percent > 20 ? "warning" : "critical";

    let detailsHtml = "";

    // Torpedoes-specific details
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

    // PDC-specific details
    if (data.targetsEngaged !== undefined) {
      detailsHtml = `
        <div class="weapon-details">
          <div class="detail-row">
            <span class="detail-label">Targets Engaged</span>
            <span class="detail-value">${data.targetsEngaged}</span>
          </div>
          ${data.tracking ? `
            <div class="detail-row">
              <span class="detail-label">Tracking</span>
              <span class="detail-value">${data.tracking}</span>
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
            <span class="ammo-count">${current}/${data.max}</span>
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
