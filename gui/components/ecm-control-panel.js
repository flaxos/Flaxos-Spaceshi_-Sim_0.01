/**
 * ECM Control Panel
 * Provides interactive controls for electronic countermeasures:
 * - Radar jammer toggle
 * - Chaff deployment
 * - Flare deployment
 * - EMCON mode toggle
 * - Status readout
 */

import { stateManager } from "../js/state-manager.js";

class ECMControlPanel extends HTMLElement {
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

  async _sendCommand(cmd, args = {}) {
    if (window.flaxosApp && window.flaxosApp.sendCommand) {
      return window.flaxosApp.sendCommand(cmd, args);
    }
    return null;
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 12px;
        }

        .section {
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--status-info, #00aaff);
          margin-bottom: 8px;
          padding-bottom: 4px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .status-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 0;
          font-size: 0.75rem;
        }

        .status-label {
          color: var(--text-secondary, #888899);
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
        }

        .status-value.active {
          color: var(--status-nominal, #00ff88);
        }

        .status-value.warning {
          color: var(--status-warning, #ffaa00);
        }

        .status-value.critical {
          color: var(--status-critical, #ff4444);
        }

        .status-value.emcon {
          color: var(--status-info, #00aaff);
        }

        /* ECM Mode indicator */
        .ecm-mode {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 10px;
          margin-bottom: 12px;
          border-radius: 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .ecm-mode.standby {
          background: rgba(85, 85, 102, 0.15);
          border: 1px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }

        .ecm-mode.active {
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .ecm-mode.emcon {
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
        }

        .mode-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: currentColor;
        }

        .ecm-mode.active .mode-dot {
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        /* Control buttons */
        .controls-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
          margin-top: 8px;
        }

        .ecm-btn {
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid rgba(0, 170, 255, 0.3);
          border-radius: 4px;
          color: var(--status-info, #00aaff);
          padding: 8px 10px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          cursor: pointer;
          text-transform: uppercase;
          transition: all 0.15s ease;
          text-align: center;
          min-height: 36px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 2px;
        }

        .ecm-btn:hover {
          background: rgba(0, 170, 255, 0.2);
          border-color: var(--status-info, #00aaff);
        }

        .ecm-btn.active {
          background: rgba(0, 255, 136, 0.15);
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .ecm-btn.emcon-active {
          background: rgba(0, 170, 255, 0.2);
          border-color: var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
        }

        .ecm-btn.disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .ecm-btn.full-width {
          grid-column: 1 / -1;
        }

        .btn-count {
          font-size: 0.6rem;
          opacity: 0.7;
        }

        /* Countermeasure bars */
        .cm-bar-container {
          margin-top: 4px;
        }

        .cm-bar-label {
          display: flex;
          justify-content: space-between;
          font-size: 0.65rem;
          margin-bottom: 2px;
        }

        .cm-bar-label-name {
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
        }

        .cm-bar-label-count {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
        }

        .cm-bar {
          height: 4px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 2px;
          overflow: hidden;
        }

        .cm-bar-fill {
          height: 100%;
          border-radius: 2px;
          transition: width 0.3s ease;
        }

        .cm-bar-fill.chaff {
          background: var(--status-warning, #ffaa00);
        }

        .cm-bar-fill.flare {
          background: var(--status-critical, #ff4444);
        }

        .cm-active-timer {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          color: var(--status-warning, #ffaa00);
          margin-top: 2px;
        }

        .no-ecm {
          color: var(--text-dim, #555566);
          font-style: italic;
          text-align: center;
          padding: 20px 10px;
          font-size: 0.75rem;
        }
      </style>

      <div id="ecm-content">
        <div class="no-ecm">ECM system not available</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const ecm = ship?.ecm;
    const container = this.shadowRoot.getElementById("ecm-content");

    if (!ecm || !container) {
      if (container) {
        container.innerHTML = '<div class="no-ecm">ECM system not available</div>';
      }
      return;
    }

    const modeClass = ecm.emcon_active ? "emcon" : (ecm.jammer_enabled || ecm.chaff_active || ecm.flare_active) ? "active" : "standby";
    const modeText = ecm.status || "standby";

    const chaffPct = ecm.chaff_max > 0 ? (ecm.chaff_count / ecm.chaff_max * 100) : 0;
    const flarePct = ecm.flare_max > 0 ? (ecm.flare_count / ecm.flare_max * 100) : 0;

    container.innerHTML = `
      <!-- ECM Mode Indicator -->
      <div class="ecm-mode ${modeClass}">
        <div class="mode-dot"></div>
        <span>${modeText}</span>
      </div>

      <!-- Controls -->
      <div class="section">
        <div class="section-title">Countermeasures</div>
        <div class="controls-grid">
          <button class="ecm-btn ${ecm.jammer_enabled ? 'active' : ''} ${ecm.emcon_active ? 'disabled' : ''}"
                  id="btn-jammer">
            ${ecm.jammer_enabled ? 'JAM ON' : 'JAMMER'}
            <span class="btn-count">${Math.round(ecm.jammer_power / 1000)}kW</span>
          </button>
          <button class="ecm-btn ${ecm.emcon_active ? 'emcon-active' : ''}"
                  id="btn-emcon">
            ${ecm.emcon_active ? 'EMCON ON' : 'EMCON'}
            <span class="btn-count">stealth</span>
          </button>
          <button class="ecm-btn ${ecm.chaff_count <= 0 ? 'disabled' : ''}"
                  id="btn-chaff">
            CHAFF
            <span class="btn-count">${ecm.chaff_count}/${ecm.chaff_max}</span>
          </button>
          <button class="ecm-btn ${ecm.flare_count <= 0 ? 'disabled' : ''}"
                  id="btn-flare">
            FLARE
            <span class="btn-count">${ecm.flare_count}/${ecm.flare_max}</span>
          </button>
        </div>
      </div>

      <!-- Expendables Status -->
      <div class="section">
        <div class="section-title">Expendables</div>
        <div class="cm-bar-container">
          <div class="cm-bar-label">
            <span class="cm-bar-label-name">Chaff</span>
            <span class="cm-bar-label-count">${ecm.chaff_count}/${ecm.chaff_max}</span>
          </div>
          <div class="cm-bar">
            <div class="cm-bar-fill chaff" style="width: ${chaffPct}%"></div>
          </div>
          ${ecm.chaff_active ? `<div class="cm-active-timer">Active: ${ecm.chaff_remaining_time}s</div>` : ''}
        </div>
        <div class="cm-bar-container" style="margin-top: 8px">
          <div class="cm-bar-label">
            <span class="cm-bar-label-name">Flares</span>
            <span class="cm-bar-label-count">${ecm.flare_count}/${ecm.flare_max}</span>
          </div>
          <div class="cm-bar">
            <div class="cm-bar-fill flare" style="width: ${flarePct}%"></div>
          </div>
          ${ecm.flare_active ? `<div class="cm-active-timer">Active: ${ecm.flare_remaining_time}s</div>` : ''}
        </div>
      </div>

      <!-- Status Details -->
      <div class="section">
        <div class="section-title">Status</div>
        <div class="status-row">
          <span class="status-label">Jammer</span>
          <span class="status-value ${ecm.jammer_enabled ? 'active' : ''}">${ecm.jammer_enabled ? 'ACTIVE' : 'OFF'}</span>
        </div>
        <div class="status-row">
          <span class="status-label">EMCON</span>
          <span class="status-value ${ecm.emcon_active ? 'emcon' : ''}">${ecm.emcon_active ? 'ENGAGED' : 'OFF'}</span>
        </div>
        <div class="status-row">
          <span class="status-label">ECM Factor</span>
          <span class="status-value">${Math.round(ecm.ecm_factor * 100)}%</span>
        </div>
      </div>
    `;

    // Bind button events
    this._bindButtons(ecm);
  }

  _bindButtons(ecm) {
    const btnJammer = this.shadowRoot.getElementById("btn-jammer");
    const btnEmcon = this.shadowRoot.getElementById("btn-emcon");
    const btnChaff = this.shadowRoot.getElementById("btn-chaff");
    const btnFlare = this.shadowRoot.getElementById("btn-flare");

    if (btnJammer) {
      btnJammer.addEventListener("click", () => {
        if (ecm.emcon_active) return;
        const cmd = ecm.jammer_enabled ? "deactivate_jammer" : "activate_jammer";
        this._sendCommand(cmd);
      });
    }

    if (btnEmcon) {
      btnEmcon.addEventListener("click", () => {
        this._sendCommand("set_emcon", { enabled: !ecm.emcon_active });
      });
    }

    if (btnChaff) {
      btnChaff.addEventListener("click", () => {
        if (ecm.chaff_count > 0) {
          this._sendCommand("deploy_chaff");
        }
      });
    }

    if (btnFlare) {
      btnFlare.addEventListener("click", () => {
        if (ecm.flare_count > 0) {
          this._sendCommand("deploy_flare");
        }
      });
    }
  }
}

customElements.define("ecm-control-panel", ECMControlPanel);
export default ECMControlPanel;
