/**
 * ECM Control Panel
 * Provides interactive controls for electronic countermeasures:
 * - Radar jammer toggle
 * - Chaff deployment
 * - Flare deployment
 * - EMCON mode toggle
 * - Status readout
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

class ECMControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tier = window.controlTier || "arcade";
  }

  connectedCallback() {
    this.render();
    this._subscribe();

    // Tier-change listener: switch between manual/preset/hidden ECM views
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._updateDisplay();
    };
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
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

  async _sendCommand(cmd, args = {}) {
    return wsClient.sendShipCommand(cmd, args);
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

        /* === MANUAL/RAW tier: jammer power slider === */
        .jammer-slider-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
        }
        .jammer-slider-label {
          font-size: 0.65rem;
          text-transform: uppercase;
          color: var(--text-secondary, #888899);
          white-space: nowrap;
        }
        .jammer-slider {
          flex: 1;
          -webkit-appearance: none;
          appearance: none;
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          outline: none;
        }
        .jammer-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: var(--status-info, #00aaff);
          cursor: pointer;
        }
        .jammer-power-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-primary, #e0e0e0);
          min-width: 4em;
          text-align: right;
        }
        .freq-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }
        .freq-label {
          font-size: 0.65rem;
          text-transform: uppercase;
          color: var(--text-secondary, #888899);
        }
        .freq-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-primary, #e0e0e0);
        }

        /* === ARCADE tier: preset mode buttons === */
        .preset-grid {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr;
          gap: 6px;
          margin-bottom: 12px;
        }
        .preset-btn {
          padding: 12px 8px;
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
          background: var(--bg-input, #1a1a24);
          color: var(--text-dim, #555566);
          font-family: inherit;
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          cursor: pointer;
          transition: all 0.15s ease;
          text-align: center;
        }
        .preset-btn:hover {
          border-color: var(--text-secondary, #888899);
          color: var(--text-primary, #e0e0e0);
        }
        .preset-btn.active.aggressive {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.1);
        }
        .preset-btn.active.defensive {
          border-color: var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
          background: rgba(0, 170, 255, 0.1);
        }
        .preset-btn.active.silent {
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.08);
        }
        .preset-hint {
          font-size: 0.55rem;
          font-weight: 400;
          opacity: 0.7;
          display: block;
          margin-top: 2px;
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
    const tier = this._tier;

    if (!ecm || !container) {
      if (container) {
        container.innerHTML = '<div class="no-ecm">ECM system not available</div>';
      }
      return;
    }

    // CPU-ASSIST: ECM is hidden (auto-tactical manages it).
    // Show a minimal status indicator in case the panel is forced visible.
    if (tier === "cpu-assist") {
      const modeClass = ecm.emcon_active ? "emcon" : (ecm.jammer_enabled || ecm.chaff_active) ? "active" : "standby";
      container.innerHTML = `
        <div class="ecm-mode ${modeClass}">
          <div class="mode-dot"></div>
          <span>AUTO-TACTICAL ECM</span>
        </div>
        <div class="no-ecm">ECM managed by auto-tactical system</div>
      `;
      return;
    }

    // ARCADE: preset ECM modes (AGGRESSIVE / DEFENSIVE / SILENT)
    if (tier === "arcade") {
      this._renderArcadeEcm(container, ecm);
      return;
    }

    // MANUAL/RAW: full manual ECM with jammer power slider, individual deploy buttons
    this._renderManualEcm(container, ecm, tier);
  }

  /**
   * ARCADE tier: three preset ECM modes with one-click activation.
   * AGGRESSIVE = jammer max + auto-deploy countermeasures
   * DEFENSIVE = chaff/flare auto on incoming
   * SILENT = EMCON mode
   */
  _renderArcadeEcm(container, ecm) {
    // Determine which preset is currently active based on ECM state
    let activePreset = "none";
    if (ecm.emcon_active) {
      activePreset = "silent";
    } else if (ecm.jammer_enabled) {
      activePreset = "aggressive";
    } else if (ecm.chaff_active || ecm.flare_active) {
      activePreset = "defensive";
    }

    const modeClass = ecm.emcon_active ? "emcon" : (ecm.jammer_enabled || ecm.chaff_active) ? "active" : "standby";
    const modeText = ecm.status || "standby";

    const chaffPct = ecm.chaff_max > 0 ? (ecm.chaff_count / ecm.chaff_max * 100) : 0;
    const flarePct = ecm.flare_max > 0 ? (ecm.flare_count / ecm.flare_max * 100) : 0;

    container.innerHTML = `
      <div class="ecm-mode ${modeClass}">
        <div class="mode-dot"></div>
        <span>${modeText}</span>
      </div>

      <div class="preset-grid">
        <button class="preset-btn ${activePreset === 'aggressive' ? 'active aggressive' : ''}"
                id="preset-aggressive">
          AGGRESSIVE
          <span class="preset-hint">JAM + AUTO CM</span>
        </button>
        <button class="preset-btn ${activePreset === 'defensive' ? 'active defensive' : ''}"
                id="preset-defensive">
          DEFENSIVE
          <span class="preset-hint">AUTO CHAFF/FLARE</span>
        </button>
        <button class="preset-btn ${activePreset === 'silent' ? 'active silent' : ''}"
                id="preset-silent">
          SILENT
          <span class="preset-hint">EMCON</span>
        </button>
      </div>

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
        </div>
        <div class="cm-bar-container" style="margin-top: 8px">
          <div class="cm-bar-label">
            <span class="cm-bar-label-name">Flares</span>
            <span class="cm-bar-label-count">${ecm.flare_count}/${ecm.flare_max}</span>
          </div>
          <div class="cm-bar">
            <div class="cm-bar-fill flare" style="width: ${flarePct}%"></div>
          </div>
        </div>
      </div>
    `;

    // Bind preset buttons
    const presetAggressive = this.shadowRoot.getElementById("preset-aggressive");
    const presetDefensive = this.shadowRoot.getElementById("preset-defensive");
    const presetSilent = this.shadowRoot.getElementById("preset-silent");

    if (presetAggressive) {
      presetAggressive.addEventListener("click", () => {
        // AGGRESSIVE: jammer on, EMCON off
        this._sendCommand("set_emcon", { enabled: false });
        this._sendCommand("activate_jammer");
      });
    }
    if (presetDefensive) {
      presetDefensive.addEventListener("click", () => {
        // DEFENSIVE: jammer off, EMCON off, deploy chaff+flare if available
        this._sendCommand("set_emcon", { enabled: false });
        this._sendCommand("deactivate_jammer");
        if (ecm.chaff_count > 0) this._sendCommand("deploy_chaff");
        if (ecm.flare_count > 0) this._sendCommand("deploy_flare");
      });
    }
    if (presetSilent) {
      presetSilent.addEventListener("click", () => {
        // SILENT: EMCON on, jammer off
        this._sendCommand("deactivate_jammer");
        this._sendCommand("set_emcon", { enabled: true });
      });
    }
  }

  /**
   * MANUAL/RAW tier: full manual ECM with jammer power slider,
   * individual chaff/flare deploy buttons with count, EMCON toggle, frequency display.
   */
  _renderManualEcm(container, ecm, tier) {
    const modeClass = ecm.emcon_active ? "emcon" : (ecm.jammer_enabled || ecm.chaff_active || ecm.flare_active) ? "active" : "standby";
    const modeText = ecm.status || "standby";

    const chaffPct = ecm.chaff_max > 0 ? (ecm.chaff_count / ecm.chaff_max * 100) : 0;
    const flarePct = ecm.flare_max > 0 ? (ecm.flare_count / ecm.flare_max * 100) : 0;

    // Jammer power in kW for display
    const jammerPowerKw = Math.round((ecm.jammer_power || 0) / 1000);
    const jammerMaxKw = Math.round((ecm.jammer_max_power || ecm.jammer_power || 10000) / 1000);

    container.innerHTML = `
      <!-- ECM Mode Indicator -->
      <div class="ecm-mode ${modeClass}">
        <div class="mode-dot"></div>
        <span>${modeText}</span>
      </div>

      <!-- Jammer Power Slider (MANUAL/RAW) -->
      <div class="section">
        <div class="section-title">Jammer</div>
        <div class="jammer-slider-row">
          <span class="jammer-slider-label">POWER</span>
          <input type="range" class="jammer-slider" id="jammer-power-slider"
                 min="0" max="${jammerMaxKw}" value="${jammerPowerKw}" step="1">
          <span class="jammer-power-value" id="jammer-power-display">${jammerPowerKw} kW</span>
        </div>
        <div class="controls-grid">
          <button class="ecm-btn ${ecm.jammer_enabled ? 'active' : ''} ${ecm.emcon_active ? 'disabled' : ''}"
                  id="btn-jammer">
            ${ecm.jammer_enabled ? 'JAM ON' : 'JAMMER'}
          </button>
          <button class="ecm-btn ${ecm.emcon_active ? 'emcon-active' : ''}"
                  id="btn-emcon">
            ${ecm.emcon_active ? 'EMCON ON' : 'EMCON'}
          </button>
        </div>
      </div>

      <!-- Individual Countermeasure Deploy -->
      <div class="section">
        <div class="section-title">Countermeasures</div>
        <div class="controls-grid">
          <button class="ecm-btn ${ecm.chaff_count <= 0 ? 'disabled' : ''}"
                  id="btn-chaff">
            DEPLOY CHAFF
            <span class="btn-count">${ecm.chaff_count}/${ecm.chaff_max}</span>
          </button>
          <button class="ecm-btn ${ecm.flare_count <= 0 ? 'disabled' : ''}"
                  id="btn-flare">
            DEPLOY FLARE
            <span class="btn-count">${ecm.flare_count}/${ecm.flare_max}</span>
          </button>
        </div>
      </div>

      <!-- Expendables Status Bars -->
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
          <span class="status-label">Jammer Power</span>
          <span class="status-value">${jammerPowerKw} kW</span>
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

    // Bind buttons and slider
    this._bindButtons(ecm);

    // Jammer power slider
    const slider = this.shadowRoot.getElementById("jammer-power-slider");
    const display = this.shadowRoot.getElementById("jammer-power-display");
    if (slider) {
      slider.addEventListener("input", () => {
        if (display) display.textContent = `${slider.value} kW`;
      });
      slider.addEventListener("change", () => {
        this._sendCommand("set_jammer_power", { power: parseInt(slider.value) * 1000 });
      });
    }
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
