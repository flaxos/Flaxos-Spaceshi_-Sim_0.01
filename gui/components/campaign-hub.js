/**
 * Campaign Hub -- between-mission management screen.
 *
 * Shows ship status, crew roster, credits, faction reputation,
 * available missions, and campaign controls.  Communicates with the
 * server via wsClient.send() (meta-level commands, not ship-scoped).
 */

import { wsClient } from "../js/ws-client.js";

class CampaignHub extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._campaign = null;
    this._scenarios = [];
    this._pollInterval = null;
  }

  connectedCallback() {
    this.render();
    this._fetchStatus();
    this._pollInterval = setInterval(() => this._fetchStatus(), 3000);
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }

  async _fetchStatus() {
    try {
      const res = await wsClient.send("campaign_status", {});
      if (res && res.ok) {
        this._campaign = res.campaign;
        this._updateDisplay();
      } else {
        this._campaign = null;
        this._updateDisplay();
      }
    } catch {
      /* server may not have campaign active */
    }
  }

  async _newCampaign() {
    const res = await wsClient.send("campaign_new", {});
    if (res && res.ok) {
      this._campaign = res.campaign;
      this._updateDisplay();
    }
  }

  async _saveCampaign() {
    const res = await wsClient.send("campaign_save", {});
    if (res && res.ok) {
      this._showToast("Campaign saved");
    } else {
      this._showToast("Save failed: " + (res?.message || "unknown"));
    }
  }

  async _loadCampaign() {
    const res = await wsClient.send("campaign_load", {});
    if (res && res.ok) {
      this._campaign = res.campaign;
      this._updateDisplay();
      this._showToast("Campaign loaded");
    } else {
      this._showToast("Load failed: " + (res?.message || "unknown"));
    }
  }

  async _startMission(scenarioId) {
    const res = await wsClient.send("load_scenario", { scenario: scenarioId });
    if (res && res.ok) {
      this._showToast("Mission starting: " + scenarioId);
      document.dispatchEvent(
        new CustomEvent("scenario-loaded", { detail: res })
      );
    } else {
      this._showToast("Failed to load: " + (res?.error || "unknown"));
    }
  }

  _showToast(msg) {
    const el = this.shadowRoot.getElementById("toast");
    if (el) {
      el.textContent = msg;
      el.classList.add("visible");
      setTimeout(() => el.classList.remove("visible"), 2500);
    }
  }

  _updateDisplay() {
    const c = this._campaign;
    const container = this.shadowRoot.getElementById("content");
    if (!container) return;

    if (!c) {
      container.innerHTML = `
        <div class="empty-state">
          <p>No active campaign.</p>
          <button id="btn-new">NEW CAMPAIGN</button>
          <button id="btn-load">LOAD CAMPAIGN</button>
        </div>`;
      this.shadowRoot
        .getElementById("btn-new")
        ?.addEventListener("click", () => this._newCampaign());
      this.shadowRoot
        .getElementById("btn-load")
        ?.addEventListener("click", () => this._loadCampaign());
      return;
    }

    /* --- Ship status --- */
    const subsysHtml = Object.entries(c.subsystems || {})
      .map(([name, pct]) => {
        const cls =
          pct >= 80 ? "nominal" : pct >= 40 ? "impaired" : "destroyed";
        return `<div class="subsys ${cls}">${name}: ${pct.toFixed(0)}%</div>`;
      })
      .join("");

    const ammoHtml = Object.entries(c.ammo || {})
      .map(([type, count]) => `<span class="ammo-item">${type}: ${count}</span>`)
      .join("");

    /* --- Crew roster --- */
    const crewHtml = (c.crew_roster || [])
      .map((m) => {
        const healthCls =
          m.health >= 0.8 ? "nominal" : m.health >= 0.4 ? "impaired" : "destroyed";
        return `<div class="crew-member">
          <span class="crew-name">${m.name}</span>
          <span class="crew-stat ${healthCls}">HP ${(m.health * 100).toFixed(0)}%</span>
          <span class="crew-stat">FTG ${(m.fatigue * 100).toFixed(0)}%</span>
          <span class="crew-stat">STR ${(m.stress * 100).toFixed(0)}%</span>
        </div>`;
      })
      .join("");

    /* --- Reputation bars --- */
    const repHtml = Object.entries(c.reputation || {})
      .map(([faction, val]) => {
        const pct = ((val + 100) / 200) * 100;
        const cls = val > 20 ? "rep-pos" : val < -20 ? "rep-neg" : "rep-neutral";
        return `<div class="rep-row">
          <span class="rep-faction">${faction}</span>
          <div class="rep-bar"><div class="rep-fill ${cls}" style="width:${pct}%"></div></div>
          <span class="rep-val">${val}</span>
        </div>`;
      })
      .join("");

    /* --- Available missions --- */
    const missionHtml = (c.unlocked_scenarios || [])
      .map(
        (sid) =>
          `<button class="mission-btn" data-scenario="${sid}">${sid.replace(/_/g, " ")}</button>`
      )
      .join("");

    container.innerHTML = `
      <div class="campaign-grid">
        <section class="ship-section">
          <h3>SHIP STATUS -- ${(c.ship_class || "unknown").toUpperCase()}</h3>
          <div class="stat-row">HULL: ${(c.hull_percent || 0).toFixed(0)}%</div>
          <div class="stat-row">FUEL: ${c.fuel || 0} / ${c.max_fuel || 0}</div>
          <div class="subsys-grid">${subsysHtml}</div>
          <div class="ammo-row">${ammoHtml}</div>
        </section>

        <section class="crew-section">
          <h3>CREW (${c.crew_count || 0})</h3>
          ${crewHtml || "<div class='empty'>No crew</div>"}
        </section>

        <section class="finance-section">
          <h3>CREDITS: ${c.credits}</h3>
          <h3>CHAPTER ${(c.current_chapter || 0) + 1}</h3>
          <div class="rep-container">
            <h4>FACTION REPUTATION</h4>
            ${repHtml}
          </div>
        </section>

        <section class="mission-section">
          <h3>AVAILABLE MISSIONS</h3>
          <div class="mission-list">${missionHtml || "<div class='empty'>No missions unlocked</div>"}</div>
        </section>

        <section class="controls-section">
          <button id="btn-save">SAVE CAMPAIGN</button>
          <button id="btn-new2">NEW CAMPAIGN</button>
        </section>
      </div>`;

    // Wire buttons
    this.shadowRoot
      .getElementById("btn-save")
      ?.addEventListener("click", () => this._saveCampaign());
    this.shadowRoot
      .getElementById("btn-new2")
      ?.addEventListener("click", () => this._newCampaign());

    this.shadowRoot.querySelectorAll(".mission-btn").forEach((btn) => {
      btn.addEventListener("click", () =>
        this._startMission(btn.dataset.scenario)
      );
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: "Share Tech Mono", monospace;
          color: #c8d6e5;
        }
        h3, h4 { margin: 0 0 0.4em; color: #00d2ff; font-size: 0.85rem; }
        .empty-state {
          text-align: center;
          padding: 2em;
        }
        .empty-state button, .controls-section button {
          background: #1a2634;
          border: 1px solid #00d2ff;
          color: #00d2ff;
          padding: 0.5em 1.2em;
          cursor: pointer;
          font-family: inherit;
          margin: 0.3em;
        }
        .empty-state button:hover, .controls-section button:hover {
          background: #00d2ff;
          color: #0a1020;
        }
        .campaign-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.8em;
        }
        section {
          background: rgba(10, 16, 32, 0.6);
          border: 1px solid #1a2634;
          border-radius: 4px;
          padding: 0.6em;
        }
        .stat-row { font-size: 0.8rem; margin: 0.2em 0; }
        .subsys-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.2em;
          font-size: 0.75rem;
        }
        .subsys.nominal { color: #2ecc71; }
        .subsys.impaired { color: #f39c12; }
        .subsys.destroyed { color: #e74c3c; }
        .ammo-row {
          display: flex;
          gap: 0.8em;
          font-size: 0.75rem;
          margin-top: 0.3em;
          color: #aaa;
        }
        .crew-member {
          display: flex;
          gap: 0.6em;
          font-size: 0.75rem;
          padding: 0.2em 0;
          border-bottom: 1px solid #1a2634;
        }
        .crew-name { flex: 1; color: #ddd; }
        .crew-stat { color: #888; }
        .crew-stat.nominal { color: #2ecc71; }
        .crew-stat.impaired { color: #f39c12; }
        .crew-stat.destroyed { color: #e74c3c; }
        .rep-row {
          display: flex;
          align-items: center;
          gap: 0.4em;
          font-size: 0.75rem;
          margin: 0.2em 0;
        }
        .rep-faction { width: 5em; }
        .rep-bar {
          flex: 1;
          height: 8px;
          background: #1a2634;
          border-radius: 4px;
          overflow: hidden;
        }
        .rep-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s;
        }
        .rep-pos { background: #2ecc71; }
        .rep-neg { background: #e74c3c; }
        .rep-neutral { background: #f39c12; }
        .rep-val { width: 2.5em; text-align: right; }
        .mission-list { display: flex; flex-direction: column; gap: 0.3em; }
        .mission-btn {
          background: #1a2634;
          border: 1px solid #00d2ff;
          color: #00d2ff;
          padding: 0.4em 0.8em;
          cursor: pointer;
          font-family: inherit;
          font-size: 0.8rem;
          text-align: left;
          text-transform: capitalize;
        }
        .mission-btn:hover {
          background: #00d2ff;
          color: #0a1020;
        }
        .controls-section {
          grid-column: 1 / -1;
          display: flex;
          gap: 0.5em;
          justify-content: center;
        }
        .empty { color: #555; font-size: 0.75rem; font-style: italic; }
        #toast {
          position: fixed;
          bottom: 1em;
          left: 50%;
          transform: translateX(-50%);
          background: #1a2634;
          border: 1px solid #00d2ff;
          color: #00d2ff;
          padding: 0.4em 1em;
          border-radius: 4px;
          font-size: 0.8rem;
          opacity: 0;
          transition: opacity 0.3s;
          pointer-events: none;
        }
        #toast.visible { opacity: 1; }
      </style>
      <div id="content"></div>
      <div id="toast"></div>`;
  }
}

customElements.define("campaign-hub", CampaignHub);
