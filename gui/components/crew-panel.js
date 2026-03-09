/**
 * Crew Panel Component
 * Displays crew status (fatigue, stress, health, skills) and management actions.
 * Polls crew_status every 5s. Captain station gets promote/demote/transfer controls.
 */

import { wsClient } from "../js/ws-client.js";

const SKILL_LEVEL_NAMES = {
  1: "NOV", 2: "TRN", 3: "CMP", 4: "PRO", 5: "EXP", 6: "MST"
};

const STATIONS = ["HELM", "TACTICAL", "ENGINEERING", "SENSORS", "COMMS", "CAPTAIN"];

class CrewPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._pollTimer = null;
    this._crew = [];
  }

  connectedCallback() {
    this._renderShell();
    this._poll();
    this._pollTimer = setInterval(() => this._poll(), 5000);
  }

  disconnectedCallback() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  async _poll() {
    try {
      const res = await wsClient.sendShipCommand("crew_status");
      this._crew = res?.crew || res || [];
      this._updateDisplay();
    } catch (e) {
      console.error("crew_status poll failed:", e);
    }
  }

  get _isCaptain() {
    return window.flaxosApp?.stationManager?.currentStation === "CAPTAIN";
  }

  _barColor(value, invert = false) {
    // invert=true means high value is bad (fatigue, stress)
    const v = invert ? value : 1 - value;
    if (v > 0.8) return "critical";
    if (v > 0.5) return "warning";
    return "nominal";
  }

  _topSkills(skills) {
    if (!skills || typeof skills !== "object") return [];
    return Object.entries(skills)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
          padding: 12px;
        }
        .crew-list { display: flex; flex-direction: column; gap: 10px; }
        .crew-card {
          background: var(--bg-input, #1a1a2e);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          padding: 10px 12px;
        }
        .card-header {
          display: flex; justify-content: space-between; align-items: center;
          margin-bottom: 8px;
        }
        .crew-name { font-weight: 600; font-size: 0.85rem; }
        .crew-role { color: var(--text-secondary, #a0a0b0); font-size: 0.7rem; text-transform: uppercase; }
        .station-badge {
          font-size: 0.65rem; padding: 2px 6px; border-radius: 3px;
          background: var(--status-info, #4488ff); color: #fff;
        }
        .bar-row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
        .bar-label { width: 52px; font-size: 0.65rem; color: var(--text-dim, #666680); text-transform: uppercase; }
        .bar-track {
          flex: 1; height: 10px; background: rgba(0,0,0,0.3); border-radius: 3px; overflow: hidden;
        }
        .bar-fill {
          height: 100%; transition: width 0.3s ease;
        }
        .bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .bar-fill.critical { background: var(--status-critical, #ff4444); }
        .bar-val { width: 32px; text-align: right; font-size: 0.65rem; color: var(--text-secondary, #a0a0b0); }
        .skills-row { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
        .skill-badge {
          font-size: 0.6rem; padding: 1px 5px; border-radius: 3px;
          background: rgba(255,255,255,0.06); color: var(--text-secondary, #a0a0b0);
        }
        .efficiency {
          margin-top: 6px; font-size: 0.7rem; color: var(--text-dim, #666680);
        }
        .eff-value { color: var(--status-nominal, #00ff88); font-weight: 600; }
        .actions { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
        button {
          font-family: inherit; font-size: 0.65rem; padding: 3px 8px;
          border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px;
          background: var(--bg-panel, #12121a); color: var(--text-primary, #e0e0e0);
          cursor: pointer;
        }
        button:hover { border-color: var(--status-info, #4488ff); }
        button.rest { border-color: var(--status-warning, #ffaa00); }
        select {
          font-family: inherit; font-size: 0.65rem; padding: 2px 4px;
          background: var(--bg-panel, #12121a); color: var(--text-primary, #e0e0e0);
          border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px;
        }
        .captain-section {
          margin-top: 6px; padding-top: 6px;
          border-top: 1px dashed var(--border-default, #2a2a3a);
        }
        .captain-label { font-size: 0.6rem; color: var(--text-dim, #666680); margin-bottom: 4px; }
        .empty-state {
          text-align: center; color: var(--text-dim, #666680);
          padding: 24px; font-style: italic;
        }
      </style>
      <div id="content"><div class="empty-state">Polling crew status...</div></div>
    `;
  }

  _updateDisplay() {
    const el = this.shadowRoot.getElementById("content");
    if (!this._crew.length) {
      el.innerHTML = '<div class="empty-state">No crew data available.</div>';
      return;
    }
    el.innerHTML = `<div class="crew-list">${this._crew.map(c => this._renderCard(c)).join("")}</div>`;
    this._bindActions();
  }

  _renderCard(c) {
    const top = this._topSkills(c.skills);
    const effPct = ((c.efficiency ?? 0) * 100).toFixed(0);
    const isCpt = this._isCaptain;
    return `
      <div class="crew-card" data-crew-id="${c.crew_id}">
        <div class="card-header">
          <div>
            <span class="crew-name">${c.name}</span>
            <span class="crew-role">${c.role || "---"}</span>
          </div>
          ${c.station_assignment ? `<span class="station-badge">${c.station_assignment}</span>` : ""}
        </div>
        ${this._renderBar("Fatigue", c.fatigue, true)}
        ${this._renderBar("Stress", c.stress, true)}
        ${this._renderBar("Health", c.health, false)}
        <div class="skills-row">
          ${top.map(([sk, lv]) => `<span class="skill-badge">${sk} ${SKILL_LEVEL_NAMES[lv] || lv}</span>`).join("")}
        </div>
        <div class="efficiency">EFF <span class="eff-value">${effPct}%</span></div>
        <div class="actions">
          <button class="rest" data-action="rest" data-id="${c.crew_id}">REST</button>
        </div>
        ${isCpt ? this._renderCaptainControls(c) : ""}
      </div>`;
  }

  _renderBar(label, value, invert) {
    const v = Math.max(0, Math.min(1, value ?? 0));
    const cls = this._barColor(v, invert);
    return `
      <div class="bar-row">
        <span class="bar-label">${label}</span>
        <div class="bar-track"><div class="bar-fill ${cls}" style="width:${(v * 100).toFixed(0)}%"></div></div>
        <span class="bar-val">${(v * 100).toFixed(0)}%</span>
      </div>`;
  }

  _renderCaptainControls(c) {
    const opts = STATIONS.map(s =>
      `<option value="${s}" ${c.station_assignment === s ? "selected" : ""}>${s}</option>`
    ).join("");
    return `
      <div class="captain-section">
        <div class="captain-label">CAPTAIN CONTROLS</div>
        <div class="actions">
          <button data-action="promote" data-id="${c.crew_id}">PROMOTE</button>
          <button data-action="demote" data-id="${c.crew_id}">DEMOTE</button>
          <select data-action="transfer" data-id="${c.crew_id}">${opts}</select>
        </div>
      </div>`;
  }

  _bindActions() {
    const root = this.shadowRoot;
    root.querySelectorAll("button[data-action]").forEach(btn => {
      btn.addEventListener("click", (e) => this._handleAction(e));
    });
    root.querySelectorAll("select[data-action='transfer']").forEach(sel => {
      sel.addEventListener("change", (e) => this._handleTransfer(e));
    });
  }

  async _handleAction(e) {
    const action = e.target.dataset.action;
    const id = e.target.dataset.id;
    try {
      if (action === "rest") {
        await wsClient.sendShipCommand("crew_rest", { crew_id: id });
      } else if (action === "promote") {
        await wsClient.sendShipCommand("promote_to_officer", { target_client: id });
      } else if (action === "demote") {
        await wsClient.sendShipCommand("demote_from_officer", { target_client: id });
      }
      this._poll();
    } catch (err) {
      console.error(`crew action ${action} failed:`, err);
    }
  }

  async _handleTransfer(e) {
    const id = e.target.dataset.id;
    const station = e.target.value;
    try {
      await wsClient.sendShipCommand("transfer_station", { target_client: id, station });
      this._poll();
    } catch (err) {
      console.error("transfer_station failed:", err);
    }
  }
}

customElements.define("crew-panel", CrewPanel);
export { CrewPanel };
