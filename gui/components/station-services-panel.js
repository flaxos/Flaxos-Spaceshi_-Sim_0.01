/**
 * Station Services Panel
 *
 * Between-mission economy UI.  Shows repair, resupply, crew hiring, and
 * upgrade options with credit costs.  Sends economy commands to the server
 * and updates on response.
 *
 * Lives in the MISSION view -- visible when docked at a station.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class StationServicesPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._prices = null;
    this._credits = 0;
    this._repairEstimate = null;
    this._resupplyEstimate = null;
  }

  connectedCallback() {
    this._render();
    this._subscribe();
    // Fetch initial prices
    this._fetchPrices();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      // Re-fetch prices when game state changes (e.g. after repair)
      this._fetchPrices();
    });
  }

  async _fetchPrices() {
    try {
      const result = await wsClient.sendShipCommand("station_prices", {});
      if (result && result.ok) {
        this._credits = result.credits || 0;
        this._prices = result.prices || {};
        this._repairEstimate = result.repair_estimate || {};
        this._resupplyEstimate = result.resupply_estimate || {};
        this._updateDisplay();
      }
    } catch {
      // Server may not have economy state yet -- show placeholder
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 12px;
          color: var(--text-primary, #c8d6e5);
        }

        .credits-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 12px;
          background: rgba(46, 213, 115, 0.1);
          border: 1px solid rgba(46, 213, 115, 0.3);
          border-radius: 4px;
          margin-bottom: 12px;
        }

        .credits-label {
          color: rgba(46, 213, 115, 0.7);
          text-transform: uppercase;
          font-size: 10px;
          letter-spacing: 1px;
        }

        .credits-value {
          color: #2ed573;
          font-size: 18px;
          font-weight: bold;
        }

        .section {
          margin-bottom: 12px;
          border: 1px solid rgba(200, 214, 229, 0.1);
          border-radius: 4px;
          overflow: hidden;
        }

        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 6px 10px;
          background: rgba(200, 214, 229, 0.05);
          border-bottom: 1px solid rgba(200, 214, 229, 0.1);
          text-transform: uppercase;
          font-size: 10px;
          letter-spacing: 1px;
          color: rgba(200, 214, 229, 0.6);
        }

        .section-cost {
          color: #ffa502;
          font-size: 11px;
        }

        .section-body {
          padding: 8px 10px;
        }

        .line-item {
          display: flex;
          justify-content: space-between;
          padding: 2px 0;
          color: rgba(200, 214, 229, 0.7);
          font-size: 11px;
        }

        .line-item .cost {
          color: #ffa502;
        }

        .btn {
          display: inline-block;
          padding: 6px 14px;
          border: 1px solid rgba(46, 213, 115, 0.4);
          border-radius: 3px;
          background: rgba(46, 213, 115, 0.1);
          color: #2ed573;
          font-family: inherit;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          margin-top: 6px;
        }

        .btn:hover {
          background: rgba(46, 213, 115, 0.2);
          border-color: rgba(46, 213, 115, 0.6);
        }

        .btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
          border-color: rgba(200, 214, 229, 0.2);
          color: rgba(200, 214, 229, 0.4);
          background: transparent;
        }

        .btn-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          margin-top: 6px;
        }

        select {
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(200, 214, 229, 0.2);
          border-radius: 3px;
          color: #c8d6e5;
          font-family: inherit;
          font-size: 11px;
          padding: 4px 8px;
        }

        .upgrade-grid {
          display: grid;
          grid-template-columns: 1fr auto auto;
          gap: 4px 8px;
          align-items: center;
        }

        .upgrade-name {
          font-size: 11px;
        }

        .upgrade-cost {
          color: #ffa502;
          font-size: 11px;
          text-align: right;
        }

        .feedback {
          padding: 4px 8px;
          margin-top: 6px;
          border-radius: 3px;
          font-size: 11px;
          display: none;
        }

        .feedback.success {
          display: block;
          background: rgba(46, 213, 115, 0.1);
          color: #2ed573;
        }

        .feedback.error {
          display: block;
          background: rgba(255, 71, 87, 0.1);
          color: #ff4757;
        }

        .zero-cost {
          color: rgba(200, 214, 229, 0.3);
        }
      </style>

      <!-- Credits balance -->
      <div class="credits-bar">
        <span class="credits-label">Credits</span>
        <span class="credits-value" id="credits-display">0</span>
      </div>

      <!-- REPAIR section -->
      <div class="section">
        <div class="section-header">
          <span>Repair</span>
          <span class="section-cost" id="repair-total">0 cr</span>
        </div>
        <div class="section-body">
          <div id="repair-items"></div>
          <button class="btn" id="btn-repair" disabled>Repair All</button>
          <div class="feedback" id="repair-feedback"></div>
        </div>
      </div>

      <!-- RESUPPLY section -->
      <div class="section">
        <div class="section-header">
          <span>Resupply</span>
          <span class="section-cost" id="resupply-total">0 cr</span>
        </div>
        <div class="section-body">
          <div id="resupply-items"></div>
          <button class="btn" id="btn-resupply" disabled>Resupply All</button>
          <div class="feedback" id="resupply-feedback"></div>
        </div>
      </div>

      <!-- CREW section -->
      <div class="section">
        <div class="section-header">
          <span>Hire Crew</span>
        </div>
        <div class="section-body">
          <div class="btn-row">
            <select id="crew-level">
              <option value="competent">Competent (100 cr)</option>
              <option value="skilled">Skilled (250 cr)</option>
              <option value="expert">Expert (500 cr)</option>
            </select>
            <button class="btn" id="btn-hire">Hire</button>
          </div>
          <div class="feedback" id="crew-feedback"></div>
        </div>
      </div>

      <!-- UPGRADES section -->
      <div class="section">
        <div class="section-header">
          <span>Ship Upgrades</span>
        </div>
        <div class="section-body">
          <div class="upgrade-grid" id="upgrade-grid"></div>
          <div class="feedback" id="upgrade-feedback"></div>
        </div>
      </div>
    `;

    // Wire up buttons
    this.shadowRoot.getElementById("btn-repair").addEventListener("click", () => this._doRepair());
    this.shadowRoot.getElementById("btn-resupply").addEventListener("click", () => this._doResupply());
    this.shadowRoot.getElementById("btn-hire").addEventListener("click", () => this._doHire());
  }

  _updateDisplay() {
    const $ = (id) => this.shadowRoot.getElementById(id);

    // Credits
    $("credits-display").textContent = this._credits.toLocaleString();

    // Repair breakdown
    const repair = this._repairEstimate || {};
    const repairItems = $("repair-items");
    let repairHtml = "";
    const hullCost = repair.hull || 0;
    if (hullCost > 0) {
      repairHtml += `<div class="line-item"><span>Hull</span><span class="cost">${hullCost} cr</span></div>`;
    }
    const subs = repair.subsystems || {};
    for (const [name, cost] of Object.entries(subs)) {
      if (cost > 0) {
        repairHtml += `<div class="line-item"><span>${name}</span><span class="cost">${cost} cr</span></div>`;
      }
    }
    if (!repairHtml) {
      repairHtml = `<div class="line-item zero-cost">No damage</div>`;
    }
    repairItems.innerHTML = repairHtml;

    const repairTotal = repair.total || 0;
    $("repair-total").textContent = `${repairTotal} cr`;
    $("btn-repair").disabled = repairTotal === 0 || repairTotal > this._credits;

    // Resupply breakdown
    const resupply = this._resupplyEstimate || {};
    const resupplyItems = $("resupply-items");
    let resupplyHtml = "";
    for (const key of ["fuel", "railgun", "torpedo", "missile", "pdc"]) {
      const cost = resupply[key] || 0;
      if (cost > 0) {
        resupplyHtml += `<div class="line-item"><span>${key}</span><span class="cost">${cost} cr</span></div>`;
      }
    }
    if (!resupplyHtml) {
      resupplyHtml = `<div class="line-item zero-cost">Fully supplied</div>`;
    }
    resupplyItems.innerHTML = resupplyHtml;

    const resupplyTotal = resupply.total || 0;
    $("resupply-total").textContent = `${resupplyTotal} cr`;
    $("btn-resupply").disabled = resupplyTotal === 0 || resupplyTotal > this._credits;

    // Upgrades grid
    const prices = this._prices || {};
    const upgrades = prices.upgrades || {};
    const grid = $("upgrade-grid");
    let upgradeHtml = "";
    const upgradeLabels = {
      armor: "+1cm Armor (section)",
      sensor_range: "+20% Sensor Range",
      gimbal: "Fixed to Gimbal",
      torpedo_tube: "+1 Torpedo Tube",
      drone_bay: "+1 Drone Bay",
      reactor: "+10% Reactor",
    };
    for (const [type, cost] of Object.entries(upgrades)) {
      const label = upgradeLabels[type] || type;
      const canAfford = this._credits >= cost;
      upgradeHtml += `
        <span class="upgrade-name">${label}</span>
        <span class="upgrade-cost">${cost} cr</span>
        <button class="btn" data-upgrade="${type}" ${canAfford ? "" : "disabled"}>Buy</button>
      `;
    }
    grid.innerHTML = upgradeHtml;

    // Wire upgrade buttons
    grid.querySelectorAll("button[data-upgrade]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const type = btn.getAttribute("data-upgrade");
        // For armor and gimbal, would need a target selector -- simplified
        // to first available for now.
        this._doUpgrade(type);
      });
    });
  }

  async _doRepair() {
    const fb = this.shadowRoot.getElementById("repair-feedback");
    try {
      const result = await wsClient.sendShipCommand("station_repair", {});
      if (result && result.ok) {
        fb.className = "feedback success";
        fb.textContent = result.message || "Repairs complete";
      } else {
        fb.className = "feedback error";
        fb.textContent = result.message || "Repair failed";
      }
    } catch (e) {
      fb.className = "feedback error";
      fb.textContent = "Repair failed: " + e.message;
    }
    this._fetchPrices();
  }

  async _doResupply() {
    const fb = this.shadowRoot.getElementById("resupply-feedback");
    try {
      const result = await wsClient.sendShipCommand("station_resupply", {});
      if (result && result.ok) {
        fb.className = "feedback success";
        fb.textContent = result.message || "Resupply complete";
      } else {
        fb.className = "feedback error";
        fb.textContent = result.message || "Resupply failed";
      }
    } catch (e) {
      fb.className = "feedback error";
      fb.textContent = "Resupply failed: " + e.message;
    }
    this._fetchPrices();
  }

  async _doHire() {
    const fb = this.shadowRoot.getElementById("crew-feedback");
    const level = this.shadowRoot.getElementById("crew-level").value;
    try {
      const result = await wsClient.sendShipCommand("station_hire_crew", {
        skill_level: level,
      });
      if (result && result.ok) {
        fb.className = "feedback success";
        fb.textContent = result.message || "Crew hired";
      } else {
        fb.className = "feedback error";
        fb.textContent = result.message || "Hire failed";
      }
    } catch (e) {
      fb.className = "feedback error";
      fb.textContent = "Hire failed: " + e.message;
    }
    this._fetchPrices();
  }

  async _doUpgrade(upgradeType) {
    const fb = this.shadowRoot.getElementById("upgrade-feedback");
    try {
      const result = await wsClient.sendShipCommand("station_upgrade", {
        upgrade_type: upgradeType,
        target: "",
      });
      if (result && result.ok) {
        fb.className = "feedback success";
        fb.textContent = result.message || "Upgrade applied";
      } else {
        fb.className = "feedback error";
        fb.textContent = result.message || result.error || "Upgrade failed";
      }
    } catch (e) {
      fb.className = "feedback error";
      fb.textContent = "Upgrade failed: " + e.message;
    }
    this._fetchPrices();
  }
}

customElements.define("station-services-panel", StationServicesPanel);
