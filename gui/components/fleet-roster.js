/**
 * Fleet Roster Panel
 * Displays fleet ship list with status cards, flagship badge,
 * and controls for creating fleets or adding ships.
 */

import { wsClient } from "../js/ws-client.js";

class FleetRoster extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._pollInterval = null;
    this._fleet = null;
  }

  connectedCallback() {
    this._render();
    this._poll();
    this._pollInterval = setInterval(() => this._poll(), 4000);
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }

  async _poll() {
    try {
      const res = await wsClient.sendShipCommand("fleet_status", {});
      this._fleet = res?.fleet ?? null;
      this._update();
    } catch {
      this._fleet = null;
      this._update();
    }
  }

  _statusColor(status) {
    if (status === "nominal") return "var(--status-nominal, #00ff88)";
    if (status === "damaged") return "var(--status-warning, #ffaa00)";
    return "var(--status-critical, #ff4444)";
  }

  _update() {
    const body = this.shadowRoot.getElementById("body");
    if (!body) return;

    if (!this._fleet) {
      body.innerHTML = `
        <div class="create-form">
          <label class="label">No fleet assigned</label>
          <input id="fleet-name" class="input" type="text"
                 placeholder="Fleet name" maxlength="32" />
          <button class="btn btn-create" id="btn-create">CREATE FLEET</button>
        </div>`;
      body.querySelector("#btn-create").addEventListener("click", () => this._createFleet());
      return;
    }

    const { name, flagship, ships = [], formation } = this._fleet;
    const header = `<div class="fleet-header">
      <span class="fleet-name">${this._esc(name)}</span>
      ${formation ? `<span class="formation">${this._esc(formation)}</span>` : ""}
    </div>`;

    const cards = ships.map(s => {
      const isFlagship = s.id === flagship || s.name === flagship;
      const status = s.status || "nominal";
      const fuel = Math.max(0, Math.min(100, s.fuel ?? 100));
      return `<div class="card${isFlagship ? " flagship" : ""}">
        <div class="card-top">
          <span class="ship-name">${this._esc(s.name || s.id)}</span>
          ${isFlagship ? '<span class="badge">FLAGSHIP</span>' : ""}
        </div>
        <div class="card-row">
          <span class="status" style="color:${this._statusColor(status)}">${status.toUpperCase()}</span>
          <span class="weapons-ready" title="Weapons ready">${s.weapons_ready ? "WPN RDY" : "WPN --"}</span>
        </div>
        <div class="fuel-row">
          <span class="fuel-label">FUEL</span>
          <div class="fuel-track"><div class="fuel-fill" style="width:${fuel}%"></div></div>
          <span class="fuel-pct">${fuel}%</span>
        </div>
      </div>`;
    }).join("");

    body.innerHTML = header + `<div class="ship-list">${cards}</div>
      <button class="btn btn-add" id="btn-add">+ ADD SHIP</button>`;
    body.querySelector("#btn-add").addEventListener("click", () => this._addShip());
  }

  async _createFleet() {
    const input = this.shadowRoot.getElementById("fleet-name");
    const name = input?.value.trim();
    if (!name) return;
    try {
      await wsClient.sendShipCommand("fleet_create", {
        fleet_id: crypto.randomUUID(),
        name,
        ships: [],
      });
      this._poll();
    } catch (err) {
      console.error("fleet_create failed:", err);
    }
  }

  async _addShip() {
    // Prompt kept minimal; a modal could replace this later
    const ship = prompt("Enter ship ID to add:");
    if (!ship) return;
    try {
      await wsClient.sendShipCommand("fleet_add_ship", {
        fleet_id: this._fleet.id ?? this._fleet.fleet_id,
        ship,
      });
      this._poll();
    } catch (err) {
      console.error("fleet_add_ship failed:", err);
    }
  }

  /** Basic HTML escape */
  _esc(str) {
    const d = document.createElement("div");
    d.textContent = str ?? "";
    return d.innerHTML;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; font-family:var(--font-mono, "JetBrains Mono", monospace);
          font-size:0.8rem; color:var(--text-primary, #e0e0e0);
          background:var(--bg-panel, #12121a); padding:12px; box-sizing:border-box; }
        .fleet-header { display:flex; justify-content:space-between; align-items:center;
          margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid var(--border-default, #2a2a3a); }
        .fleet-name { font-size:1rem; font-weight:700; letter-spacing:0.5px; }
        .formation { font-size:0.7rem; color:var(--text-dim, #666680); text-transform:uppercase; }
        .ship-list { overflow-y:auto; max-height:360px; display:flex; flex-direction:column; gap:6px; }
        .card { background:var(--bg-input, #1a1a2e); border:1px solid var(--border-default, #2a2a3a);
          border-radius:4px; padding:8px 10px; }
        .card.flagship { border-color:#c8a415; box-shadow:0 0 4px rgba(200,164,21,0.3); }
        .card-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }
        .ship-name { font-weight:600; }
        .badge { font-size:0.6rem; font-weight:700; color:#c8a415;
          border:1px solid #c8a415; border-radius:2px; padding:1px 4px; }
        .card-row { display:flex; justify-content:space-between; font-size:0.7rem; margin-bottom:4px; }
        .status { font-weight:600; }
        .weapons-ready { color:var(--text-dim, #666680); }
        .fuel-row { display:flex; align-items:center; gap:6px; font-size:0.65rem; }
        .fuel-label { color:var(--text-secondary, #a0a0b0); width:30px; }
        .fuel-track { flex:1; height:4px; background:var(--border-default, #2a2a3a); border-radius:2px; overflow:hidden; }
        .fuel-fill { height:100%; background:var(--status-info, #4488ff); border-radius:2px; transition:width 0.4s; }
        .fuel-pct { width:30px; text-align:right; color:var(--text-dim, #666680); }
        .btn { display:block; width:100%; padding:8px; margin-top:8px; border:1px solid var(--border-default, #2a2a3a);
          border-radius:4px; background:var(--bg-input, #1a1a2e); color:var(--text-primary, #e0e0e0);
          font-family:inherit; font-size:0.75rem; cursor:pointer; text-transform:uppercase; letter-spacing:1px; }
        .btn:hover { border-color:var(--status-info, #4488ff); }
        .btn-create { border-color:var(--status-nominal, #00ff88); color:var(--status-nominal, #00ff88); }
        .btn-create:hover { background:#00ff8818; }
        .create-form { display:flex; flex-direction:column; gap:8px; }
        .label { color:var(--text-secondary, #a0a0b0); font-size:0.75rem; text-transform:uppercase; }
        .input { background:var(--bg-input, #1a1a2e); border:1px solid var(--border-default, #2a2a3a);
          border-radius:4px; padding:6px 8px; color:var(--text-primary, #e0e0e0);
          font-family:inherit; font-size:0.8rem; outline:none; }
        .input:focus { border-color:var(--status-info, #4488ff); }
      </style>
      <div id="body"></div>`;
  }
}

customElements.define("fleet-roster", FleetRoster);
