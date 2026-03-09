/**
 * Fleet Fire Control
 * Coordinate fleet-level target designation, fire mode, and weapons release.
 * All commands route through the server via wsClient.sendShipCommand.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

const FIRE_MODES = { VOLLEY: "volley", INDEPENDENT: "independent" };
const STATUS = { FREE: "WEAPONS FREE", HOLD: "WEAPONS HOLD", FIRING: "FIRING" };

class FleetFireControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._fireMode = FIRE_MODES.VOLLEY;
    this._status = STATUS.HOLD;
    this._currentTarget = null;
  }

  connectedCallback() {
    this._render();
    this._unsubscribe = stateManager.subscribe("*", () => this._updateDisplay());
    this._setupEvents();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
  }

  get fleetId() {
    return this.getAttribute("fleet-id") || "default";
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--font-mono, "JetBrains Mono", monospace); }
        .panel { background: var(--bg-panel, #12121a); border: 1px solid var(--border-default, #2a2a3a);
                 border-radius: 4px; padding: 12px; }
        .section { margin-bottom: 12px; }
        .section:last-child { margin-bottom: 0; }
        .label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.5px;
                 color: var(--text-dim, #666680); margin-bottom: 6px; }
        .target-row { display: flex; gap: 8px; align-items: center; }
        select { flex: 1; background: var(--bg-input, #1a1a2e); color: var(--text-primary, #e0e0e0);
                 border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px;
                 padding: 6px 8px; font-family: inherit; font-size: 0.75rem; }
        button { font-family: inherit; font-size: 0.7rem; border: none; border-radius: 3px;
                 padding: 6px 12px; cursor: pointer; text-transform: uppercase; letter-spacing: 0.3px; }
        .btn-designate { background: var(--status-info, #4488ff); color: #fff; }
        .btn-designate:hover { filter: brightness(1.2); }
        .current-target { display: flex; justify-content: space-between; align-items: center;
                          padding: 6px 8px; background: var(--bg-input, #1a1a2e); border-radius: 3px;
                          font-size: 0.75rem; color: var(--text-primary, #e0e0e0); min-height: 1.4em; }
        .target-range { color: var(--text-secondary, #a0a0b0); font-size: 0.65rem; }
        .no-target { color: var(--text-dim, #666680); font-style: italic; }
        .mode-toggle { display: flex; gap: 4px; }
        .mode-btn { flex: 1; padding: 8px; text-align: center; background: var(--bg-input, #1a1a2e);
                    color: var(--text-dim, #666680); border: 1px solid var(--border-default, #2a2a3a); }
        .mode-btn.active { color: var(--status-info, #4488ff);
                           border-color: var(--status-info, #4488ff); }
        .fire-row { display: flex; gap: 8px; }
        .btn-fire { flex: 2; padding: 12px; background: var(--status-critical, #ff4444); color: #fff;
                    font-size: 0.85rem; font-weight: 700; letter-spacing: 1px; }
        .btn-fire:hover { filter: brightness(1.2); }
        .btn-fire:disabled { opacity: 0.4; cursor: not-allowed; filter: none; }
        .btn-cease { flex: 1; padding: 12px; background: var(--bg-input, #1a1a2e);
                     color: var(--status-warning, #ffaa00);
                     border: 1px solid var(--status-warning, #ffaa00); font-size: 0.75rem; }
        .btn-cease:hover { background: var(--status-warning, #ffaa00); color: #000; }
        .status-indicator { text-align: center; padding: 4px; font-size: 0.7rem; font-weight: 600;
                            letter-spacing: 0.5px; border-radius: 3px; }
        .status-hold { color: var(--text-dim, #666680); }
        .status-free { color: var(--status-nominal, #00ff88); }
        .status-firing { color: var(--status-critical, #ff4444); animation: pulse 1s infinite; }
        @keyframes pulse { 50% { opacity: 0.6; } }
      </style>
      <div class="panel">
        <div class="section">
          <div class="label">Target Designation</div>
          <div class="target-row">
            <select id="contact-select"><option value="">-- select contact --</option></select>
            <button class="btn-designate" id="btn-designate">Designate</button>
          </div>
        </div>
        <div class="section">
          <div class="label">Current Target</div>
          <div class="current-target" id="current-target">
            <span class="no-target">No target designated</span>
          </div>
        </div>
        <div class="section">
          <div class="label">Fire Mode</div>
          <div class="mode-toggle">
            <button class="mode-btn active" id="mode-volley" data-mode="volley">Volley</button>
            <button class="mode-btn" id="mode-independent" data-mode="independent">Independent</button>
          </div>
        </div>
        <div class="section">
          <div class="fire-row">
            <button class="btn-fire" id="btn-fire" disabled>Fire</button>
            <button class="btn-cease" id="btn-cease">Cease Fire</button>
          </div>
        </div>
        <div class="status-indicator status-hold" id="status">${STATUS.HOLD}</div>
      </div>`;
  }

  _setupEvents() {
    const root = this.shadowRoot;
    root.getElementById("btn-designate").addEventListener("click", () => this._designate());
    root.getElementById("btn-fire").addEventListener("click", () => this._fire());
    root.getElementById("btn-cease").addEventListener("click", () => this._ceaseFire());
    root.querySelectorAll(".mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => this._setMode(btn.dataset.mode));
    });
  }

  _updateDisplay() {
    const contacts = stateManager.getContacts();
    const select = this.shadowRoot.getElementById("contact-select");
    const current = select.value;
    select.innerHTML = `<option value="">-- select contact --</option>` +
      contacts.map((c) => {
        const id = c.id || c.name;
        return `<option value="${id}"${id === current ? " selected" : ""}>${c.name || id}</option>`;
      }).join("");

    // Update current target display with latest contact data
    if (this._currentTarget) {
      const match = contacts.find((c) => (c.id || c.name) === this._currentTarget);
      const el = this.shadowRoot.getElementById("current-target");
      if (match) {
        const range = match.range != null ? `${(match.range / 1000).toFixed(1)} km` : "---";
        el.innerHTML = `<span>${match.name || match.id}</span><span class="target-range">${range}</span>`;
      }
    }
    this.shadowRoot.getElementById("btn-fire").disabled = !this._currentTarget;
  }

  _setMode(mode) {
    this._fireMode = mode;
    this.shadowRoot.querySelectorAll(".mode-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
  }

  _setStatus(status) {
    this._status = status;
    const el = this.shadowRoot.getElementById("status");
    el.textContent = status;
    el.className = "status-indicator " +
      (status === STATUS.FIRING ? "status-firing" : status === STATUS.FREE ? "status-free" : "status-hold");
  }

  async _designate() {
    const contactId = this.shadowRoot.getElementById("contact-select").value;
    if (!contactId) return;
    await wsClient.sendShipCommand("fleet_target", { fleet_id: this.fleetId, contact: contactId });
    this._currentTarget = contactId;
    this._setStatus(STATUS.FREE);
    this._updateDisplay();
  }

  async _fire() {
    if (!this._currentTarget) return;
    const volley = this._fireMode === FIRE_MODES.VOLLEY;
    await wsClient.sendShipCommand("fleet_fire", { fleet_id: this.fleetId, volley });
    this._setStatus(STATUS.FIRING);
  }

  async _ceaseFire() {
    await wsClient.sendShipCommand("fleet_cease_fire", { fleet_id: this.fleetId });
    this._setStatus(this._currentTarget ? STATUS.FREE : STATUS.HOLD);
  }
}

customElements.define("fleet-fire-control", FleetFireControl);
