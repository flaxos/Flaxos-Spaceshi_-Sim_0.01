/**
 * Fleet Formation Control
 * Manages formation type, spacing, and parameters for fleet maneuvers.
 */

import { wsClient } from "../js/ws-client.js";

const FORMATIONS = [
  { id: "line",    label: "LINE",    preview: "  *\n  *\n  *\n  *" },
  { id: "column",  label: "COLUMN",  preview: "* * * *\n       \n       \n       " },
  { id: "wall",    label: "WALL",    preview: "* * *\n* * *\n     \n     " },
  { id: "sphere",  label: "SPHERE",  preview: "  * *  \n *   * \n *   * \n  * *  " },
  { id: "wedge",   label: "WEDGE",   preview: "    *   \n  *   * \n*       *\n        " },
  { id: "echelon", label: "ECHELON", preview: "*      \n  *    \n    *  \n      *" },
  { id: "diamond", label: "DIAMOND", preview: "   *   \n *   * \n   *   \n       " },
];

class FormationControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._selected = null;
    this._spacing = 2000;
    this._wallColumns = 3;
    this._echelonAngle = 30;
    this._currentFormation = null;
    this._fleetId = null;
    this._pollInterval = null;
    this._onMessage = null;
  }

  connectedCallback() {
    this._render();
    this._setupListeners();
    this._onMessage = (e) => this._handleServerUpdate(e.detail);
    wsClient.addEventListener("message", this._onMessage);
    // Poll fleet status periodically
    wsClient.sendShipCommand("fleet_status", {});
    this._pollInterval = setInterval(() => {
      wsClient.sendShipCommand("fleet_status", {});
    }, 5000);
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
    if (this._onMessage) {
      wsClient.removeEventListener("message", this._onMessage);
      this._onMessage = null;
    }
  }

  _handleServerUpdate(data) {
    if (data?.type === "fleet_status" || data?.command === "fleet_status") {
      this._currentFormation = data.formation || null;
      this._fleetId = data.fleet_id || this._fleetId;
      this._updateStatusBadge();
    }
  }

  _updateStatusBadge() {
    const badge = this.shadowRoot.querySelector(".status-badge");
    if (!badge) return;
    if (this._currentFormation) {
      badge.textContent = this._currentFormation.toUpperCase();
      badge.className = "status-badge active";
    } else {
      badge.textContent = "NO FORMATION";
      badge.className = "status-badge inactive";
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 12px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
          background: var(--bg-panel, #12121a);
        }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
        .title { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-secondary, #a0a0b0); }
        .status-badge {
          font-size: 11px; padding: 2px 8px; border-radius: 3px;
          border: 1px solid var(--border-default, #2a2a3a);
        }
        .status-badge.active { color: var(--status-nominal, #00ff88); border-color: var(--status-nominal, #00ff88); }
        .status-badge.inactive { color: var(--text-dim, #666680); }
        .grid {
          display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
          margin-bottom: 12px;
        }
        .grid button:last-child:nth-child(odd) { grid-column: span 2; }
        .form-btn {
          background: var(--bg-input, #1a1a2e); border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-primary, #e0e0e0); padding: 6px 8px; cursor: pointer;
          font-family: inherit; font-size: 12px; border-radius: 3px;
          transition: border-color 0.15s;
        }
        .form-btn:hover { border-color: var(--status-info, #4488ff); }
        .form-btn.selected { border-color: var(--status-info, #4488ff); background: #1a2a4a; }
        .preview {
          background: var(--bg-input, #1a1a2e); border: 1px solid var(--border-default, #2a2a3a);
          padding: 8px 12px; margin-bottom: 12px; font-size: 12px;
          line-height: 1.4; white-space: pre; text-align: center;
          color: var(--status-info, #4488ff); border-radius: 3px;
          min-height: 60px; display: flex; align-items: center; justify-content: center;
        }
        .slider-row { margin-bottom: 10px; }
        .slider-label {
          display: flex; justify-content: space-between; font-size: 11px;
          color: var(--text-dim, #666680); margin-bottom: 4px;
        }
        .slider-label .val { color: var(--text-primary, #e0e0e0); }
        input[type="range"] {
          width: 100%; accent-color: var(--status-info, #4488ff);
          background: transparent; cursor: pointer;
        }
        .extra-params { margin-bottom: 12px; }
        .param-row {
          display: flex; align-items: center; gap: 8px;
          font-size: 11px; color: var(--text-dim, #666680); margin-bottom: 6px;
        }
        .param-row input {
          width: 60px; background: var(--bg-input, #1a1a2e);
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-primary, #e0e0e0); padding: 3px 6px;
          font-family: inherit; font-size: 11px; border-radius: 3px;
        }
        .actions { display: flex; gap: 8px; }
        .actions button {
          flex: 1; padding: 8px; border: none; cursor: pointer;
          font-family: inherit; font-size: 12px; font-weight: bold;
          border-radius: 3px; text-transform: uppercase;
        }
        .btn-form { background: #114422; color: var(--status-nominal, #00ff88); }
        .btn-form:hover { background: #1a6633; }
        .btn-form:disabled { opacity: 0.4; cursor: not-allowed; }
        .btn-break { background: #441111; color: var(--status-critical, #ff4444); }
        .btn-break:hover { background: #662222; }
      </style>
      <div class="header">
        <span class="title">Formation</span>
        <span class="status-badge inactive">NO FORMATION</span>
      </div>
      <div class="preview"><span class="preview-text">Select a formation</span></div>
      <div class="grid">
        ${FORMATIONS.map(f => `<button class="form-btn" data-id="${f.id}">${f.label}</button>`).join("")}
      </div>
      <div class="slider-row">
        <div class="slider-label"><span>Spacing</span><span class="val spacing-val">2000m</span></div>
        <input type="range" min="500" max="10000" step="100" value="2000" class="spacing-slider">
      </div>
      <div class="extra-params"></div>
      <div class="actions">
        <button class="btn-form" disabled>FORM UP</button>
        <button class="btn-break">BREAK</button>
      </div>
    `;
  }

  _setupListeners() {
    const root = this.shadowRoot;
    // Formation type selection
    root.querySelectorAll(".form-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        root.querySelectorAll(".form-btn").forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
        this._selected = btn.dataset.id;
        root.querySelector(".btn-form").disabled = false;
        this._updatePreview();
        this._updateExtraParams();
      });
    });
    // Spacing slider
    const slider = root.querySelector(".spacing-slider");
    slider.addEventListener("input", () => {
      this._spacing = parseInt(slider.value, 10);
      root.querySelector(".spacing-val").textContent = `${this._spacing}m`;
    });
    // Form up
    root.querySelector(".btn-form").addEventListener("click", () => this._formUp());
    // Break formation
    root.querySelector(".btn-break").addEventListener("click", () => this._breakFormation());
  }

  _updatePreview() {
    const info = FORMATIONS.find(f => f.id === this._selected);
    const el = this.shadowRoot.querySelector(".preview-text");
    el.textContent = info ? info.preview : "Select a formation";
  }

  _updateExtraParams() {
    const container = this.shadowRoot.querySelector(".extra-params");
    if (this._selected === "wall") {
      container.innerHTML = `<div class="param-row">
        <span>Wall columns:</span>
        <input type="number" min="2" max="10" value="${this._wallColumns}" class="wall-cols-input">
      </div>`;
      container.querySelector(".wall-cols-input").addEventListener("input", (e) => {
        this._wallColumns = parseInt(e.target.value, 10) || 3;
      });
    } else if (this._selected === "echelon") {
      container.innerHTML = `<div class="param-row">
        <span>Echelon angle (deg):</span>
        <input type="number" min="10" max="80" value="${this._echelonAngle}" class="ech-angle-input">
      </div>`;
      container.querySelector(".ech-angle-input").addEventListener("input", (e) => {
        this._echelonAngle = parseInt(e.target.value, 10) || 30;
      });
    } else {
      container.innerHTML = "";
    }
  }

  _formUp() {
    if (!this._selected) return;
    const params = {
      fleet_id: this._fleetId,
      formation: this._selected,
      spacing: this._spacing,
    };
    if (this._selected === "wall") params.wall_columns = this._wallColumns;
    if (this._selected === "echelon") params.echelon_angle = this._echelonAngle;
    wsClient.sendShipCommand("fleet_form", params);
  }

  _breakFormation() {
    wsClient.sendShipCommand("fleet_break_formation", { fleet_id: this._fleetId });
  }
}

customElements.define("formation-control", FormationControl);
