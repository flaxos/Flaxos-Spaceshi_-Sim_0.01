/**
 * Comms Control Panel
 * Provides interactive controls for communications:
 * - Transponder toggle, IFF code management, and spoofing
 * - Radio hail (with light-speed delay) and broadcast messaging
 * - Diplomatic state indicators on contacts
 * - Distress beacon activation
 * - Message log with hail response rendering
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const CHANNELS = ["general", "fleet", "emergency", "tactical"];

/** Colour mapping for diplomatic states */
const DIPLO_COLORS = {
  allied: "var(--status-nominal, #00ff88)",
  neutral: "var(--status-info, #00aaff)",
  hostile: "var(--status-critical, #ff4444)",
  unknown: "var(--text-dim, #555566)",
};

class CommsControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._hailingTarget = null; // contact_id currently being hailed
  }

  connectedCallback() {
    this.render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
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
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const container = this.shadowRoot.getElementById("comms-content");
    if (!container) return;

    const comms = ship?.comms;
    if (!comms) {
      container.innerHTML = '<div class="no-comms">Comms system not available</div>';
      return;
    }

    const status = (comms.status || "offline").toUpperCase();

    // Determine mode class
    let modeClass = "silent";
    if (comms.status === "DISTRESS" || comms.distress_active) modeClass = "distress";
    else if (comms.status === "EMCON" || comms.emcon_suppressed) modeClass = "emcon";
    else if (comms.status === "offline" || !comms.enabled) modeClass = "offline";
    else if (comms.status === "active" || comms.enabled) modeClass = "active";

    // Transponder state class
    let xpdrClass = "off";
    if (comms.is_spoofed && comms.transponder_active) xpdrClass = "spoofed";
    else if (comms.transponder_active) xpdrClass = "active";
    else if (comms.transponder_enabled && comms.emcon_suppressed) xpdrClass = "suppressed";

    let xpdrStatus = "OFF";
    if (comms.is_spoofed && comms.transponder_active) xpdrStatus = "SPOOFED";
    else if (comms.transponder_active) xpdrStatus = "ACTIVE";
    else if (comms.transponder_enabled && comms.emcon_suppressed) xpdrStatus = "EMCON SUPPRESSED";
    else if (comms.transponder_enabled) xpdrStatus = "ENABLED";

    const radioRange = comms.radio_range
      ? (comms.radio_range >= 1000
          ? (comms.radio_range / 1000).toFixed(1) + " Mm"
          : comms.radio_range.toFixed(0) + " km")
      : "--";

    const pendingBadge = comms.pending_hails > 0
      ? `<span class="pending-badge">${comms.pending_hails}</span>`
      : "";

    const channelOptions = CHANNELS
      .map(ch => `<option value="${ch}">${ch.toUpperCase()}</option>`)
      .join("");

    // Get current target contact for the hail button
    const targetId = ship?.target_id || "";
    const isHailing = comms.pending_hails > 0;
    const hailBtnClass = isHailing ? "hailing" : (targetId ? "" : "disabled");
    const hailBtnText = isHailing ? "HAILING..." : "HAIL TARGET";
    const hailTitle = targetId
      ? `Hail contact ${targetId}`
      : "Select a target first";

    // Spoof badge
    const spoofBadge = comms.is_spoofed
      ? '<span class="spoof-badge">SPOOFED</span>'
      : '';

    container.innerHTML = `
      <div class="comms-mode ${modeClass}">
        <div class="mode-dot"></div>
        <span>COMMS: ${status}</span>
      </div>

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

      <!-- RADIO -->
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

      <!-- DISTRESS BEACON -->
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
      </div>

      <!-- MESSAGE LOG -->
      <div class="section">
        <div class="section-title">Message Log (${comms.message_count || 0})</div>
        <div class="message-log" id="message-log">
          ${this._renderMessages(comms.recent_messages)}
        </div>
      </div>
    `;

    this._bindControls(comms, targetId);
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

  _bindControls(comms, targetId) {
    // Transponder toggle
    const btnXpdr = this.shadowRoot.getElementById("btn-transponder-toggle");
    if (btnXpdr) {
      btnXpdr.addEventListener("click", () => {
        this._sendCommand("set_transponder", { enabled: !comms.transponder_enabled });
      });
    }

    // Set IFF code
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

    // Spoof toggle
    const btnSpoof = this.shadowRoot.getElementById("btn-spoof-toggle");
    if (btnSpoof) {
      btnSpoof.addEventListener("click", () => {
        this._sendCommand("set_transponder", { spoofed: !comms.is_spoofed });
      });
    }

    // Set spoof identity
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

    // Hail current target button
    const btnHailTarget = this.shadowRoot.getElementById("btn-hail-target");
    if (btnHailTarget && targetId) {
      btnHailTarget.addEventListener("click", () => {
        this._sendCommand("hail_contact", { target: targetId, message: "Hailing..." });
      });
    }

    // Hail manual input
    const btnHail = this.shadowRoot.getElementById("btn-hail");
    const inputHailTarget = this.shadowRoot.getElementById("input-hail-target");
    if (btnHail && inputHailTarget) {
      const doHail = () => {
        const target = inputHailTarget.value.trim();
        if (target) {
          this._sendCommand("hail_contact", { target, message: "Hailing..." });
          inputHailTarget.value = "";
        }
      };
      btnHail.addEventListener("click", doHail);
      inputHailTarget.addEventListener("keydown", (e) => { if (e.key === "Enter") doHail(); });
    }

    // Broadcast
    const btnBroadcast = this.shadowRoot.getElementById("btn-broadcast");
    const inputBroadcastMsg = this.shadowRoot.getElementById("input-broadcast-msg");
    const selectChannel = this.shadowRoot.getElementById("select-channel");
    if (btnBroadcast && inputBroadcastMsg && selectChannel) {
      const doBroadcast = () => {
        const message = inputBroadcastMsg.value.trim();
        const channel = selectChannel.value;
        if (message) {
          this._sendCommand("broadcast_message", { message, channel });
          inputBroadcastMsg.value = "";
        }
      };
      btnBroadcast.addEventListener("click", doBroadcast);
      inputBroadcastMsg.addEventListener("keydown", (e) => { if (e.key === "Enter") doBroadcast(); });
    }

    // Distress beacon
    const btnDistress = this.shadowRoot.getElementById("btn-distress");
    if (btnDistress) {
      btnDistress.addEventListener("click", () => {
        this._sendCommand("set_distress", { enabled: !comms.distress_beacon_enabled });
      });
    }

    // Auto-scroll message log
    const logEl = this.shadowRoot.getElementById("message-log");
    if (logEl) logEl.scrollTop = 0;

    this._updateAutoCommsPanel();
  }

  // --- Auto-Comms (CPU-ASSIST tier) ---
  _updateAutoCommsPanel() {
    let panel = this.shadowRoot.getElementById("auto-comms-panel");
    const tier = window.controlTier || "raw";
    if (tier !== "cpu-assist") { if (panel) panel.style.display = "none"; return; }
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "auto-comms-panel";
      panel.style.cssText = "border:1px solid rgba(153,119,221,0.3);border-radius:4px;padding:8px;margin:8px 0;background:rgba(153,119,221,0.05);";
      panel.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="color:#9977dd;font-size:0.7rem;font-weight:600;letter-spacing:0.5px;">AUTO COMMS</span>
        <button id="auto-comms-toggle" style="background:rgba(153,119,221,0.15);color:#9977dd;border:1px solid rgba(153,119,221,0.3);padding:2px 10px;border-radius:3px;cursor:pointer;font-size:0.65rem;">ENABLE</button>
      </div>
      <div style="display:flex;gap:4px;margin-bottom:6px;" id="comms-policy-row">
        <button data-policy="open_comms" style="flex:1;background:var(--bg-input);color:var(--text-secondary);border:1px solid var(--border-default);padding:3px;border-radius:3px;cursor:pointer;font-size:0.6rem;">OPEN</button>
        <button data-policy="radio_silence" style="flex:1;background:var(--bg-input);color:var(--text-secondary);border:1px solid var(--border-default);padding:3px;border-radius:3px;cursor:pointer;font-size:0.6rem;">SILENCE</button>
        <button data-policy="diplomatic_mode" style="flex:1;background:var(--bg-input);color:var(--text-secondary);border:1px solid var(--border-default);padding:3px;border-radius:3px;cursor:pointer;font-size:0.6rem;">DIPLOMATIC</button>
      </div>
      <div id="comms-proposals"></div>`;
      const content = this.shadowRoot.querySelector(".comms-content") || this.shadowRoot.getElementById("comms-content") || this.shadowRoot.firstElementChild;
      if (content) content.prepend(panel); else this.shadowRoot.appendChild(panel);
      panel.querySelector("#auto-comms-toggle").addEventListener("click", () => {
        const ship = stateManager.getShipState();
        wsClient.sendShipCommand(ship?.auto_comms?.enabled ? "disable_auto_comms" : "enable_auto_comms", {});
      });
      panel.querySelector("#comms-policy-row").addEventListener("click", (e) => {
        const btn = e.target.closest("[data-policy]");
        if (btn) wsClient.sendShipCommand("set_comms_policy", { policy: btn.dataset.policy });
      });
      panel.querySelector("#comms-proposals").addEventListener("click", (e) => {
        const a = e.target.closest("[data-approve]"); const d = e.target.closest("[data-deny]");
        if (a) wsClient.sendShipCommand("approve_comms", { proposal_id: a.dataset.approve });
        if (d) wsClient.sendShipCommand("deny_comms", { proposal_id: d.dataset.deny });
      });
    }
    panel.style.display = "block";
    const ship = stateManager.getShipState();
    const st = ship?.auto_comms || {};
    const toggle = panel.querySelector("#auto-comms-toggle");
    toggle.textContent = st.enabled ? "DISABLE" : "ENABLE";
    toggle.style.background = st.enabled ? "rgba(0,255,136,0.15)" : "rgba(153,119,221,0.15)";
    const policy = st.policy || "open_comms";
    panel.querySelectorAll("[data-policy]").forEach(b => {
      b.style.borderColor = b.dataset.policy === policy ? "#9977dd" : "var(--border-default)";
      b.style.color = b.dataset.policy === policy ? "#9977dd" : "var(--text-secondary)";
    });
    const proposals = st.proposals || [];
    const pc = panel.querySelector("#comms-proposals");
    pc.innerHTML = proposals.length === 0
      ? '<div style="color:var(--text-dim);font-size:0.65rem;">No pending proposals</div>'
      : proposals.map(p => `<div style="background:var(--bg-input);border:1px solid var(--border-default);border-radius:4px;padding:5px 8px;margin:3px 0;font-size:0.65rem;">
          <div style="color:var(--text-primary);margin-bottom:3px;">${p.description || p.action}</div>
          <button data-approve="${p.id}" style="background:rgba(0,255,136,0.15);color:#00ff88;border:1px solid rgba(0,255,136,0.3);padding:1px 8px;border-radius:3px;cursor:pointer;font-size:0.6rem;margin-right:3px;">APPROVE</button>
          <button data-deny="${p.id}" style="background:rgba(255,68,68,0.15);color:#ff4444;border:1px solid rgba(255,68,68,0.3);padding:1px 8px;border-radius:3px;cursor:pointer;font-size:0.6rem;">DENY</button>
        </div>`).join('');
  }
}

customElements.define("comms-control-panel", CommsControlPanel);
export { CommsControlPanel };
