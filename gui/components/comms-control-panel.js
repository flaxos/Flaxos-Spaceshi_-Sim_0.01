/**
 * Comms Control Panel
 * Provides interactive controls for communications:
 * - Transponder toggle, IFF code management, and spoofing
 * - Radio hail (with light-speed delay) and broadcast messaging
 * - Diplomatic state indicators on contacts
 * - Distress beacon activation
 * - Message log with hail response rendering
 *
 * Tier-aware rendering:
 *   MANUAL:     Raw radio only — frequency, power, IFF hex, signal meter, raw compose.
 *   RAW:        Full workstation — all controls, raw signal data, transponder spoof, message log.
 *   ARCADE:     Simplified — one-click HAIL per contact, diplo badges, broadcast presets.
 *   CPU-ASSIST: Auto-comms hero — proposals queue with approve/deny, incoming messages only.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getProposalCSS } from "../js/proposal-styles.js";

const CHANNELS = ["general", "fleet", "emergency", "tactical"];

/** Colour mapping for diplomatic states */
const DIPLO_COLORS = {
  allied: "var(--status-nominal, #00ff88)",
  neutral: "var(--status-info, #00aaff)",
  hostile: "var(--status-critical, #ff4444)",
  unknown: "var(--text-dim, #555566)",
};

/** Broadcast presets for ARCADE tier */
const BROADCAST_PRESETS = [
  { label: "IDENT", msg: "This is {ship}, transmitting IFF. Over.", channel: "general" },
  { label: "HOLD FIRE", msg: "All stations hold fire. Repeat: hold fire.", channel: "tactical" },
  { label: "MAYDAY", msg: "Mayday, mayday, mayday. Requesting immediate assistance.", channel: "emergency" },
  { label: "SURRENDER", msg: "We are standing down. Cease fire.", channel: "general" },
];

class CommsControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";
    this._hailingTarget = null; // contact_id currently being hailed
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    // Listen for tier changes (same pattern as flight-computer-panel)
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._updateDisplay();
    };
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

  async _sendCommand(cmd, args = {}) {
    return wsClient.sendShipCommand(cmd, args);
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>${CommsControlPanel._styles()}</style>
      <div id="comms-content">
        <div class="no-comms">Comms system not available</div>
      </div>
    `;
  }

  static _styles() {
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
      .status-row {
        display: flex; justify-content: space-between;
        align-items: center; padding: 4px 0; font-size: 0.75rem;
      }
      .status-label { color: var(--text-secondary, #888899); }
      .status-value {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-weight: 600; color: var(--text-primary, #e0e0e0);
      }
      .status-value.active { color: var(--status-nominal, #00ff88); }
      .status-value.warning { color: var(--status-warning, #ffaa00); }
      .status-value.critical { color: var(--status-critical, #ff4444); }
      .status-value.suppressed { color: var(--status-warning, #ffaa00); }
      .status-value.off { color: var(--text-dim, #555566); }
      .status-value.info { color: var(--status-info, #00aaff); }

      .comms-mode {
        display: flex; align-items: center; gap: 8px;
        padding: 8px 10px; margin-bottom: 12px; border-radius: 4px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.75rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 1px;
      }
      .comms-mode.active {
        background: rgba(0,255,136,0.1);
        border: 1px solid var(--status-nominal, #00ff88);
        color: var(--status-nominal, #00ff88);
      }
      .comms-mode.silent {
        background: rgba(85,85,102,0.15);
        border: 1px solid var(--text-dim, #555566);
        color: var(--text-dim, #555566);
      }
      .comms-mode.emcon {
        background: rgba(0,170,255,0.1);
        border: 1px solid var(--status-info, #00aaff);
        color: var(--status-info, #00aaff);
      }
      .comms-mode.distress {
        background: rgba(255,68,68,0.15);
        border: 1px solid var(--status-critical, #ff4444);
        color: var(--status-critical, #ff4444);
        animation: distress-flash 1s ease-in-out infinite;
      }
      .comms-mode.offline {
        background: rgba(255,68,68,0.08);
        border: 1px solid rgba(255,68,68,0.3);
        color: var(--status-critical, #ff4444);
      }
      .mode-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: currentColor;
      }
      .comms-mode.active .mode-dot { animation: pulse 1.5s ease-in-out infinite; }
      .comms-mode.distress .mode-dot { animation: pulse-fast 0.6s ease-in-out infinite; }

      @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
      @keyframes pulse-fast { 0%,100%{opacity:1} 50%{opacity:0.2} }
      @keyframes distress-flash {
        0%,100%{border-color:var(--status-critical,#ff4444)}
        50%{border-color:rgba(255,68,68,0.3)}
      }

      .comms-btn {
        background: rgba(0,170,255,0.1);
        border: 1px solid rgba(0,170,255,0.3); border-radius: 4px;
        color: var(--status-info, #00aaff);
        padding: 8px 10px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem; cursor: pointer;
        text-transform: uppercase; transition: all 0.15s ease;
        text-align: center; min-height: 32px;
      }
      .comms-btn:hover {
        background: rgba(0,170,255,0.2);
        border-color: var(--status-info, #00aaff);
      }
      .comms-btn.active {
        background: rgba(0,255,136,0.15);
        border-color: var(--status-nominal, #00ff88);
        color: var(--status-nominal, #00ff88);
      }
      .comms-btn.disabled {
        opacity: 0.4; cursor: not-allowed;
        pointer-events: none;
      }
      .comms-btn.hailing {
        background: rgba(255,170,0,0.15);
        border-color: var(--status-warning, #ffaa00);
        color: var(--status-warning, #ffaa00);
        animation: pulse 1.5s ease-in-out infinite;
      }
      .comms-btn.distress {
        background: rgba(255,68,68,0.1);
        border: 1px solid rgba(255,68,68,0.3);
        color: var(--status-critical, #ff4444);
      }
      .comms-btn.distress:hover {
        background: rgba(255,68,68,0.25);
        border-color: var(--status-critical, #ff4444);
      }
      .comms-btn.distress.active {
        background: rgba(255,68,68,0.3);
        border-color: var(--status-critical, #ff4444);
        animation: distress-flash 1s ease-in-out infinite;
      }
      .comms-btn.full-width { width: 100%; }

      .input-row {
        display: flex; gap: 6px; align-items: center;
        margin-bottom: 8px;
      }
      .comms-input {
        flex: 1;
        background: rgba(0,0,0,0.3);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        color: var(--text-primary, #e0e0e0);
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem; padding: 6px 8px; min-height: 28px;
        outline: none; transition: border-color 0.15s ease;
      }
      .comms-input:focus { border-color: var(--status-info, #00aaff); }
      .comms-input::placeholder {
        color: var(--text-dim, #555566); font-style: italic;
      }
      .comms-select {
        background: rgba(0,0,0,0.3);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        color: var(--text-primary, #e0e0e0);
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem; padding: 6px 8px; min-height: 28px;
        outline: none; cursor: pointer;
      }
      .comms-select option {
        background: var(--bg-primary, #0a0a0f);
        color: var(--text-primary, #e0e0e0);
      }
      .input-label {
        font-size: 0.65rem; color: var(--text-dim, #555566);
        text-transform: uppercase; letter-spacing: 0.3px;
        margin-bottom: 4px;
      }
      .input-group { margin-bottom: 10px; }

      .transponder-code {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 1rem; font-weight: 700; letter-spacing: 2px;
        padding: 6px 10px; border-radius: 4px; text-align: center;
        margin-bottom: 8px;
      }
      .transponder-code.active {
        background: rgba(0,255,136,0.08);
        border: 1px solid rgba(0,255,136,0.3);
        color: var(--status-nominal, #00ff88);
      }
      .transponder-code.spoofed {
        background: rgba(255,170,0,0.08);
        border: 1px solid rgba(255,170,0,0.3);
        color: var(--status-warning, #ffaa00);
      }
      .transponder-code.suppressed {
        background: rgba(255,170,0,0.08);
        border: 1px solid rgba(255,170,0,0.3);
        color: var(--status-warning, #ffaa00);
        text-decoration: line-through;
      }
      .transponder-code.off {
        background: rgba(85,85,102,0.08);
        border: 1px solid rgba(85,85,102,0.3);
        color: var(--text-dim, #555566);
      }

      .transponder-controls {
        display: flex; gap: 6px; margin-top: 8px;
      }
      .transponder-controls .comms-btn { flex-shrink: 0; }

      .spoof-badge {
        font-size: 0.6rem; font-weight: 700;
        color: var(--status-warning, #ffaa00);
        text-transform: uppercase; margin-left: 4px;
      }

      .diplo-badge {
        font-size: 0.6rem; font-weight: 700;
        text-transform: uppercase; padding: 1px 5px;
        border-radius: 3px; margin-left: 4px;
      }

      .message-log {
        max-height: 200px; overflow-y: auto;
        background: rgba(0,0,0,0.25);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px; padding: 6px;
      }
      .message-log::-webkit-scrollbar { width: 4px; }
      .message-log::-webkit-scrollbar-track { background: transparent; }
      .message-log::-webkit-scrollbar-thumb {
        background: var(--border-default, #2a2a3a); border-radius: 2px;
      }
      .msg-entry {
        padding: 3px 4px;
        border-bottom: 1px solid rgba(42,42,58,0.5);
        font-size: 0.65rem; line-height: 1.4;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
      }
      .msg-entry:last-child { border-bottom: none; }
      .msg-time { color: var(--text-dim, #555566); }
      .msg-type { font-weight: 600; text-transform: uppercase; }
      .msg-type.hail_sent { color: var(--status-info, #00aaff); }
      .msg-type.hail_response { color: var(--status-nominal, #00ff88); }
      .msg-type.broadcast_sent { color: var(--status-nominal, #00ff88); }
      .msg-type.distress_activated, .msg-type.distress_cancelled {
        color: var(--status-critical, #ff4444);
      }
      .msg-type.system { color: var(--status-warning, #ffaa00); }
      .msg-delay {
        color: var(--text-dim, #555566); font-style: italic;
        font-size: 0.6rem;
      }
      .msg-route { color: var(--text-secondary, #888899); }
      .msg-body { color: var(--text-primary, #e0e0e0); }
      .msg-empty {
        text-align: center; color: var(--text-dim, #555566);
        font-style: italic; padding: 12px 8px; font-size: 0.7rem;
      }
      .pending-badge {
        display: inline-block;
        background: var(--status-warning, #ffaa00);
        color: var(--bg-primary, #0a0a0f);
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.6rem; font-weight: 700;
        padding: 1px 5px; border-radius: 8px;
        margin-left: 6px; vertical-align: middle;
      }
      .no-comms {
        color: var(--text-dim, #555566); font-style: italic;
        text-align: center; padding: 20px 10px; font-size: 0.75rem;
      }

      /* --- MANUAL tier: signal meter, textarea, slider --- */
      .signal-meter {
        height: 6px; border-radius: 3px;
        background: rgba(42, 42, 58, 0.5);
        overflow: hidden; margin: 4px 0;
      }
      .signal-fill {
        height: 100%; border-radius: 3px;
        transition: width 0.3s ease;
      }
      .comms-textarea {
        width: 100%; resize: vertical;
        min-height: 48px; max-height: 120px;
        box-sizing: border-box;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
      }
      .comms-slider {
        flex: 1; height: 4px;
        -webkit-appearance: none; appearance: none;
        background: var(--bg-input, #1a1a24);
        border-radius: 2px; outline: none;
      }
      .comms-slider::-webkit-slider-thumb {
        -webkit-appearance: none; width: 14px; height: 14px;
        border-radius: 50%; background: var(--status-info, #00aaff);
        cursor: pointer;
      }

      /* --- ARCADE tier: contact hail grid, broadcast presets --- */
      .contact-hail-grid {
        display: flex; flex-direction: column; gap: 4px;
      }
      .contact-hail-btn {
        display: flex; justify-content: space-between; align-items: center;
        text-align: left; padding: 8px 10px;
      }
      .contact-name {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.75rem; font-weight: 600;
      }
      .preset-grid {
        display: grid; grid-template-columns: 1fr 1fr; gap: 4px;
      }
      .preset-btn {
        font-size: 0.65rem; font-weight: 700;
        letter-spacing: 0.5px; padding: 6px 8px;
      }

      /* --- CPU-ASSIST tier: auto-comms hero, proposals --- */
      .auto-comms-hero {
        border: 1px solid rgba(192, 160, 255, 0.2);
        border-radius: 6px; padding: 12px;
        background: rgba(192, 160, 255, 0.03);
      }
      .policy-grid {
        display: flex; gap: 4px;
      }
      .policy-btn {
        flex: 1; font-size: 0.65rem; font-weight: 600;
        letter-spacing: 0.3px; padding: 4px 6px;
      }
      .policy-btn.active {
        background: rgba(192, 160, 255, 0.15);
        border-color: rgba(192, 160, 255, 0.5);
        color: #c0a0ff;
      }
      /* Proposal cards — shared styles from proposal-styles.js */
      ${getProposalCSS()}
    `;
  }

  /* -----------------------------------------------------------------------
   * _updateDisplay — tier-aware main render dispatcher.
   * Routes to per-tier render methods so each tier gets distinct UI.
   * ----------------------------------------------------------------------- */
  _updateDisplay() {
    const ship = stateManager.getShipState();
    const container = this.shadowRoot.getElementById("comms-content");
    if (!container) return;

    const comms = ship?.comms;
    if (!comms) {
      container.innerHTML = '<div class="no-comms">Comms system not available</div>';
      return;
    }

    const tier = this._tier;
    if (tier === "manual") {
      container.innerHTML = this._renderManualTier(comms, ship);
    } else if (tier === "cpu-assist") {
      container.innerHTML = this._renderCpuAssistTier(comms, ship);
    } else if (tier === "arcade") {
      container.innerHTML = this._renderArcadeTier(comms, ship);
    } else {
      // RAW tier — full workstation, all controls
      container.innerHTML = this._renderRawTier(comms, ship);
    }

    this._bindControls(comms, ship?.target_id || "");
  }

  /* -----------------------------------------------------------------------
   * MANUAL tier: Raw radio controls only.
   * Frequency input, transmit power slider, raw IFF hex, signal meter,
   * raw message compose textarea. No diplomatic assists.
   * ----------------------------------------------------------------------- */
  _renderManualTier(comms, ship) {
    const modeHtml = this._renderModeIndicator(comms);
    const signalPct = Math.min(100, Math.max(0, (comms.signal_strength || 0) * 100));
    const signalColor = signalPct > 60 ? "var(--status-nominal,#00ff88)"
      : signalPct > 30 ? "var(--status-warning,#ffaa00)" : "var(--status-critical,#ff4444)";

    return `
      ${modeHtml}

      <!-- RAW RADIO CONTROLS -->
      <div class="section">
        <div class="section-title">Radio Transceiver</div>
        <div class="input-group">
          <div class="input-label">Frequency (MHz)</div>
          <div class="input-row">
            <input type="number" class="comms-input" id="input-frequency"
                   placeholder="243.000" step="0.001" min="1" max="30000"
                   value="${comms.frequency || ""}" />
            <button class="comms-btn" id="btn-set-freq">TUNE</button>
          </div>
        </div>
        <div class="input-group">
          <div class="input-label">Transmit Power (W)</div>
          <div class="input-row">
            <input type="range" class="comms-slider" id="input-tx-power"
                   min="1" max="1000" step="1"
                   value="${comms.radio_power || 100}" />
            <span class="status-value" id="tx-power-readout" style="min-width:4em;text-align:right;">
              ${comms.radio_power != null ? comms.radio_power.toFixed(0) + " W" : "--"}
            </span>
          </div>
        </div>
        <div class="input-group">
          <div class="input-label">Signal Strength</div>
          <div class="signal-meter">
            <div class="signal-fill" style="width:${signalPct}%;background:${signalColor}"></div>
          </div>
          <div class="status-row">
            <span class="status-label">SNR</span>
            <span class="status-value">${signalPct.toFixed(0)}%</span>
          </div>
        </div>
      </div>

      <!-- IFF TRANSPONDER (raw hex) -->
      <div class="section">
        <div class="section-title">IFF Transponder</div>
        <div class="input-group">
          <div class="input-label">IFF Code (hex)</div>
          <div class="input-row">
            <input type="text" class="comms-input" id="input-iff-code"
                   placeholder="0x7742" style="font-family:var(--font-mono);letter-spacing:2px;"
                   value="${comms.transponder_code || ""}" maxlength="16" />
            <button class="comms-btn" id="btn-set-iff">SET</button>
          </div>
        </div>
        <div class="transponder-controls">
          <button class="comms-btn ${comms.transponder_enabled ? 'active' : ''} full-width"
                  id="btn-transponder-toggle">
            ${comms.transponder_enabled ? "XPDR OFF" : "XPDR ON"}
          </button>
        </div>
      </div>

      <!-- RAW MESSAGE COMPOSE -->
      <div class="section">
        <div class="section-title">Transmit</div>
        <div class="input-group">
          <div class="input-label">Target ID</div>
          <div class="input-row">
            <input type="text" class="comms-input" id="input-hail-target"
                   placeholder="Contact ID or callsign" />
          </div>
        </div>
        <div class="input-group">
          <div class="input-label">Message</div>
          <textarea class="comms-input comms-textarea" id="input-raw-message"
                    placeholder="Type raw message..." rows="3"></textarea>
        </div>
        <div class="input-row">
          <button class="comms-btn full-width" id="btn-hail">TRANSMIT</button>
        </div>
      </div>

      <!-- DISTRESS (always available) -->
      ${this._renderDistressSection(comms)}
    `;
  }

  /* -----------------------------------------------------------------------
   * RAW tier: Full comms workstation — all controls, raw signal data,
   * transponder spoof, message log. Existing behavior preserved.
   * ----------------------------------------------------------------------- */
  _renderRawTier(comms, ship) {
    const modeHtml = this._renderModeIndicator(comms);
    const targetId = ship?.target_id || "";
    const { xpdrClass, xpdrStatus } = this._getTransponderState(comms);
    const radioRange = this._formatRadioRange(comms.radio_range);
    const pendingBadge = comms.pending_hails > 0
      ? `<span class="pending-badge">${comms.pending_hails}</span>` : "";
    const channelOptions = CHANNELS
      .map(ch => `<option value="${ch}">${ch.toUpperCase()}</option>`).join("");
    const isHailing = comms.pending_hails > 0;
    const hailBtnClass = isHailing ? "hailing" : (targetId ? "" : "disabled");
    const hailBtnText = isHailing ? "HAILING..." : "HAIL TARGET";
    const hailTitle = targetId ? `Hail contact ${targetId}` : "Select a target first";
    const spoofBadge = comms.is_spoofed ? '<span class="spoof-badge">SPOOFED</span>' : '';
    const signalPct = Math.min(100, Math.max(0, (comms.signal_strength || 0) * 100));
    const signalColor = signalPct > 60 ? "var(--status-nominal,#00ff88)"
      : signalPct > 30 ? "var(--status-warning,#ffaa00)" : "var(--status-critical,#ff4444)";

    return `
      ${modeHtml}

      <!-- TRANSPONDER -->
      <div class="section">
        <div class="section-title">Transponder${spoofBadge}</div>
        <div class="transponder-code ${xpdrClass}">
          ${comms.transponder_code || "----"}
        </div>
        <div class="status-row">
          <span class="status-label">Status</span>
          <span class="status-value ${xpdrClass}">${xpdrStatus}</span>
        </div>
        ${comms.is_spoofed ? `
        <div class="status-row">
          <span class="status-label">Declared Class</span>
          <span class="status-value warning">${comms.declared_class || "--"}</span>
        </div>
        <div class="status-row">
          <span class="status-label">Declared Faction</span>
          <span class="status-value warning">${comms.declared_faction || "--"}</span>
        </div>
        ` : ''}
        <div class="transponder-controls">
          <button class="comms-btn ${comms.transponder_enabled ? 'active' : ''} full-width"
                  id="btn-transponder-toggle">
            ${comms.transponder_enabled ? "DISABLE TRANSPONDER" : "ENABLE TRANSPONDER"}
          </button>
        </div>
        <div class="input-group" style="margin-top: 8px;">
          <div class="input-label">Set IFF Code</div>
          <div class="input-row">
            <input type="text" class="comms-input" id="input-iff-code"
                   placeholder="e.g. UNE-7742"
                   value="${comms.transponder_code || ""}"
                   maxlength="16" />
            <button class="comms-btn" id="btn-set-iff">SET</button>
          </div>
        </div>
        <div class="input-group">
          <div class="input-label">Transponder Spoofing</div>
          <div class="input-row">
            <button class="comms-btn ${comms.is_spoofed ? 'active' : ''}" id="btn-spoof-toggle"
                    style="flex: 1;">
              ${comms.is_spoofed ? "DISABLE SPOOF" : "ENABLE SPOOF"}
            </button>
          </div>
          ${comms.is_spoofed ? `
          <div class="input-row" style="margin-top: 4px;">
            <input type="text" class="comms-input" id="input-spoof-class"
                   placeholder="Declared class" value="${comms.declared_class || ""}" />
            <input type="text" class="comms-input" id="input-spoof-faction"
                   placeholder="Declared faction" value="${comms.declared_faction || ""}" />
            <button class="comms-btn" id="btn-set-spoof">SET</button>
          </div>
          ` : ''}
        </div>
      </div>

      <!-- RADIO — with raw signal data -->
      <div class="section">
        <div class="section-title">Radio${pendingBadge}</div>
        <div class="status-row">
          <span class="status-label">Power</span>
          <span class="status-value">${comms.radio_power != null ? comms.radio_power.toFixed(1) + " W" : "--"}</span>
        </div>
        <div class="status-row">
          <span class="status-label">Range</span>
          <span class="status-value">${radioRange}</span>
        </div>
        <div class="status-row">
          <span class="status-label">Signal</span>
          <span class="status-value">${signalPct.toFixed(0)}%</span>
        </div>
        <div class="signal-meter" style="margin:4px 0 8px;">
          <div class="signal-fill" style="width:${signalPct}%;background:${signalColor}"></div>
        </div>

        <div class="input-group" style="margin-top: 10px;">
          <div class="input-label">Hail Contact</div>
          <div class="input-row">
            <button class="comms-btn ${hailBtnClass} full-width" id="btn-hail-target"
                    title="${hailTitle}">
              ${hailBtnText}${targetId ? ` (${targetId})` : ''}
            </button>
          </div>
          <div class="input-row">
            <input type="text" class="comms-input" id="input-hail-target"
                   placeholder="Or enter target ID" />
            <button class="comms-btn" id="btn-hail">HAIL</button>
          </div>
        </div>

        <div class="input-group">
          <div class="input-label">Broadcast Message</div>
          <div class="input-row">
            <input type="text" class="comms-input" id="input-broadcast-msg"
                   placeholder="Message..." />
            <select class="comms-select" id="select-channel">
              ${channelOptions}
            </select>
            <button class="comms-btn" id="btn-broadcast">BROADCAST</button>
          </div>
        </div>
      </div>

      ${this._renderDistressSection(comms)}

      <!-- MESSAGE LOG -->
      <div class="section">
        <div class="section-title">Message Log (${comms.message_count || 0})</div>
        <div class="message-log" id="message-log">
          ${this._renderMessages(comms.recent_messages)}
        </div>
      </div>
    `;
  }

  /* -----------------------------------------------------------------------
   * ARCADE tier: Simplified hail/broadcast interface.
   * One-click HAIL per contact, diplo badges, broadcast presets,
   * auto-suggested responses.
   * ----------------------------------------------------------------------- */
  _renderArcadeTier(comms, ship) {
    const modeHtml = this._renderModeIndicator(comms);
    const targetId = ship?.target_id || "";
    const { xpdrClass, xpdrStatus } = this._getTransponderState(comms);
    const isHailing = comms.pending_hails > 0;

    // Build contact hail buttons from sensor contacts
    const contacts = ship?.contacts || [];
    const contactHailBtns = contacts.length > 0
      ? contacts.map(c => {
          const name = c.name || c.classification || c.contact_id || "Unknown";
          const diplo = c.diplomatic_state || "unknown";
          const diploColor = DIPLO_COLORS[diplo] || DIPLO_COLORS.unknown;
          const isTarget = c.contact_id === targetId;
          const targetMark = isTarget ? ' style="border-color:var(--status-info,#00aaff);"' : '';
          return `
            <button class="comms-btn contact-hail-btn${isTarget ? ' active' : ''}"${targetMark}
                    data-hail-contact="${this._escapeHtml(c.contact_id)}">
              <span class="contact-name">${this._escapeHtml(name)}</span>
              <span class="diplo-badge" style="color:${diploColor};border:1px solid ${diploColor}">${diplo.toUpperCase()}</span>
            </button>`;
        }).join("")
      : '<div class="msg-empty">No contacts detected</div>';

    // Broadcast presets
    const presetBtns = BROADCAST_PRESETS.map((p, i) => `
      <button class="comms-btn preset-btn" data-preset-idx="${i}">${p.label}</button>
    `).join("");

    return `
      ${modeHtml}

      <!-- TRANSPONDER (simplified) -->
      <div class="section">
        <div class="section-title">Transponder</div>
        <div class="status-row">
          <span class="status-label">IFF</span>
          <span class="status-value ${xpdrClass}">${comms.transponder_code || "----"}</span>
        </div>
        <div class="status-row">
          <span class="status-label">Status</span>
          <span class="status-value ${xpdrClass}">${xpdrStatus}</span>
        </div>
        <div class="transponder-controls">
          <button class="comms-btn ${comms.transponder_enabled ? 'active' : ''} full-width"
                  id="btn-transponder-toggle">
            ${comms.transponder_enabled ? "TRANSPONDER OFF" : "TRANSPONDER ON"}
          </button>
        </div>
      </div>

      <!-- HAIL CONTACTS (one button per detected contact) -->
      <div class="section">
        <div class="section-title">Hail Contact${isHailing ? ' <span class="pending-badge">HAILING</span>' : ''}</div>
        <div class="contact-hail-grid">
          ${contactHailBtns}
        </div>
      </div>

      <!-- QUICK BROADCAST PRESETS -->
      <div class="section">
        <div class="section-title">Broadcast</div>
        <div class="preset-grid">
          ${presetBtns}
        </div>
        <div class="input-group" style="margin-top:8px;">
          <div class="input-row">
            <input type="text" class="comms-input" id="input-broadcast-msg"
                   placeholder="Custom message..." />
            <button class="comms-btn" id="btn-broadcast">SEND</button>
          </div>
        </div>
      </div>

      ${this._renderDistressSection(comms)}

      <!-- RECENT MESSAGES (compact) -->
      <div class="section">
        <div class="section-title">Recent (${comms.message_count || 0})</div>
        <div class="message-log" id="message-log">
          ${this._renderMessages((comms.recent_messages || []).slice(0, 5))}
        </div>
      </div>
    `;
  }

  /* -----------------------------------------------------------------------
   * CPU-ASSIST tier: Auto-comms hero with approve/deny workflow.
   * Shows incoming messages queue, auto-response recommendations,
   * comms policy selector. Minimal manual controls.
   * ----------------------------------------------------------------------- */
  _renderCpuAssistTier(comms, ship) {
    const modeHtml = this._renderModeIndicator(comms);
    const autoComms = ship?.auto_comms || {};
    const proposals = autoComms.proposals || [];
    const policy = autoComms.policy || "open_comms";

    // Policy selector buttons
    const policies = [
      { id: "open_comms", label: "OPEN" },
      { id: "radio_silence", label: "SILENCE" },
      { id: "diplomatic_mode", label: "DIPLOMATIC" },
    ];
    const policyBtns = policies.map(p =>
      `<button class="comms-btn policy-btn${p.id === policy ? ' active' : ''}"
              data-policy="${p.id}">${p.label}</button>`
    ).join("");

    // Proposals queue
    const proposalsHtml = proposals.length === 0
      ? '<div class="no-proposals">Auto-comms standing by — no proposals</div>'
      : proposals.map(p => {
          const confidence = p.confidence ?? 0;
          const remaining = Math.max(0, p.time_remaining || 0);
          const total = p.total_time || 30;
          const timerPct = Math.min(100, (remaining / total) * 100);
          const isUrgent = confidence > 0.8 || remaining < 5;
          const urgentClass = isUrgent ? " urgent" : "";
          return `
          <div class="proposal-card${urgentClass}">
            <div class="proposal-header">
              <span class="proposal-action">${this._escapeHtml(p.description || p.action)}</span>
              ${confidence > 0 ? `<span class="proposal-confidence">${(confidence * 100).toFixed(0)}%</span>` : ""}
              ${p.crew_efficiency != null ? `<span class="proposal-crew">Crew: ${(p.crew_efficiency * 100).toFixed(0)}%</span>` : ""}
            </div>
            ${remaining > 0 ? `<div class="proposal-timer"><div class="proposal-timer-fill" style="width:${timerPct}%"></div></div>` : ""}
            <div class="proposal-actions">
              <button class="proposal-approve" data-approve="${this._escapeHtml(p.id)}">EXECUTE</button>
              <button class="proposal-deny" data-deny="${this._escapeHtml(p.id)}">STAND DOWN</button>
            </div>
          </div>`;
        }).join("");

    return `
      ${modeHtml}

      <!-- AUTO-COMMS CONTROL -->
      <div class="section auto-comms-hero">
        <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>Auto Communications</span>
          <button class="comms-btn ${autoComms.enabled ? 'active' : ''}" id="auto-comms-toggle"
                  style="padding:2px 12px;font-size:0.65rem;">
            ${autoComms.enabled ? "DISABLE" : "ENABLE"}
          </button>
        </div>

        <!-- Comms Policy -->
        <div class="input-group">
          <div class="input-label">Comms Policy</div>
          <div class="policy-grid" id="comms-policy-row">
            ${policyBtns}
          </div>
        </div>

        <!-- Proposals Queue -->
        <div class="input-group">
          <div class="input-label">Pending Actions (${proposals.length})</div>
          <div class="proposals-queue" id="comms-proposals">
            ${proposalsHtml}
          </div>
        </div>
      </div>

      <!-- TRANSPONDER (read-only status) -->
      <div class="section">
        <div class="section-title">Transponder</div>
        <div class="status-row">
          <span class="status-label">IFF</span>
          <span class="status-value">${comms.transponder_code || "----"}</span>
        </div>
        <div class="status-row">
          <span class="status-label">Status</span>
          <span class="status-value ${this._getTransponderState(comms).xpdrClass}">
            ${this._getTransponderState(comms).xpdrStatus}
          </span>
        </div>
      </div>

      ${this._renderDistressSection(comms)}

      <!-- INCOMING MESSAGES (read-only) -->
      <div class="section">
        <div class="section-title">Incoming Messages (${comms.message_count || 0})</div>
        <div class="message-log" id="message-log">
          ${this._renderMessages((comms.recent_messages || []).slice(0, 8))}
        </div>
      </div>
    `;
  }

  /* -----------------------------------------------------------------------
   * Shared render helpers — used across tiers.
   * ----------------------------------------------------------------------- */

  /** Comms mode indicator bar (top of all tier layouts). */
  _renderModeIndicator(comms) {
    const status = (comms.status || "offline").toUpperCase();
    let modeClass = "silent";
    if (comms.status === "DISTRESS" || comms.distress_active) modeClass = "distress";
    else if (comms.status === "EMCON" || comms.emcon_suppressed) modeClass = "emcon";
    else if (comms.status === "offline" || !comms.enabled) modeClass = "offline";
    else if (comms.status === "active" || comms.enabled) modeClass = "active";

    return `
      <div class="comms-mode ${modeClass}">
        <div class="mode-dot"></div>
        <span>COMMS: ${status}</span>
      </div>`;
  }

  /** Distress beacon section — shown in all tiers. */
  _renderDistressSection(comms) {
    return `
      <div class="section">
        <div class="section-title">Distress Beacon</div>
        <div class="status-row">
          <span class="status-label">Beacon</span>
          <span class="status-value ${comms.distress_active ? 'critical' : comms.distress_beacon_enabled ? 'warning' : 'off'}">
            ${comms.distress_active ? "TRANSMITTING" : comms.distress_beacon_enabled ? "ARMED" : "OFF"}
          </span>
        </div>
        <button class="comms-btn distress ${comms.distress_beacon_enabled ? 'active' : ''} full-width"
                id="btn-distress" style="margin-top: 8px;">
          ${comms.distress_beacon_enabled ? "CANCEL DISTRESS" : "ACTIVATE DISTRESS"}
        </button>
      </div>`;
  }

  /** Derive transponder display state from comms data. */
  _getTransponderState(comms) {
    let xpdrClass = "off";
    if (comms.is_spoofed && comms.transponder_active) xpdrClass = "spoofed";
    else if (comms.transponder_active) xpdrClass = "active";
    else if (comms.transponder_enabled && comms.emcon_suppressed) xpdrClass = "suppressed";

    let xpdrStatus = "OFF";
    if (comms.is_spoofed && comms.transponder_active) xpdrStatus = "SPOOFED";
    else if (comms.transponder_active) xpdrStatus = "ACTIVE";
    else if (comms.transponder_enabled && comms.emcon_suppressed) xpdrStatus = "EMCON SUPPRESSED";
    else if (comms.transponder_enabled) xpdrStatus = "ENABLED";

    return { xpdrClass, xpdrStatus };
  }

  /** Format radio range for display. */
  _formatRadioRange(range) {
    if (!range) return "--";
    return range >= 1000
      ? (range / 1000).toFixed(1) + " Mm"
      : range.toFixed(0) + " km";
  }

  /**
   * Render recent messages into the log with light-delay annotations.
   */
  _renderMessages(messages) {
    if (!messages || messages.length === 0) {
      return '<div class="msg-empty">No messages</div>';
    }

    return messages
      .slice()
      .reverse()
      .map(msg => {
        const time = msg.time != null ? this._formatTime(msg.time) : "--:--";
        const type = (msg.type || "system").toLowerCase();
        const from = msg.from || "?";
        const body = msg.message || "";

        // Light-delay annotation
        let delayTag = "";
        if (msg.delay_seconds > 0.5) {
          delayTag = ` <span class="msg-delay">+${msg.delay_seconds.toFixed(1)}s light delay</span>`;
        }

        // Diplomatic state badge for hail responses
        let diploBadge = "";
        if (msg.diplomatic_state && msg.diplomatic_state !== "unknown") {
          const color = DIPLO_COLORS[msg.diplomatic_state] || DIPLO_COLORS.unknown;
          diploBadge = ` <span class="diplo-badge" style="color:${color};border:1px solid ${color}">${msg.diplomatic_state.toUpperCase()}</span>`;
        }

        // Response type indicator for hail responses
        let responseTag = "";
        if (msg.response_type === "warning") {
          responseTag = ' <span style="color:var(--status-critical,#ff4444)">[THREAT]</span>';
        } else if (msg.response_type === "no_response") {
          responseTag = ' <span style="color:var(--text-dim,#555566)">[NO RESPONSE]</span>';
        }

        const to = msg.to ? ` &rarr; ${msg.to}` : "";

        return `
          <div class="msg-entry">
            <span class="msg-time">[${time}]</span>
            <span class="msg-type ${type}">${type.replace("_", " ").toUpperCase()}</span>${diploBadge}${responseTag}<span class="msg-route">: ${from}${to}</span>${delayTag}
            <br><span class="msg-body">${this._escapeHtml(body)}</span>
          </div>`;
      })
      .join("");
  }

  _formatTime(t) {
    if (typeof t === "string") return t;
    if (typeof t === "number") {
      const mins = Math.floor(t / 60);
      const secs = Math.floor(t % 60);
      return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return "--:--";
  }

  _escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* -----------------------------------------------------------------------
   * _bindControls — attaches event listeners after render.
   * Handles all tier variants; missing elements are silently skipped.
   * ----------------------------------------------------------------------- */
  _bindControls(comms, targetId) {
    // Transponder toggle (all tiers except cpu-assist)
    const btnXpdr = this.shadowRoot.getElementById("btn-transponder-toggle");
    if (btnXpdr) {
      btnXpdr.addEventListener("click", () => {
        this._sendCommand("set_transponder", { enabled: !comms.transponder_enabled });
      });
    }

    // Set IFF code (manual + raw)
    const btnSetIFF = this.shadowRoot.getElementById("btn-set-iff");
    const inputIFF = this.shadowRoot.getElementById("input-iff-code");
    if (btnSetIFF && inputIFF) {
      const setIFF = () => {
        const code = inputIFF.value.trim();
        if (code) this._sendCommand("set_transponder", { code });
      };
      btnSetIFF.addEventListener("click", setIFF);
      inputIFF.addEventListener("keydown", (e) => { if (e.key === "Enter") setIFF(); });
    }

    // Spoof toggle (raw only)
    const btnSpoof = this.shadowRoot.getElementById("btn-spoof-toggle");
    if (btnSpoof) {
      btnSpoof.addEventListener("click", () => {
        this._sendCommand("set_transponder", { spoofed: !comms.is_spoofed });
      });
    }

    // Set spoof identity (raw only)
    const btnSetSpoof = this.shadowRoot.getElementById("btn-set-spoof");
    if (btnSetSpoof) {
      btnSetSpoof.addEventListener("click", () => {
        const cls = this.shadowRoot.getElementById("input-spoof-class")?.value.trim();
        const fac = this.shadowRoot.getElementById("input-spoof-faction")?.value.trim();
        const args = {};
        if (cls) args.declared_class = cls;
        if (fac) args.declared_faction = fac;
        if (Object.keys(args).length > 0) {
          this._sendCommand("set_transponder", args);
        }
      });
    }

    // Hail current target button (raw tier)
    const btnHailTarget = this.shadowRoot.getElementById("btn-hail-target");
    if (btnHailTarget && targetId) {
      btnHailTarget.addEventListener("click", () => {
        this._sendCommand("hail_contact", { target: targetId, message: "Hailing..." });
      });
    }

    // Hail manual input (raw + manual tiers)
    const btnHail = this.shadowRoot.getElementById("btn-hail");
    const inputHailTarget = this.shadowRoot.getElementById("input-hail-target");
    if (btnHail && inputHailTarget) {
      const doHail = () => {
        // Manual tier has a raw-message textarea, use it if present
        const rawMsg = this.shadowRoot.getElementById("input-raw-message");
        const target = inputHailTarget.value.trim();
        const message = rawMsg ? rawMsg.value.trim() || "Hailing..." : "Hailing...";
        if (target) {
          this._sendCommand("hail_contact", { target, message });
          inputHailTarget.value = "";
          if (rawMsg) rawMsg.value = "";
        }
      };
      btnHail.addEventListener("click", doHail);
      inputHailTarget.addEventListener("keydown", (e) => { if (e.key === "Enter") doHail(); });
    }

    // Frequency tuning (manual tier)
    const btnSetFreq = this.shadowRoot.getElementById("btn-set-freq");
    const inputFreq = this.shadowRoot.getElementById("input-frequency");
    if (btnSetFreq && inputFreq) {
      const setFreq = () => {
        const freq = parseFloat(inputFreq.value);
        if (!isNaN(freq) && freq > 0) {
          this._sendCommand("set_radio_frequency", { frequency: freq });
        }
      };
      btnSetFreq.addEventListener("click", setFreq);
      inputFreq.addEventListener("keydown", (e) => { if (e.key === "Enter") setFreq(); });
    }

    // TX power slider (manual tier)
    const inputTxPower = this.shadowRoot.getElementById("input-tx-power");
    const txReadout = this.shadowRoot.getElementById("tx-power-readout");
    if (inputTxPower) {
      inputTxPower.addEventListener("input", () => {
        if (txReadout) txReadout.textContent = inputTxPower.value + " W";
      });
      inputTxPower.addEventListener("change", () => {
        this._sendCommand("set_radio_power", { power: parseInt(inputTxPower.value, 10) });
      });
    }

    // Broadcast (raw + arcade tiers)
    const btnBroadcast = this.shadowRoot.getElementById("btn-broadcast");
    const inputBroadcastMsg = this.shadowRoot.getElementById("input-broadcast-msg");
    const selectChannel = this.shadowRoot.getElementById("select-channel");
    if (btnBroadcast && inputBroadcastMsg) {
      const doBroadcast = () => {
        const message = inputBroadcastMsg.value.trim();
        const channel = selectChannel ? selectChannel.value : "general";
        if (message) {
          this._sendCommand("broadcast_message", { message, channel });
          inputBroadcastMsg.value = "";
        }
      };
      btnBroadcast.addEventListener("click", doBroadcast);
      inputBroadcastMsg.addEventListener("keydown", (e) => { if (e.key === "Enter") doBroadcast(); });
    }

    // Contact hail buttons (arcade tier — delegated)
    const contactGrid = this.shadowRoot.querySelector(".contact-hail-grid");
    if (contactGrid) {
      contactGrid.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-hail-contact]");
        if (btn) {
          this._sendCommand("hail_contact", {
            target: btn.dataset.hailContact,
            message: "Hailing...",
          });
        }
      });
    }

    // Broadcast presets (arcade tier — delegated)
    const presetGrid = this.shadowRoot.querySelector(".preset-grid");
    if (presetGrid) {
      presetGrid.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-preset-idx]");
        if (btn) {
          const preset = BROADCAST_PRESETS[parseInt(btn.dataset.presetIdx, 10)];
          if (preset) {
            const shipName = stateManager.getShipState()?.name || "Unknown";
            const msg = preset.msg.replace("{ship}", shipName);
            this._sendCommand("broadcast_message", { message: msg, channel: preset.channel });
          }
        }
      });
    }

    // Distress beacon (all tiers)
    const btnDistress = this.shadowRoot.getElementById("btn-distress");
    if (btnDistress) {
      btnDistress.addEventListener("click", () => {
        this._sendCommand("set_distress", { enabled: !comms.distress_beacon_enabled });
      });
    }

    // Auto-comms toggle (cpu-assist tier)
    const autoToggle = this.shadowRoot.getElementById("auto-comms-toggle");
    if (autoToggle) {
      autoToggle.addEventListener("click", () => {
        const ship = stateManager.getShipState();
        wsClient.sendShipCommand(
          ship?.auto_comms?.enabled ? "disable_auto_comms" : "enable_auto_comms", {}
        );
      });
    }

    // Comms policy selector (cpu-assist tier — delegated)
    const policyRow = this.shadowRoot.getElementById("comms-policy-row");
    if (policyRow) {
      policyRow.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-policy]");
        if (btn) {
          wsClient.sendShipCommand("set_comms_policy", { policy: btn.dataset.policy });
        }
      });
    }

    // Proposals approve/deny (cpu-assist tier — delegated)
    const proposalsEl = this.shadowRoot.getElementById("comms-proposals");
    if (proposalsEl) {
      proposalsEl.addEventListener("click", (e) => {
        const approveBtn = e.target.closest("[data-approve]");
        const denyBtn = e.target.closest("[data-deny]");
        if (approveBtn) {
          wsClient.sendShipCommand("approve_comms", { proposal_id: approveBtn.dataset.approve });
        }
        if (denyBtn) {
          wsClient.sendShipCommand("deny_comms", { proposal_id: denyBtn.dataset.deny });
        }
      });
    }

    // Auto-scroll message log
    const logEl = this.shadowRoot.getElementById("message-log");
    if (logEl) logEl.scrollTop = 0;
  }
}

customElements.define("comms-control-panel", CommsControlPanel);
export { CommsControlPanel };
