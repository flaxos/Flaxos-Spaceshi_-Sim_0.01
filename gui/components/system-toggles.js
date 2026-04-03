/**
 * System Power Toggles
 * Toggle switches for ship systems.
 *
 * Tier awareness:
 *   MANUAL/RAW: Individual on/off toggles with raw power draw (kW) per system.
 *   ARCADE:     Simplified toggle labels ("SENSORS ON/OFF"), no power numbers.
 *   CPU-ASSIST: Hidden by tiers.css (auto-ops manages priority). Renders read-only fallback if forced visible.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const DEFAULT_SYSTEMS = [
  { id: "propulsion", name: "Propulsion", critical: true },
  { id: "sensors", name: "Sensors", critical: false },
  { id: "weapons", name: "Weapons", critical: false },
  { id: "navigation", name: "Navigation", critical: false },
  { id: "comms", name: "Comms", critical: false },
];

class SystemToggles extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._systemStates = {};
    this._tierHandler = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._tierHandler = () => { this.render(); this._updateDisplay(); };
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

  _getTier() {
    return window.controlTier || "arcade";
  }

  render() {
    const tier = this._getTier();
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._tierStyles(tier)}</style>
      <div class="systems-list" id="systems-list"></div>
      ${tier !== "cpu-assist" ? `
      <div class="confirm-dialog hidden" id="confirm-dialog">
        <div class="confirm-box">
          <div class="confirm-title">Critical System</div>
          <div class="confirm-message" id="confirm-message">
            Are you sure you want to disable this system?
          </div>
          <div class="confirm-buttons">
            <button class="confirm-btn confirm-no" id="confirm-no">Cancel</button>
            <button class="confirm-btn confirm-yes" id="confirm-yes">Confirm</button>
          </div>
        </div>
      </div>` : ""}
    `;

    if (tier !== "cpu-assist") {
      this._setupConfirmDialog();
    }
    this._renderSystems();
  }

  _setupConfirmDialog() {
    const dialog = this.shadowRoot.getElementById("confirm-dialog");
    const yesBtn = this.shadowRoot.getElementById("confirm-yes");
    const noBtn = this.shadowRoot.getElementById("confirm-no");
    if (!dialog || !yesBtn || !noBtn) return;

    noBtn.addEventListener("click", () => {
      dialog.classList.add("hidden");
      this._pendingToggle = null;
    });

    yesBtn.addEventListener("click", () => {
      if (this._pendingToggle) {
        this._doToggle(this._pendingToggle.systemId, this._pendingToggle.newState);
      }
      dialog.classList.add("hidden");
      this._pendingToggle = null;
    });
  }

  _renderSystems() {
    const list = this.shadowRoot.getElementById("systems-list");
    const systems = this._getSystems();
    const tier = this._getTier();

    if (tier === "cpu-assist") {
      // Read-only summary: auto-ops manages
      list.innerHTML = `
        <div class="assist-note">System priority managed by auto-ops.</div>
        ${systems.map(system => `
          <div class="system-row readonly">
            <div class="system-info">
              <span class="system-indicator ${this._getIndicatorClass(system.state)}"></span>
              <span class="system-name">${system.name}</span>
            </div>
            <span class="readonly-label ${system.enabled ? 'on' : 'off'}">${system.enabled ? 'ON' : 'OFF'}</span>
          </div>
        `).join("")}
      `;
      return;
    }

    const showPowerDraw = tier === "manual" || tier === "raw";

    list.innerHTML = systems.map(system => {
      // Estimated power draw per system (derive from state if available, else defaults)
      const powerDraw = showPowerDraw ? this._getSystemPowerDraw(system.id) : null;
      const powerLabel = powerDraw !== null ? `<span class="power-draw">${powerDraw.toFixed(1)} kW</span>` : "";

      return `
        <div class="system-row" data-system="${system.id}">
          <div class="system-info">
            <span class="system-indicator ${this._getIndicatorClass(system.state)}"></span>
            <span class="system-name ${system.critical ? 'critical' : ''}">${tier === "arcade" ? system.name.toUpperCase() : system.name}</span>
            ${powerLabel}
          </div>
          <div class="toggle-switch ${system.enabled ? 'on' : ''}" data-system="${system.id}"></div>
        </div>
      `;
    }).join("");

    // Add click handlers for toggles
    list.querySelectorAll(".toggle-switch").forEach(toggle => {
      toggle.addEventListener("click", () => {
        const systemId = toggle.dataset.system;
        const system = systems.find(s => s.id === systemId);
        const newState = !system.enabled;

        if (system.critical && !newState) {
          this._showConfirmDialog(system, newState);
        } else {
          this._doToggle(systemId, newState);
        }
      });
    });
  }

  _getSystems() {
    const shipSystems = stateManager.getSystems();
    const systemsList = [];

    for (const defaultSystem of DEFAULT_SYSTEMS) {
      const state = this._getSystemState(shipSystems, defaultSystem.id);
      systemsList.push({
        ...defaultSystem,
        state: state.status,
        enabled: state.enabled,
      });
    }

    return systemsList;
  }

  _getSystemState(systems, systemId) {
    const system = systems[systemId] || systems[`${systemId}_system`];

    if (system === undefined) {
      return { status: "unknown", enabled: true };
    }

    if (typeof system === "boolean") {
      return { status: system ? "online" : "offline", enabled: system };
    }

    if (typeof system === "string") {
      const s = system.toLowerCase();
      const enabled = s !== "offline" && s !== "off" && s !== "disabled";
      return { status: s, enabled };
    }

    if (typeof system === "object" && system !== null) {
      const enabled = system.enabled !== false && system.status !== "offline";
      return { status: system.status || (enabled ? "online" : "offline"), enabled };
    }

    return { status: "unknown", enabled: true };
  }

  /** Estimate per-system power draw from state. Returns kW or null. */
  _getSystemPowerDraw(systemId) {
    const ship = stateManager.getShipState();
    const ops = ship?.ops;
    if (ops?.power_draw && ops.power_draw[systemId] !== undefined) {
      return ops.power_draw[systemId];
    }
    // Fallback: rough estimates by system type
    const DEFAULTS = {
      propulsion: 25.0, sensors: 8.0, weapons: 15.0, navigation: 3.0, comms: 2.0,
    };
    return DEFAULTS[systemId] ?? 5.0;
  }

  _getIndicatorClass(status) {
    const s = (status || "").toLowerCase();
    if (s === "online" || s === "active" || s === "ready") return "online";
    if (s === "warning" || s === "degraded") return "warning";
    if (s === "error" || s === "failed" || s === "critical") return "error";
    return "";
  }

  _showConfirmDialog(system, newState) {
    const dialog = this.shadowRoot.getElementById("confirm-dialog");
    const message = this.shadowRoot.getElementById("confirm-message");
    if (!dialog || !message) return;

    message.textContent = `Are you sure you want to ${newState ? 'enable' : 'disable'} ${system.name}?`;
    this._pendingToggle = { systemId: system.id, newState };

    dialog.classList.remove("hidden");
  }

  async _doToggle(systemId, newState) {
    const toggle = this.shadowRoot.querySelector(`.toggle-switch[data-system="${systemId}"]`);
    if (toggle) {
      toggle.classList.add("pending");
    }

    try {
      await wsClient.sendShipCommand("toggle_system", {
        system: systemId,
        state: newState ? 1 : 0
      });
    } catch (error) {
      console.error(`System toggle failed for ${systemId}:`, error);
    } finally {
      if (toggle) {
        toggle.classList.remove("pending");
      }
    }
  }

  _updateDisplay() {
    this._renderSystems();
  }

  // ---------------------------------------------------------------------------
  // Styles
  // ---------------------------------------------------------------------------

  _baseStyles() {
    return `
      :host {
        display: block;
        padding: 16px;
        font-family: var(--font-sans, "Inter", sans-serif);
      }
      .systems-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .system-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 12px;
        background: var(--bg-input, #1a1a24);
        border-radius: 8px;
        transition: background 0.1s ease;
      }
      .system-row:hover {
        background: var(--bg-hover, #22222e);
      }
      .system-info {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .system-indicator {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--status-offline, #555566);
        transition: all 0.2s ease;
      }
      .system-indicator.online {
        background: var(--status-nominal, #00ff88);
        box-shadow: 0 0 6px var(--status-nominal, #00ff88);
      }
      .system-indicator.warning {
        background: var(--status-warning, #ffaa00);
        box-shadow: 0 0 6px var(--status-warning, #ffaa00);
      }
      .system-indicator.error {
        background: var(--status-critical, #ff4444);
        box-shadow: 0 0 6px var(--status-critical, #ff4444);
      }
      .system-name {
        font-size: 0.85rem;
        color: var(--text-primary, #e0e0e0);
      }
      .toggle-switch {
        position: relative;
        width: 44px;
        height: 24px;
        background: var(--bg-primary, #0a0a0f);
        border-radius: 12px;
        cursor: pointer;
        transition: background 0.2s ease;
        flex-shrink: 0;
      }
      .toggle-switch.on {
        background: var(--status-nominal, #00ff88);
      }
      .toggle-switch::before {
        content: '';
        position: absolute;
        top: 3px;
        left: 3px;
        width: 18px;
        height: 18px;
        background: var(--text-primary, #e0e0e0);
        border-radius: 50%;
        transition: transform 0.2s ease;
      }
      .toggle-switch.on::before {
        transform: translateX(20px);
        background: var(--bg-primary, #0a0a0f);
      }
      .toggle-switch.pending {
        opacity: 0.6;
        pointer-events: none;
      }
      .confirm-dialog {
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
      }
      .confirm-dialog.hidden { display: none; }
      .confirm-box {
        background: var(--bg-panel, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 12px;
        padding: 24px;
        max-width: 300px;
        text-align: center;
      }
      .confirm-title {
        font-size: 1rem;
        font-weight: 600;
        color: var(--status-warning, #ffaa00);
        margin-bottom: 8px;
      }
      .confirm-message {
        font-size: 0.85rem;
        color: var(--text-secondary, #888899);
        margin-bottom: 16px;
      }
      .confirm-buttons {
        display: flex;
        gap: 8px;
      }
      .confirm-btn {
        flex: 1;
        padding: 10px 16px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        cursor: pointer;
        min-height: 44px;
      }
      .confirm-yes {
        background: var(--status-warning, #ffaa00);
        border: none;
        color: var(--bg-primary, #0a0a0f);
      }
      .confirm-no {
        background: transparent;
        border: 1px solid var(--border-default, #2a2a3a);
        color: var(--text-primary, #e0e0e0);
      }
    `;
  }

  _tierStyles(tier) {
    if (tier === "manual") return this._manualStyles();
    if (tier === "raw") return this._rawStyles();
    if (tier === "cpu-assist") return this._cpuAssistStyles();
    return this._arcadeStyles();
  }

  _manualStyles() {
    return `
      :host { font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .system-row { border-radius: 0; border-left: 2px solid #ff8800; }
      .system-name { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; font-size: 0.75rem; }
      .power-draw {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        color: #ff880088;
      }
      .toggle-switch { border-radius: 2px; }
      .toggle-switch::before { border-radius: 2px; }
      .toggle-switch.on { background: #ff8800; }
      .confirm-box { border-radius: 0; }
    `;
  }

  _rawStyles() {
    return `
      :host { font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .system-row { border-radius: 0; }
      .system-name { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; font-size: 0.8rem; }
      .power-draw {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        color: var(--text-dim, #666);
      }
      .toggle-switch { border-radius: 4px; }
      .toggle-switch::before { border-radius: 4px; }
      .toggle-switch.on { background: #ff4444; }
      .confirm-box { border-radius: 0; }
    `;
  }

  _arcadeStyles() {
    return `
      .system-name {
        font-weight: 600;
        letter-spacing: 0.5px;
      }
      .system-row {
        border-radius: 10px;
      }
      .power-draw { display: none; }
    `;
  }

  _cpuAssistStyles() {
    return `
      .assist-note {
        font-size: 0.75rem;
        color: var(--text-dim, #666);
        font-style: italic;
        text-align: center;
        padding: 4px 0 10px;
      }
      .system-row.readonly {
        opacity: 0.7;
        cursor: default;
      }
      .system-row.readonly:hover {
        background: var(--bg-input, #1a1a24);
      }
      .readonly-label {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 6px;
      }
      .readonly-label.on {
        background: rgba(0, 255, 136, 0.12);
        color: var(--status-nominal, #00ff88);
      }
      .readonly-label.off {
        background: rgba(85, 85, 102, 0.15);
        color: var(--text-dim, #555566);
      }
    `;
  }
}

customElements.define("system-toggles", SystemToggles);
export { SystemToggles };
