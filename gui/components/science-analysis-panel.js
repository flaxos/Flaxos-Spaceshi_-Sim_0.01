/**
 * Science Analysis Panel — Tier-aware
 *
 * Provides science station analysis controls with per-tier rendering:
 *   MANUAL  — Raw sensor returns only. IR watts, RCS m^2, bearing/range in
 *             radians/metres. No classification assist. Player interprets.
 *   RAW     — Full spectral breakdown tables, manual classification workflow
 *             (select contact -> view signature -> choose class from dropdown).
 *   ARCADE  — Auto-classified contacts with confidence %. Threat level badges.
 *             Simplified mass/drive-type. One-click "Deep Scan" button.
 *   CPU-ASSIST — Auto-science proposals: scan queue, threat flags, approve/deny.
 *
 * Follows the tier-change listener pattern from flight-computer-panel.js.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getProposalCSS } from "../js/proposal-styles.js";

/** Ship classification options for RAW tier manual workflow */
const SHIP_CLASSES = [
  "Unknown", "Corvette", "Frigate", "Destroyer", "Cruiser",
  "Battleship", "Carrier", "Transport", "Freighter", "Station",
  "Shuttle", "Mining", "Science", "Patrol", "Gunboat"
];

class ScienceAnalysisPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tierHandler = null;
    this._selectedContact = null;
    this._lastResult = null;
    this._tier = window.controlTier || "arcade";
  }

  connectedCallback() {
    this._render();
    this._subscribe();
    this._applyTier();
    // Listen for tier changes (same pattern as flight-computer-panel.js)
    this._tierHandler = () => this._applyTier();
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  /** Respond to tier changes — re-render the entire panel layout */
  _applyTier() {
    const newTier = window.controlTier || "arcade";
    if (newTier !== this._tier || !this.shadowRoot.querySelector(".sci-panel")) {
      this._tier = newTier;
      this._render();
      this._updateDisplay();
    }
  }

  async _sendCommand(cmd, args = {}) {
    const ws = window._flaxosModules?.wsClient || window.flaxosApp?.wsClient;
    if (ws && ws.sendShipCommand) {
      try {
        const result = await ws.sendShipCommand(cmd, args);
        if (result && result.ok) {
          this._lastResult = result;
          this._showResult(cmd, result);
        }
        return result;
      } catch (err) {
        console.error(`Science command failed: ${cmd}`, err);
        return null;
      }
    }
    return null;
  }

  // =========================================================================
  //  RENDER — tier-dispatched
  // =========================================================================

  _render() {
    const tier = this._tier;
    let body = "";
    if (tier === "manual") body = this._renderManual();
    else if (tier === "raw") body = this._renderRaw();
    else if (tier === "cpu-assist") body = this._renderCpuAssist();
    else body = this._renderArcade();

    this.shadowRoot.innerHTML = `
      <style>${this._sharedStyles()}${this._tierStyles(tier)}</style>
      <div class="sci-panel tier-${tier}">${body}</div>
    `;
    this._wireEvents(tier);
  }

  // ---- Shared CSS used by all tiers ----
  _sharedStyles() {
    return `
      :host {
        display: block;
        font-family: var(--font-sans, "Inter", sans-serif);
        font-size: 0.8rem;
        padding: 12px;
      }
      .section { margin-bottom: 16px; }
      .section-title {
        font-size: 0.7rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.5px;
        color: var(--status-info, #00aaff);
        margin-bottom: 8px; padding-bottom: 4px;
        border-bottom: 1px solid var(--border-default, #2a2a3a);
      }
      .contact-select {
        width: 100%; padding: 6px 8px;
        background: var(--bg-secondary, #12121a);
        color: var(--text-primary, #e0e0e8);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.75rem; margin-bottom: 8px;
      }
      .btn-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
      .btn {
        padding: 6px 12px;
        background: var(--bg-secondary, #12121a);
        color: var(--text-primary, #e0e0e8);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem; cursor: pointer;
        transition: background 0.15s, border-color 0.15s;
      }
      .btn:hover { background: var(--bg-tertiary, #1a1a2a); border-color: var(--status-info, #00aaff); }
      .btn:disabled { opacity: 0.4; cursor: not-allowed; }
      .btn-scan { border-color: var(--status-info, #00aaff); color: var(--status-info, #00aaff); }
      .btn-scan:hover:not(:disabled) { background: rgba(0, 170, 255, 0.1); }
      .result-panel {
        background: var(--bg-secondary, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px; padding: 10px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem; line-height: 1.5;
        max-height: 300px; overflow-y: auto; white-space: pre-wrap;
      }
      .result-panel .label { color: var(--text-secondary, #888899); }
      .result-panel .value { color: var(--text-primary, #e0e0e8); }
      .result-panel .highlight { color: var(--status-info, #00aaff); font-weight: 600; }
      .threat-minimal { color: var(--status-nominal, #00ff88); }
      .threat-low { color: var(--status-nominal, #00ff88); }
      .threat-moderate { color: var(--status-warning, #ffaa00); }
      .threat-high { color: var(--status-critical, #ff4444); }
      .threat-critical { color: var(--status-critical, #ff4444); font-weight: 700; }
      .status-row { display: flex; justify-content: space-between; padding: 3px 0; }
      .status-label { color: var(--text-secondary, #888899); }
      .status-value {
        color: var(--text-primary, #e0e0e8);
        font-family: var(--font-mono, "JetBrains Mono", monospace);
      }
      .no-contacts { color: var(--text-dim, #555566); font-style: italic; padding: 8px 0; }
    `;
  }

  // ---- Per-tier extra CSS ----
  _tierStyles(tier) {
    if (tier === "manual") return `
      /* MANUAL: amber monospace, minimal chrome */
      .sci-panel.tier-manual {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: #ffe0b0;
      }
      .sci-panel.tier-manual .section-title {
        color: #ff8800;
        border-bottom-color: #442200;
      }
      .raw-data-grid {
        display: grid; grid-template-columns: max-content 1fr;
        gap: 2px 12px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
      }
      .raw-data-grid .lbl { color: #aa7744; text-transform: uppercase; }
      .raw-data-grid .val { color: #ffe0b0; }
      .manual-note {
        color: #886644; font-size: 0.65rem; font-style: italic;
        margin-top: 12px; border-top: 1px solid #332200; padding-top: 6px;
      }
    `;
    if (tier === "raw") return `
      /* RAW: green phosphor terminal, full data exposure */
      .sci-panel.tier-raw {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: #d8e8d8;
      }
      .sci-panel.tier-raw .section-title {
        color: #44ff88;
        border-bottom-color: #113322;
      }
      .spectral-table {
        width: 100%; border-collapse: collapse;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.65rem; margin-bottom: 8px;
      }
      .spectral-table th {
        text-align: left; color: #44ff88; padding: 3px 6px;
        border-bottom: 1px solid #224433;
        font-weight: 600; text-transform: uppercase;
      }
      .spectral-table td {
        padding: 3px 6px; color: #d8e8d8;
        border-bottom: 1px solid #1a2a1f;
      }
      .classify-row {
        display: flex; gap: 6px; align-items: center; margin-top: 8px;
      }
      .classify-select {
        flex: 1; padding: 4px 6px;
        background: var(--bg-secondary, #12121a);
        color: #d8e8d8;
        border: 1px solid #224433;
        border-radius: 3px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
      }
    `;
    if (tier === "cpu-assist") return `
      /* Proposal cards — shared styles from proposal-styles.js */
      ${getProposalCSS()}
      /* Legacy alias: auto-proposal maps to proposal-card */
      .auto-proposal {
        background: rgba(192, 160, 255, 0.06);
        border: 1px solid rgba(192, 160, 255, 0.3);
        border-left: 3px solid var(--tier-accent, #c0a0ff);
        border-radius: 6px; padding: 10px 12px; margin-bottom: 8px;
        animation: proposalSlideIn 0.3s ease-out;
        position: relative; overflow: hidden;
      }
      .auto-proposal .desc {
        color: var(--text-primary, #e0e0e8);
        font-size: 0.72rem; margin-bottom: 6px; line-height: 1.4;
      }
      .auto-proposal .meta {
        color: var(--text-dim, #555566);
        font-size: 0.6rem; margin-bottom: 4px;
      }
      .btn-deny:hover { background: rgba(255, 68, 68, 0.2); }
      .auto-toggle-row {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 10px; padding: 6px 8px;
        background: rgba(192, 160, 255, 0.05);
        border: 1px solid rgba(192, 160, 255, 0.15);
        border-radius: 4px;
      }
      .auto-toggle-label {
        color: #c0a0ff; font-size: 0.7rem; font-weight: 600;
        letter-spacing: 0.5px;
      }
      .auto-toggle-btn {
        background: rgba(192, 160, 255, 0.15); color: #c0a0ff;
        border: 1px solid rgba(192, 160, 255, 0.3);
        padding: 3px 12px; border-radius: 4px; cursor: pointer;
        font-size: 0.65rem;
      }
      .auto-toggle-btn:hover { background: rgba(192, 160, 255, 0.25); }
      .auto-toggle-btn.active {
        background: rgba(0, 255, 136, 0.15); color: #00ff88;
        border-color: rgba(0, 255, 136, 0.3);
      }
      .threat-flag {
        display: inline-block; padding: 1px 6px; border-radius: 3px;
        font-size: 0.6rem; font-weight: 600; text-transform: uppercase;
        margin-left: 6px;
      }
      .threat-flag.high { background: rgba(255, 68, 68, 0.2); color: #ff4444; }
      .threat-flag.moderate { background: rgba(255, 170, 0, 0.2); color: #ffaa00; }
      .threat-flag.low { background: rgba(0, 255, 136, 0.15); color: #00ff88; }
      .contact-summary {
        display: flex; justify-content: space-between; align-items: center;
        padding: 4px 0; border-bottom: 1px solid var(--border-default, #2a2a3a);
        font-size: 0.7rem;
      }
      .contact-summary .cname { color: var(--text-primary, #e0e0e8); }
      .contact-summary .cdist { color: var(--text-secondary, #888899); font-family: var(--font-mono, monospace); }
    `;
    // ARCADE
    return `
      /* ARCADE: clean blue UI, threat badges, one-click actions */
      .threat-badge {
        display: inline-block; padding: 2px 8px; border-radius: 10px;
        font-size: 0.6rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .threat-badge.critical { background: rgba(255, 68, 68, 0.2); color: #ff4444; }
      .threat-badge.high { background: rgba(255, 68, 68, 0.15); color: #ff6666; }
      .threat-badge.moderate { background: rgba(255, 170, 0, 0.15); color: #ffaa00; }
      .threat-badge.low { background: rgba(0, 255, 136, 0.1); color: #00ff88; }
      .threat-badge.minimal { background: rgba(85, 85, 102, 0.2); color: #888899; }
      .contact-card {
        background: var(--bg-secondary, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 6px; padding: 8px 10px; margin: 4px 0;
        cursor: pointer; transition: border-color 0.15s;
      }
      .contact-card:hover { border-color: var(--status-info, #00aaff); }
      .contact-card.selected { border-color: var(--status-info, #00aaff); background: rgba(0, 170, 255, 0.05); }
      .card-header {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 4px;
      }
      .card-name { color: var(--text-primary, #e0e0e8); font-weight: 600; font-size: 0.75rem; }
      .card-details {
        display: grid; grid-template-columns: 1fr 1fr; gap: 2px 12px;
        font-size: 0.7rem;
      }
      .card-details .cd-label { color: var(--text-dim, #555566); }
      .card-details .cd-value { color: var(--text-secondary, #888899); font-family: var(--font-mono, monospace); }
      .btn-deep-scan {
        width: 100%; padding: 8px; margin-top: 8px;
        background: rgba(0, 170, 255, 0.1);
        color: var(--status-info, #00aaff);
        border: 1px solid var(--status-info, #00aaff);
        border-radius: 6px; cursor: pointer;
        font-size: 0.75rem; font-weight: 600;
        transition: background 0.15s;
      }
      .btn-deep-scan:hover:not(:disabled) { background: rgba(0, 170, 255, 0.2); }
      .btn-deep-scan:disabled { opacity: 0.4; cursor: not-allowed; }
    `;
  }

  // =========================================================================
  //  MANUAL TIER — raw sensor returns, no classification assist
  // =========================================================================

  _renderManual() {
    return `
      <div class="section">
        <div class="section-title">Raw Sensor Returns</div>
        <div id="manual-returns" class="raw-data-grid">
          <span class="lbl">No contacts</span><span class="val">--</span>
        </div>
      </div>
      <div class="section">
        <div class="section-title">Sensor Status</div>
        <div class="status-row">
          <span class="status-label">Sensor Health</span>
          <span class="status-value" id="sensor-health">--</span>
        </div>
        <div class="status-row">
          <span class="status-label">Tracked Returns</span>
          <span class="status-value" id="tracked-contacts">--</span>
        </div>
      </div>
      <div class="manual-note">
        No classification assist at this tier. Interpret signatures manually.
      </div>
    `;
  }

  /** Update the MANUAL tier raw returns grid */
  _updateManual() {
    const grid = this.shadowRoot.getElementById("manual-returns");
    if (!grid) return;

    const contacts = stateManager.getContacts?.() || [];
    if (contacts.length === 0) {
      grid.innerHTML = `<span class="lbl">No returns</span><span class="val">--</span>`;
      return;
    }

    grid.innerHTML = contacts.map(c => {
      const id = c.id || c.contact_id || "???";
      const range = c.range ?? c.distance ?? 0;
      const bearing = c.bearing ?? 0;
      // Convert to radians for the manual display
      const bearingRad = typeof bearing === "number" ? (bearing * Math.PI / 180).toFixed(4) : "--";
      const irWatts = c.ir_signature ?? c.emissions?.ir_watts ?? "--";
      const rcsM2 = c.rcs ?? c.emissions?.rcs_m2 ?? "--";
      const signal = c.signal_strength ?? c.confidence ?? "--";

      return `
        <span class="lbl">RTN</span><span class="val">${id}</span>
        <span class="lbl">BRG</span><span class="val">${bearingRad} rad</span>
        <span class="lbl">RNG</span><span class="val">${range.toFixed(0)} m</span>
        <span class="lbl">IR</span><span class="val">${typeof irWatts === "number" ? this._formatPower(irWatts) : irWatts}</span>
        <span class="lbl">RCS</span><span class="val">${typeof rcsM2 === "number" ? rcsM2.toFixed(2) + " m\u00B2" : rcsM2}</span>
        <span class="lbl">SIG</span><span class="val">${typeof signal === "number" ? (signal * 100).toFixed(0) + "%" : signal}</span>
      `;
    }).join('<span class="lbl" style="grid-column:span 2;border-top:1px solid #332200;margin:4px 0;"></span>');
  }

  // =========================================================================
  //  RAW TIER — full spectral tables, manual classification workflow
  // =========================================================================

  _renderRaw() {
    return `
      <div class="section">
        <div class="section-title">Contact Selection</div>
        <select class="contact-select" id="contact-select">
          <option value="">-- Select Contact --</option>
        </select>
      </div>

      <div class="section">
        <div class="section-title">Spectral Breakdown</div>
        <table class="spectral-table" id="spectral-table">
          <thead>
            <tr><th>Field</th><th>Value</th><th>Unit</th></tr>
          </thead>
          <tbody id="spectral-body">
            <tr><td colspan="3" style="color:var(--text-dim);">Select a contact</td></tr>
          </tbody>
        </table>
      </div>

      <div class="section">
        <div class="section-title">Manual Classification</div>
        <div class="classify-row">
          <select class="classify-select" id="classify-select" disabled>
            ${SHIP_CLASSES.map(c => `<option value="${c}">${c}</option>`).join("")}
          </select>
          <button class="btn" id="btn-classify" disabled>Classify</button>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Analysis Commands</div>
        <div class="btn-row">
          <button class="btn" id="btn-analyze" disabled>Analyze</button>
          <button class="btn" id="btn-spectral" disabled>Spectral</button>
          <button class="btn" id="btn-mass" disabled>Est. Mass</button>
          <button class="btn" id="btn-threat" disabled>Threat</button>
        </div>
        <div class="btn-row">
          <button class="btn btn-scan" id="btn-spectral-scan" disabled
            title="Spectral Scan -- effective within 50 km">Spectral Scan</button>
          <button class="btn btn-scan" id="btn-composition-scan" disabled
            title="Composition Scan -- effective within 20 km, requires active ping">Composition Scan</button>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Result</div>
        <div class="result-panel" id="result-panel">
          <span class="label">Select a contact and run analysis.</span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Sensor Status</div>
        <div class="status-row">
          <span class="status-label">Sensor Health</span>
          <span class="status-value" id="sensor-health">--</span>
        </div>
        <div class="status-row">
          <span class="status-label">Tracked Contacts</span>
          <span class="status-value" id="tracked-contacts">--</span>
        </div>
      </div>
    `;
  }

  /** Update the RAW tier spectral breakdown table for the selected contact */
  _updateRawSpectral() {
    const body = this.shadowRoot.getElementById("spectral-body");
    if (!body || !this._selectedContact) return;

    const contacts = stateManager.getContacts?.() || [];
    const contact = contacts.find(c => (c.id || c.contact_id) === this._selectedContact);
    if (!contact) {
      body.innerHTML = `<tr><td colspan="3" style="color:var(--text-dim);">Contact lost</td></tr>`;
      return;
    }

    const range = contact.range ?? contact.distance ?? 0;
    const bearing = contact.bearing ?? 0;
    const irWatts = contact.ir_signature ?? contact.emissions?.ir_watts;
    const rcsM2 = contact.rcs ?? contact.emissions?.rcs_m2;
    const confidence = contact.confidence;
    const velocity = contact.velocity ?? contact.speed;
    const rangeRate = contact.range_rate ?? contact.closure;
    const detection = contact.detection_method ?? "--";

    const rows = [
      ["Bearing", typeof bearing === "number" ? bearing.toFixed(1) : "--", "deg"],
      ["Range", typeof range === "number" ? range.toFixed(0) : "--", "m"],
      ["Range Rate", typeof rangeRate === "number" ? rangeRate.toFixed(1) : "--", "m/s"],
      ["Velocity", typeof velocity === "number" ? velocity.toFixed(1) : "--", "m/s"],
      ["IR Emission", typeof irWatts === "number" ? this._formatPower(irWatts) : "--", ""],
      ["RCS", typeof rcsM2 === "number" ? rcsM2.toFixed(2) : "--", "m\u00B2"],
      ["Confidence", typeof confidence === "number" ? (confidence * 100).toFixed(0) : "--", "%"],
      ["Detection", detection, ""],
    ];

    body.innerHTML = rows.map(([field, value, unit]) =>
      `<tr><td>${field}</td><td>${value}</td><td>${unit}</td></tr>`
    ).join("");
  }

  // =========================================================================
  //  ARCADE TIER — simplified, auto-classified, threat badges
  // =========================================================================

  _renderArcade() {
    return `
      <div class="section">
        <div class="section-title">Contacts</div>
        <div id="arcade-contacts">
          <div class="no-contacts">No contacts detected</div>
        </div>
      </div>

      <div class="section" id="arcade-selected-section" style="display:none;">
        <div class="section-title">Selected Contact</div>
        <div class="card-details" id="arcade-selected-details"></div>
        <button class="btn-deep-scan" id="btn-deep-scan" disabled>Deep Scan</button>
      </div>

      <div class="section">
        <div class="section-title">Scan Result</div>
        <div class="result-panel" id="result-panel">
          <span class="label">Select a contact and scan.</span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Sensor Status</div>
        <div class="status-row">
          <span class="status-label">Sensor Health</span>
          <span class="status-value" id="sensor-health">--</span>
        </div>
        <div class="status-row">
          <span class="status-label">Contacts Tracked</span>
          <span class="status-value" id="tracked-contacts">--</span>
        </div>
      </div>
    `;
  }

  /** Build the arcade contact card list with threat badges */
  _updateArcadeContacts() {
    const container = this.shadowRoot.getElementById("arcade-contacts");
    if (!container) return;

    const contacts = stateManager.getContacts?.() || [];
    if (contacts.length === 0) {
      container.innerHTML = `<div class="no-contacts">No contacts detected</div>`;
      return;
    }

    container.innerHTML = contacts.map(c => {
      const id = c.id || c.contact_id || "???";
      const name = c.name || c.classification || "Unknown";
      const range = c.range ?? c.distance ?? 0;
      const rangeKm = (range / 1000).toFixed(1);
      const threat = this._inferThreatLevel(c);
      const isSelected = id === this._selectedContact;

      return `
        <div class="contact-card ${isSelected ? "selected" : ""}" data-contact-id="${id}">
          <div class="card-header">
            <span class="card-name">${name}</span>
            <span class="threat-badge ${threat}">${threat.toUpperCase()}</span>
          </div>
          <div class="card-details">
            <span class="cd-label">Range</span><span class="cd-value">${rangeKm} km</span>
            <span class="cd-label">Confidence</span><span class="cd-value">${c.confidence ? (c.confidence * 100).toFixed(0) + "%" : "--"}</span>
          </div>
        </div>
      `;
    }).join("");

    // Update selected detail section
    this._updateArcadeSelectedDetail(contacts);
  }

  /** Update the arcade selected contact detail and deep scan button */
  _updateArcadeSelectedDetail(contacts) {
    const section = this.shadowRoot.getElementById("arcade-selected-section");
    const details = this.shadowRoot.getElementById("arcade-selected-details");
    const scanBtn = this.shadowRoot.getElementById("btn-deep-scan");
    if (!section || !details || !scanBtn) return;

    if (!this._selectedContact) {
      section.style.display = "none";
      return;
    }

    const contact = (contacts || stateManager.getContacts?.() || [])
      .find(c => (c.id || c.contact_id) === this._selectedContact);
    if (!contact) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";
    scanBtn.disabled = false;

    const range = contact.range ?? contact.distance ?? 0;
    const driveType = contact.drive_type ?? contact.emissions?.drive_type ?? "--";
    const mass = contact.estimated_mass ?? "--";

    details.innerHTML = `
      <span class="cd-label">ID</span><span class="cd-value">${contact.id || contact.contact_id}</span>
      <span class="cd-label">Class</span><span class="cd-value">${contact.name || contact.classification || "Unknown"}</span>
      <span class="cd-label">Range</span><span class="cd-value">${(range / 1000).toFixed(1)} km</span>
      <span class="cd-label">Drive</span><span class="cd-value">${driveType}</span>
      <span class="cd-label">Mass</span><span class="cd-value">${typeof mass === "number" ? this._formatMassKg(mass) : mass}</span>
      <span class="cd-label">Confidence</span><span class="cd-value">${contact.confidence ? (contact.confidence * 100).toFixed(0) + "%" : "--"}</span>
    `;
  }

  // =========================================================================
  //  CPU-ASSIST TIER — auto-science proposals, threat flags
  // =========================================================================

  _renderCpuAssist() {
    return `
      <div class="section">
        <div class="auto-toggle-row">
          <span class="auto-toggle-label">AUTO-SCIENCE</span>
          <button class="auto-toggle-btn" id="auto-sci-toggle">ENABLE</button>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Scan Proposals</div>
        <div id="proposals-list">
          <div class="no-contacts">No pending proposals</div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Contact Summary</div>
        <div id="contact-summary-list">
          <div class="no-contacts">No contacts</div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Sensor Status</div>
        <div class="status-row">
          <span class="status-label">Sensor Health</span>
          <span class="status-value" id="sensor-health">--</span>
        </div>
        <div class="status-row">
          <span class="status-label">Auto-Scans Run</span>
          <span class="status-value" id="tracked-contacts">--</span>
        </div>
      </div>
    `;
  }

  /** Update the CPU-ASSIST proposals and contact summary */
  _updateCpuAssist() {
    const ship = stateManager.getShipState();
    const autoSci = ship?.auto_science || {};

    // Toggle button state
    const toggle = this.shadowRoot.getElementById("auto-sci-toggle");
    if (toggle) {
      toggle.textContent = autoSci.enabled ? "DISABLE" : "ENABLE";
      toggle.classList.toggle("active", !!autoSci.enabled);
    }

    // Proposals
    const proposalsList = this.shadowRoot.getElementById("proposals-list");
    if (proposalsList) {
      const proposals = autoSci.proposals || [];
      if (proposals.length === 0) {
        proposalsList.innerHTML = `<div class="no-contacts">${autoSci.enabled ? "Scanning... no proposals yet" : "Enable auto-science to begin"}</div>`;
      } else {
        proposalsList.innerHTML = proposals.map(p => {
          const confidence = p.confidence ?? 0;
          const remaining = Math.max(0, p.time_remaining || 0);
          const total = p.total_time || 30;
          const timerPct = Math.min(100, (remaining / total) * 100);
          const isUrgent = confidence > 0.8 || remaining < 5 || p.priority === "high";
          const urgentClass = isUrgent ? " urgent" : "";
          return `
          <div class="proposal-card${urgentClass}">
            <div class="proposal-header">
              <span class="proposal-action">${p.description || p.action || "Scan proposal"}</span>
              ${confidence > 0 ? `<span class="proposal-confidence">${(confidence * 100).toFixed(0)}%</span>` : ""}
            </div>
            <div class="proposal-reason">${p.target || ""} ${p.priority ? "Priority: " + p.priority : ""}</div>
            ${remaining > 0 ? `<div class="proposal-timer"><div class="proposal-timer-fill" style="width:${timerPct}%"></div></div>` : ""}
            <div class="proposal-actions">
              <button class="proposal-approve" data-approve="${p.id}">APPROVE</button>
              <button class="proposal-deny" data-deny="${p.id}">DENY</button>
            </div>
          </div>`;
        }).join("");
      }
    }

    // Contact summary with threat flags
    const summaryList = this.shadowRoot.getElementById("contact-summary-list");
    if (summaryList) {
      const contacts = stateManager.getContacts?.() || [];
      if (contacts.length === 0) {
        summaryList.innerHTML = `<div class="no-contacts">No contacts</div>`;
      } else {
        // Sort by threat: hostile/high first
        const sorted = [...contacts].sort((a, b) => {
          return this._threatScore(b) - this._threatScore(a);
        });
        summaryList.innerHTML = sorted.map(c => {
          const name = c.name || c.classification || "Unknown";
          const range = c.range ?? c.distance ?? 0;
          const threat = this._inferThreatLevel(c);
          const threatHtml = threat !== "minimal"
            ? `<span class="threat-flag ${threat}">${threat}</span>`
            : "";
          return `
            <div class="contact-summary">
              <span class="cname">${name}${threatHtml}</span>
              <span class="cdist">${(range / 1000).toFixed(1)} km</span>
            </div>
          `;
        }).join("");
      }
    }
  }

  // =========================================================================
  //  EVENT WIRING — per tier
  // =========================================================================

  _wireEvents(tier) {
    if (tier === "manual") {
      // No interactive elements in manual tier
      return;
    }

    if (tier === "raw") {
      // Contact select
      const select = this.shadowRoot.getElementById("contact-select");
      if (select) {
        select.addEventListener("change", (e) => {
          this._selectedContact = e.target.value || null;
          this._updateRawButtons();
          this._updateRawSpectral();
        });
      }

      // Classification workflow
      const classifyBtn = this.shadowRoot.getElementById("btn-classify");
      if (classifyBtn) {
        classifyBtn.addEventListener("click", () => {
          if (!this._selectedContact) return;
          const classSelect = this.shadowRoot.getElementById("classify-select");
          const cls = classSelect?.value;
          if (cls) {
            this._sendCommand("classify_contact", {
              contact_id: this._selectedContact,
              classification: cls
            });
          }
        });
      }

      // Analysis commands
      this._wireAnalysisButtons();
      return;
    }

    if (tier === "arcade") {
      // Contact card selection
      const container = this.shadowRoot.getElementById("arcade-contacts");
      if (container) {
        container.addEventListener("click", (e) => {
          const card = e.target.closest(".contact-card");
          if (card) {
            this._selectedContact = card.dataset.contactId;
            this._updateArcadeContacts();
          }
        });
      }

      // Deep Scan button — runs all analysis commands in sequence
      const deepScan = this.shadowRoot.getElementById("btn-deep-scan");
      if (deepScan) {
        deepScan.addEventListener("click", async () => {
          if (!this._selectedContact) return;
          deepScan.disabled = true;
          deepScan.textContent = "Scanning...";
          // Fire spectral + composition + threat in parallel
          await Promise.all([
            this._sendCommand("science_spectral_analysis", { contact_id: this._selectedContact }),
            this._sendCommand("science_composition_scan", { contact_id: this._selectedContact }),
            this._sendCommand("assess_threat", { contact_id: this._selectedContact })
          ]);
          deepScan.disabled = false;
          deepScan.textContent = "Deep Scan";
        });
      }
      return;
    }

    if (tier === "cpu-assist") {
      // Auto-science toggle
      const toggle = this.shadowRoot.getElementById("auto-sci-toggle");
      if (toggle) {
        toggle.addEventListener("click", () => {
          const ship = stateManager.getShipState();
          const cmd = ship?.auto_science?.enabled ? "disable_auto_science" : "enable_auto_science";
          this._sendCommand(cmd, {});
        });
      }

      // Proposal approve/deny via delegation
      const proposalsList = this.shadowRoot.getElementById("proposals-list");
      if (proposalsList) {
        proposalsList.addEventListener("click", (e) => {
          const approveBtn = e.target.closest("[data-approve]");
          const denyBtn = e.target.closest("[data-deny]");
          if (approveBtn) {
            this._sendCommand("approve_science", { proposal_id: approveBtn.dataset.approve });
          }
          if (denyBtn) {
            this._sendCommand("deny_science", { proposal_id: denyBtn.dataset.deny });
          }
        });
      }
      return;
    }
  }

  /** Wire the standard analysis buttons (used in RAW tier) */
  _wireAnalysisButtons() {
    const cmds = [
      ["btn-analyze", "analyze_contact"],
      ["btn-spectral", "spectral_analysis"],
      ["btn-mass", "estimate_mass"],
      ["btn-threat", "assess_threat"],
      ["btn-spectral-scan", "science_spectral_analysis"],
      ["btn-composition-scan", "science_composition_scan"],
    ];
    for (const [id, cmd] of cmds) {
      const btn = this.shadowRoot.getElementById(id);
      if (btn) {
        btn.addEventListener("click", () => {
          if (this._selectedContact) this._sendCommand(cmd, { contact_id: this._selectedContact });
        });
      }
    }
  }

  /** Enable/disable RAW tier buttons based on contact selection */
  _updateRawButtons() {
    const hasContact = !!this._selectedContact;
    const ids = [
      "btn-analyze", "btn-spectral", "btn-mass", "btn-threat",
      "btn-spectral-scan", "btn-composition-scan",
      "btn-classify", "classify-select"
    ];
    for (const id of ids) {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.disabled = !hasContact;
    }
  }

  // =========================================================================
  //  UPDATE DISPLAY — tier-dispatched
  // =========================================================================

  _updateDisplay() {
    const ship = stateManager.getShipState();
    if (!ship) return;

    const tier = this._tier;

    // Update sensor status (shared across all tiers)
    this._updateSensorStatus(ship);

    // Tier-specific updates
    if (tier === "manual") {
      this._updateManual();
    } else if (tier === "raw") {
      this._updateContactList();
      this._updateRawSpectral();
    } else if (tier === "arcade") {
      this._updateArcadeContacts();
    } else if (tier === "cpu-assist") {
      this._updateCpuAssist();
    }
  }

  /** Update the sensor health/count readout (all tiers) */
  _updateSensorStatus(ship) {
    const sensors = ship.sensors || {};
    const healthEl = this.shadowRoot.getElementById("sensor-health");
    const contactsEl = this.shadowRoot.getElementById("tracked-contacts");

    if (healthEl) {
      const health = sensors.sensor_health ?? ship.subsystem_health?.sensors;
      healthEl.textContent = health !== undefined
        ? `${(health * 100).toFixed(0)}%`
        : "--";
    }
    if (contactsEl) {
      contactsEl.textContent = sensors.count ?? sensors.contacts?.length ?? "--";
    }
  }

  /** Update the contact dropdown (RAW tier) */
  _updateContactList() {
    const select = this.shadowRoot.getElementById("contact-select");
    if (!select) return;

    const contacts = stateManager.getContacts?.() || [];
    const isFocused = this.shadowRoot.activeElement === select;
    const currentValue = select.value;

    if (isFocused) {
      // Don't tear down the DOM while user is interacting
      return;
    }

    const options = ['<option value="">-- Select Contact --</option>'];
    for (const c of contacts) {
      const id = c.id || c.contact_id;
      if (!id) continue;
      const dist = c.distance ? `${(c.distance / 1000).toFixed(1)}km` : "?";
      const cls = c.classification || "Unknown";
      options.push(`<option value="${id}">${id} -- ${cls} @ ${dist}</option>`);
    }

    select.innerHTML = options.join("");
    if (currentValue) select.value = currentValue;
  }

  // =========================================================================
  //  RESULT FORMATTING (shared across RAW / ARCADE tiers)
  // =========================================================================

  _showResult(command, result) {
    const panel = this.shadowRoot.getElementById("result-panel");
    if (!panel) return;

    const formatters = {
      "analyze_contact": (r) => this._formatAnalysis(r),
      "spectral_analysis": (r) => this._formatSpectral(r),
      "estimate_mass": (r) => this._formatMass(r),
      "assess_threat": (r) => this._formatThreat(r),
      "science_spectral_analysis": (r) => this._formatSpectralScan(r),
      "science_composition_scan": (r) => this._formatCompositionScan(r),
    };

    const formatter = formatters[command];
    panel.innerHTML = formatter
      ? formatter(result)
      : `<span class="value">${result.status || JSON.stringify(result)}</span>`;
  }

  _formatAnalysis(r) {
    const cd = r.contact_data || {};
    const em = r.emissions || {};
    const dist = cd.distance ? `${(cd.distance / 1000).toFixed(1)} km` : "?";
    return `<span class="highlight">CONTACT ANALYSIS: ${r.contact_id}</span>
<span class="label">Classification:</span> <span class="value">${r.classification || "Unknown"}</span>
<span class="label">Distance:</span> <span class="value">${dist}</span>
<span class="label">Confidence:</span> <span class="value">${cd.confidence ? (cd.confidence * 100).toFixed(0) + "%" : "?"}</span>
<span class="label">Detection:</span> <span class="value">${cd.detection_method || "?"}</span>
<span class="label">Track Age:</span> <span class="value">${cd.age ? cd.age.toFixed(1) + "s" : "?"}</span>
<span class="label">IR Signature:</span> <span class="value">${em.ir_watts ? this._formatPower(em.ir_watts) : "?"}</span>
<span class="label">RCS:</span> <span class="value">${em.rcs_m2 ? em.rcs_m2.toFixed(1) + " m\u00B2" : "?"}</span>
<span class="label">Signature:</span> <span class="value">${em.signature_strength || "?"}</span>
<span class="label">Quality:</span> <span class="value">${r.analysis_quality ? (r.analysis_quality * 100).toFixed(0) + "%" : "?"}</span>`;
  }

  _formatSpectral(r) {
    const sd = r.spectral_data || {};
    const ir = sd.ir_signature || {};
    const rcs = sd.rcs_data || {};
    const drive = sd.drive_inference || {};
    return `<span class="highlight">SPECTRAL ANALYSIS: ${r.contact_id}</span>
<span class="label">Drive Type:</span> <span class="value">${drive.drive_type || "unknown"}</span>
<span class="label">Burn State:</span> <span class="value">${drive.burn_state || "?"}</span>
<span class="label">Est. Thrust:</span> <span class="value">${drive.estimated_thrust_kn ? drive.estimated_thrust_kn + " kN" : "?"}</span>
<span class="label">Total IR:</span> <span class="value">${ir.total_ir ? this._formatPower(ir.total_ir) : "?"}</span>
<span class="label">Plume IR:</span> <span class="value">${ir.plume_ir ? this._formatPower(ir.plume_ir) : "0"}</span>
<span class="label">Radiator/Hull:</span> <span class="value">${ir.radiator_hull_ir ? this._formatPower(ir.radiator_hull_ir) : "?"}</span>
<span class="label">Burning:</span> <span class="value">${ir.is_burning ? "YES" : "no"}</span>
<span class="label">Post-burn Decay:</span> <span class="value">${ir.post_burn_decay ? "YES" : "no"}</span>
<span class="label">RCS:</span> <span class="value">${rcs.effective_rcs ? rcs.effective_rcs.toFixed(1) + " m\u00B2" : "?"}</span>
<span class="label">EMCON Detected:</span> <span class="value">${rcs.emcon_detected ? "YES" : "no"}</span>`;
  }

  _formatMass(r) {
    const me = r.mass_estimate || {};
    const di = r.dimension_inference || {};
    return `<span class="highlight">MASS ESTIMATE: ${r.contact_id}</span>
<span class="label">Estimated Mass:</span> <span class="value">${me.estimated_mass ? this._formatMassKg(me.estimated_mass) : "?"}</span>
<span class="label">Confidence:</span> <span class="value">${me.confidence || "?"}</span>
<span class="label">Method:</span> <span class="value">${me.method || "?"}</span>
<span class="label">Range:</span> <span class="value">${me.range_low && me.range_high ? this._formatMassKg(me.range_low) + " -- " + this._formatMassKg(me.range_high) : "?"}</span>
<span class="label">Ship Class:</span> <span class="value">${di.ship_class || "?"}</span>
<span class="label">Est. Length:</span> <span class="value">${di.estimated_length ? di.estimated_length.toFixed(0) + " m" : "?"}</span>`;
  }

  _formatThreat(r) {
    const ta = r.threat_assessment || {};
    const cm = ta.countermeasures || {};
    const threatClass = `threat-${ta.overall_threat || "unknown"}`;
    const recs = r.recommendations || [];
    return `<span class="highlight">THREAT ASSESSMENT: ${r.contact_id}</span>
<span class="label">Overall:</span> <span class="${threatClass}">${(ta.overall_threat || "?").toUpperCase()} (${ta.threat_score || 0}/100)</span>
<span class="label">Weapons:</span> <span class="value">${ta.weapons_threat || "?"}</span>
<span class="label">Armor:</span> <span class="value">${ta.armor_threat || "?"}</span>
<span class="label">Mobility:</span> <span class="value">${ta.mobility_threat || "?"}</span>
<span class="label">ECM Active:</span> <span class="value">${cm.ecm_detected ? "YES" : "no"}</span>
<span class="label">EMCON:</span> <span class="value">${cm.emcon_active ? "YES" : "no"}</span>
<span class="label">Notes:</span> <span class="value">${ta.tactical_notes || "none"}</span>
${recs.length > 0 ? '\n<span class="highlight">RECOMMENDATIONS:</span>\n' + recs.map(r => `- ${r}`).join("\n") : ""}`;
  }

  _formatSpectralScan(r) {
    const sd = r.spectral_scan || {};
    const isp = sd.estimated_isp_range || [0, 0];
    const conf = sd.drive_type_confidence ?? 0;
    return `<span class="highlight">SPECTRAL SCAN: ${r.contact_id}</span>
<span class="label">Drive Type:</span> <span class="value">${sd.drive_type || "unknown"}</span>
<span class="label">Drive Confidence:</span> <span class="value">${(conf * 100).toFixed(0)}%</span>
<span class="label">Est. ISP Range:</span> <span class="value">${isp[0].toLocaleString()} -- ${isp[1].toLocaleString()} s</span>
<span class="label">Est. Max Accel:</span> <span class="value">${sd.estimated_max_accel ? sd.estimated_max_accel.toFixed(1) + " m/s\u00B2" : "?"}</span>
<span class="label">Scan Quality:</span> <span class="value">${sd.scan_quality ? (sd.scan_quality * 100).toFixed(0) + "%" : "?"}</span>
<span class="label">Range:</span> <span class="value">${sd.range_km ? sd.range_km.toFixed(1) + " km" : "?"}</span>`;
  }

  _formatCompositionScan(r) {
    const cd = r.composition_scan || {};
    const conf = cd.class_confidence ?? 0;
    return `<span class="highlight">COMPOSITION SCAN: ${r.contact_id}</span>
<span class="label">Armor Type:</span> <span class="value">${cd.armor_type || "unknown"}</span>
<span class="label">Armor Thickness:</span> <span class="value">${cd.armor_thickness_estimate ? cd.armor_thickness_estimate.toFixed(1) + " mm" : "?"}</span>
<span class="label">Ship Class:</span> <span class="value">${cd.estimated_ship_class || "unknown"}</span>
<span class="label">Class Confidence:</span> <span class="value">${(conf * 100).toFixed(0)}%</span>
<span class="label">Est. Mass:</span> <span class="value">${cd.estimated_mass ? this._formatMassKg(cd.estimated_mass) : "?"}</span>
<span class="label">Scan Quality:</span> <span class="value">${cd.scan_quality ? (cd.scan_quality * 100).toFixed(0) + "%" : "?"}</span>
<span class="label">Range:</span> <span class="value">${cd.range_km ? cd.range_km.toFixed(1) + " km" : "?"}</span>`;
  }

  // =========================================================================
  //  UTILITY
  // =========================================================================

  _formatPower(watts) {
    if (watts >= 1e6) return `${(watts / 1e6).toFixed(1)} MW`;
    if (watts >= 1e3) return `${(watts / 1e3).toFixed(1)} kW`;
    return `${watts.toFixed(0)} W`;
  }

  _formatMassKg(kg) {
    if (kg >= 1000) return `${(kg / 1000).toFixed(1)}t`;
    return `${kg.toFixed(0)} kg`;
  }

  /** Infer a threat level from contact data for badge display */
  _inferThreatLevel(contact) {
    const faction = (contact.faction || contact.iff || "").toLowerCase();
    if (faction === "hostile" || faction === "enemy") return "high";
    if (faction === "friendly" || faction === "allied") return "minimal";

    // Heuristic: closing fast + armed = moderate-high
    const rangeRate = contact.range_rate ?? contact.closure ?? 0;
    const range = contact.range ?? contact.distance ?? 99999;
    if (rangeRate < -500 && range < 20000) return "high";
    if (rangeRate < -100 && range < 50000) return "moderate";
    if (range < 10000) return "moderate";
    return "low";
  }

  /** Numeric threat score for sorting (higher = more threatening) */
  _threatScore(contact) {
    const levels = { critical: 5, high: 4, moderate: 3, low: 2, minimal: 1 };
    return levels[this._inferThreatLevel(contact)] || 0;
  }
}

customElements.define("science-analysis-panel", ScienceAnalysisPanel);
