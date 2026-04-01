/**
 * Ship Class Editor — Main Coordinator Component
 * Orchestrates the 3-column layout (hull, systems, preview) and handles
 * save/load/validate/export actions via the server protocol.
 *
 * Server commands used:
 *   - get_ship_classes_full (meta) — returns all ship class full configs
 *   - save_ship_class (meta)       — persists a ship class JSON to disk
 */

import { wsClient } from "../js/ws-client.js";
import "./ship-editor-hull.js";
import "./ship-editor-systems.js";
import "./ship-editor-preview.js";

class ShipEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._fullTemplates = []; // full ship class configs from server
  }

  connectedCallback() {
    this.render();
    this._bindEvents();
  }

  /** Fetch full ship class configs from the server and populate the template selector. */
  async loadTemplates() {
    try {
      const resp = await wsClient.send("get_ship_classes_full", {});
      if (resp?.ok && resp.ship_classes) {
        this._fullTemplates = resp.ship_classes;
        const hull = this.shadowRoot.querySelector("ship-editor-hull");
        if (hull) hull.templates = this._fullTemplates;
      }
    } catch (err) {
      console.warn("ShipEditor: failed to fetch ship classes", err);
    }
  }

  /** Collect the entire ship class config from all sub-components. */
  _collectConfig() {
    const hull = this.shadowRoot.querySelector("ship-editor-hull");
    const sys = this.shadowRoot.querySelector("ship-editor-systems");
    const preview = this.shadowRoot.querySelector("ship-editor-preview");

    const hullCfg = hull?.getConfig() || {};
    const sysCfg = sys?.getConfig() || {};
    const damageModel = preview?.getDamageModel() || {};

    return {
      ...hullCfg,
      systems: sysCfg.systems || {},
      weapon_mounts: sysCfg.weapon_mounts || [],
      damage_model: damageModel,
    };
  }

  /** Trigger preview recomputation from current field state. */
  _refreshPreview() {
    const cfg = this._collectConfig();
    const preview = this.shadowRoot.querySelector("ship-editor-preview");
    if (preview) preview.updatePreview(cfg);
  }

  /** Client-side validation. Returns true if valid, shows errors otherwise. */
  _validate() {
    const hull = this.shadowRoot.querySelector("ship-editor-hull");
    const errors = hull?.validate() || [];
    const cfg = this._collectConfig();

    // Mass plausibility
    if (cfg.mass?.dry_mass > 0 && cfg.mass?.max_fuel > cfg.mass.dry_mass * 10) {
      errors.push("Fuel mass exceeds 10x dry mass (implausible)");
    }
    // At least one system
    if (Object.keys(cfg.systems || {}).length === 0) {
      errors.push("At least one system must be enabled");
    }

    const msgEl = this.shadowRoot.getElementById("status-msg");
    if (errors.length > 0) {
      msgEl.textContent = "ERRORS: " + errors.join("; ");
      msgEl.className = "status-msg error";
      return false;
    }
    msgEl.textContent = "Validation passed";
    msgEl.className = "status-msg success";
    return true;
  }

  /** Save the ship class to the server. */
  async _save() {
    if (!this._validate()) return;
    const cfg = this._collectConfig();
    const msgEl = this.shadowRoot.getElementById("status-msg");
    try {
      msgEl.textContent = "Saving...";
      msgEl.className = "status-msg info";
      const resp = await wsClient.send("save_ship_class", { config: cfg });
      if (resp?.ok) {
        msgEl.textContent = `Saved "${cfg.class_id}" successfully`;
        msgEl.className = "status-msg success";
        // Refresh templates
        await this.loadTemplates();
      } else {
        msgEl.textContent = "Save failed: " + (resp?.error || "unknown error");
        msgEl.className = "status-msg error";
      }
    } catch (err) {
      msgEl.textContent = "Save error: " + err.message;
      msgEl.className = "status-msg error";
    }
  }

  /** Export the current config as a downloaded JSON file. */
  _export() {
    if (!this._validate()) return;
    const cfg = this._collectConfig();
    const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${cfg.class_id || "ship_class"}.json`;
    a.click();
    URL.revokeObjectURL(url);

    const msgEl = this.shadowRoot.getElementById("status-msg");
    msgEl.textContent = `Exported ${a.download}`;
    msgEl.className = "status-msg success";
  }

  /** Load template button — open the hull selector dropdown programmatically. */
  _loadTemplate() {
    const hull = this.shadowRoot.querySelector("ship-editor-hull");
    const sel = hull?.shadowRoot?.querySelector("#hull-selector");
    if (sel) {
      sel.focus();
      sel.click();
    }
  }

  _bindEvents() {
    // Bottom bar buttons
    this.shadowRoot.getElementById("btn-save").addEventListener("click", () => this._save());
    this.shadowRoot.getElementById("btn-validate").addEventListener("click", () => this._validate());
    this.shadowRoot.getElementById("btn-export").addEventListener("click", () => this._export());
    this.shadowRoot.getElementById("btn-load").addEventListener("click", () => this._loadTemplate());

    // Listen for sub-component changes to refresh preview
    this.shadowRoot.addEventListener("hull-changed", () => this._refreshPreview());
    this.shadowRoot.addEventListener("systems-changed", () => this._refreshPreview());
    this.shadowRoot.addEventListener("preview-changed", () => this._refreshPreview());

    // When a template is loaded, propagate to systems + preview sub-components
    this.shadowRoot.addEventListener("template-loaded", (e) => {
      const cfg = e.detail?.config;
      if (cfg) {
        const sys = this.shadowRoot.querySelector("ship-editor-systems");
        const preview = this.shadowRoot.querySelector("ship-editor-preview");
        if (sys) sys.loadConfig(cfg);
        if (preview) preview.loadConfig(cfg);
        this._refreshPreview();
      }
    });

    // Fetch templates once connected (or immediately if already connected)
    if (wsClient.isConnected) {
      this.loadTemplates();
    }
    wsClient.addEventListener("status_change", (e) => {
      if (e.detail?.status === "connected") this.loadTemplates();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .editor-layout {
          display: grid;
          grid-template-columns: 4fr 4fr 4fr;
          gap: 12px;
          padding: 12px;
          height: calc(100% - 56px);
          overflow: hidden;
        }

        .editor-column {
          overflow-y: auto;
          padding-right: 4px;
        }

        /* Scrollbar styling */
        .editor-column::-webkit-scrollbar { width: 5px; }
        .editor-column::-webkit-scrollbar-track { background: transparent; }
        .editor-column::-webkit-scrollbar-thumb { background: var(--border-default, #2a2a3a); border-radius: 3px; }

        .column-header {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 600;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--status-info, #00aaff);
          margin: 0 0 10px;
          padding-bottom: 6px;
          border-bottom: 2px solid var(--status-info, #00aaff);
        }

        /* Bottom bar */
        .bottom-bar {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          background: var(--bg-panel, #12121a);
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .bottom-bar button {
          padding: 8px 18px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.78rem;
          font-weight: 600;
          letter-spacing: 0.06em;
          border-radius: 4px;
          cursor: pointer;
          transition: all 0.15s ease;
          border: 1px solid;
        }

        .btn-primary {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: #000;
        }
        .btn-primary:hover { filter: brightness(1.15); }

        .btn-secondary {
          background: transparent;
          border-color: var(--border-active, #3a3a4a);
          color: var(--text-primary, #e0e0e0);
        }
        .btn-secondary:hover { background: var(--bg-hover, #22222e); }

        .btn-accent {
          background: transparent;
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }
        .btn-accent:hover { background: rgba(0,255,136,0.08); }

        .status-msg {
          flex: 1;
          font-size: 0.72rem;
          font-family: var(--font-mono, monospace);
          color: var(--text-dim, #555566);
        }
        .status-msg.error { color: var(--status-critical, #ff4444); }
        .status-msg.success { color: var(--status-nominal, #00ff88); }
        .status-msg.info { color: var(--status-info, #00aaff); }

        @media (max-width: 900px) {
          .editor-layout {
            grid-template-columns: 1fr;
            height: auto;
            overflow: auto;
          }
        }
      </style>

      <div class="editor-layout">
        <div class="editor-column">
          <div class="column-header">Hull Configuration</div>
          <ship-editor-hull></ship-editor-hull>
        </div>
        <div class="editor-column">
          <div class="column-header">Systems & Weapons</div>
          <ship-editor-systems></ship-editor-systems>
        </div>
        <div class="editor-column">
          <div class="column-header">Preview & Damage</div>
          <ship-editor-preview></ship-editor-preview>
        </div>
      </div>

      <div class="bottom-bar">
        <button class="btn-primary" id="btn-save">SAVE</button>
        <button class="btn-secondary" id="btn-load">LOAD TEMPLATE</button>
        <button class="btn-secondary" id="btn-validate">VALIDATE</button>
        <button class="btn-accent" id="btn-export">EXPORT JSON</button>
        <span class="status-msg" id="status-msg"></span>
      </div>
    `;
  }
}

customElements.define("ship-editor", ShipEditor);
export { ShipEditor };
