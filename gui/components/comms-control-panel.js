/**
 * Comms Control Panel
 * Provides interactive controls for communications:
 * - Transponder toggle and IFF code management
 * - Radio hail and broadcast messaging
 * - Distress beacon activation
 * - Message log display
 */

import { stateManager } from "../js/state-manager.js";

const CHANNELS = ["general", "fleet", "emergency", "tactical"];

class CommsControlPanel extends HTMLElement {
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

        .status-value.suppressed {
          color: var(--status-warning, #ffaa00);
        }

        .status-value.off {
          color: var(--text-dim, #555566);
        }

        .status-value.info {
          color: var(--status-info, #00aaff);
        }

        /* Comms mode indicator — mirrors ECM mode indicator pattern */
        .comms-mode {
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

        .comms-mode.active {
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .comms-mode.silent {
          background: rgba(85, 85, 102, 0.15);
          border: 1px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }

        .comms-mode.emcon {
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
        }

        .comms-mode.distress {
          background: rgba(255, 68, 68, 0.15);
          border: 1px solid var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
          animation: distress-flash 1s ease-in-out infinite;
        }

        .comms-mode.offline {
          background: rgba(255, 68, 68, 0.08);
          border: 1px solid rgba(255, 68, 68, 0.3);
          color: var(--status-critical, #ff4444);
        }

        .mode-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: currentColor;
        }

        .comms-mode.active .mode-dot {
          animation: pulse 1.5s ease-in-out infinite;
        }

        .comms-mode.distress .mode-dot {
          animation: pulse-fast 0.6s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        @keyframes pulse-fast {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.2; }
        }

        @keyframes distress-flash {
          0%, 100% { border-color: var(--status-critical, #ff4444); }
          50% { border-color: rgba(255, 68, 68, 0.3); }
        }

        /* Buttons */
        .comms-btn {
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
          min-height: 32px;
        }

        .comms-btn:hover {
          background: rgba(0, 170, 255, 0.2);
          border-color: var(--status-info, #00aaff);
        }

        .comms-btn.active {
          background: rgba(0, 255, 136, 0.15);
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .comms-btn.disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .comms-btn.distress {
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid rgba(255, 68, 68, 0.3);
          color: var(--status-critical, #ff4444);
        }

        .comms-btn.distress:hover {
          background: rgba(255, 68, 68, 0.25);
          border-color: var(--status-critical, #ff4444);
        }

        .comms-btn.distress.active {
          background: rgba(255, 68, 68, 0.3);
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
          animation: distress-flash 1s ease-in-out infinite;
        }

        .comms-btn.full-width {
          width: 100%;
        }

        /* Input fields */
        .input-row {
          display: flex;
          gap: 6px;
          align-items: center;
          margin-bottom: 8px;
        }

        .comms-input {
          flex: 1;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          padding: 6px 8px;
          min-height: 28px;
          outline: none;
          transition: border-color 0.15s ease;
        }

        .comms-input:focus {
          border-color: var(--status-info, #00aaff);
        }

        .comms-input::placeholder {
          color: var(--text-dim, #555566);
          font-style: italic;
        }

        .comms-select {
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          padding: 6px 8px;
          min-height: 28px;
          outline: none;
          cursor: pointer;
          transition: border-color 0.15s ease;
        }

        .comms-select:focus {
          border-color: var(--status-info, #00aaff);
        }

        .comms-select option {
          background: var(--bg-primary, #0a0a0f);
          color: var(--text-primary, #e0e0e0);
        }

        .input-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.3px;
          margin-bottom: 4px;
        }

        .input-group {
          margin-bottom: 10px;
        }

        /* Transponder code display */
        .transponder-code {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1rem;
          font-weight: 700;
          letter-spacing: 2px;
          padding: 6px 10px;
          border-radius: 4px;
          text-align: center;
          margin-bottom: 8px;
        }

        .transponder-code.active {
          background: rgba(0, 255, 136, 0.08);
          border: 1px solid rgba(0, 255, 136, 0.3);
          color: var(--status-nominal, #00ff88);
        }

        .transponder-code.suppressed {
          background: rgba(255, 170, 0, 0.08);
          border: 1px solid rgba(255, 170, 0, 0.3);
          color: var(--status-warning, #ffaa00);
          text-decoration: line-through;
        }

        .transponder-code.off {
          background: rgba(85, 85, 102, 0.08);
          border: 1px solid rgba(85, 85, 102, 0.3);
          color: var(--text-dim, #555566);
        }

        /* Transponder controls row */
        .transponder-controls {
          display: flex;
          gap: 6px;
          margin-top: 8px;
        }

        .transponder-controls .comms-btn {
          flex-shrink: 0;
        }

        /* Message log */
        .message-log {
          max-height: 200px;
          overflow-y: auto;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          padding: 6px;
        }

        .message-log::-webkit-scrollbar {
          width: 4px;
        }

        .message-log::-webkit-scrollbar-track {
          background: transparent;
        }

        .message-log::-webkit-scrollbar-thumb {
          background: var(--border-default, #2a2a3a);
          border-radius: 2px;
        }

        .msg-entry {
          padding: 3px 4px;
          border-bottom: 1px solid rgba(42, 42, 58, 0.5);
          font-size: 0.65rem;
          line-height: 1.4;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .msg-entry:last-child {
          border-bottom: none;
        }

        .msg-time {
          color: var(--text-dim, #555566);
        }

        .msg-type {
          font-weight: 600;
          text-transform: uppercase;
        }

        .msg-type.hail { color: var(--status-info, #00aaff); }
        .msg-type.broadcast { color: var(--status-nominal, #00ff88); }
        .msg-type.distress { color: var(--status-critical, #ff4444); }
        .msg-type.system { color: var(--status-warning, #ffaa00); }
        .msg-type.iff { color: var(--text-secondary, #888899); }

        .msg-route {
          color: var(--text-secondary, #888899);
        }

        .msg-body {
          color: var(--text-primary, #e0e0e0);
        }

        .msg-empty {
          text-align: center;
          color: var(--text-dim, #555566);
          font-style: italic;
          padding: 12px 8px;
          font-size: 0.7rem;
        }

        /* Pending hails badge */
        .pending-badge {
          display: inline-block;
          background: var(--status-warning, #ffaa00);
          color: var(--bg-primary, #0a0a0f);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.6rem;
          font-weight: 700;
          padding: 1px 5px;
          border-radius: 8px;
          margin-left: 6px;
          vertical-align: middle;
        }

        .no-comms {
          color: var(--text-dim, #555566);
          font-style: italic;
          text-align: center;
          padding: 20px 10px;
          font-size: 0.75rem;
        }
      </style>

      <div id="comms-content">
        <div class="no-comms">Comms system not available</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const container = this.shadowRoot.getElementById("comms-content");

    if (!container) return;

    // Comms telemetry is a top-level field on the ship state
    const comms = ship?.comms;

    if (!comms) {
      container.innerHTML = '<div class="no-comms">Comms system not available</div>';
      return;
    }

    const status = (comms.status || "offline").toUpperCase();

    // Determine mode class for the top-level indicator
    let modeClass = "silent";
    if (comms.status === "DISTRESS" || comms.distress_active) {
      modeClass = "distress";
    } else if (comms.status === "EMCON" || comms.emcon_suppressed) {
      modeClass = "emcon";
    } else if (comms.status === "offline" || !comms.enabled) {
      modeClass = "offline";
    } else if (comms.status === "active" || comms.enabled) {
      modeClass = "active";
    }

    // Transponder state class
    let xpdrClass = "off";
    if (comms.transponder_active) {
      xpdrClass = "active";
    } else if (comms.transponder_enabled && comms.emcon_suppressed) {
      xpdrClass = "suppressed";
    }

    // Transponder status text
    let xpdrStatus = "OFF";
    if (comms.transponder_active) {
      xpdrStatus = "ACTIVE";
    } else if (comms.transponder_enabled && comms.emcon_suppressed) {
      xpdrStatus = "EMCON SUPPRESSED";
    } else if (comms.transponder_enabled) {
      xpdrStatus = "ENABLED";
    }

    // Radio range formatting
    const radioRange = comms.radio_range
      ? (comms.radio_range >= 1000
          ? (comms.radio_range / 1000).toFixed(1) + " Mm"
          : comms.radio_range.toFixed(0) + " km")
      : "--";

    // Build pending hails badge
    const pendingBadge = comms.pending_hails > 0
      ? `<span class="pending-badge">${comms.pending_hails}</span>`
      : "";

    // Build channel options
    const channelOptions = CHANNELS
      .map(ch => `<option value="${ch}">${ch.toUpperCase()}</option>`)
      .join("");

    container.innerHTML = `
      <!-- Comms Mode Indicator -->
      <div class="comms-mode ${modeClass}">
        <div class="mode-dot"></div>
        <span>COMMS: ${status}</span>
      </div>

      <!-- TRANSPONDER Section -->
      <div class="section">
        <div class="section-title">Transponder</div>

        <div class="transponder-code ${xpdrClass}">
          ${comms.transponder_code || "----"}
        </div>

        <div class="status-row">
          <span class="status-label">Status</span>
          <span class="status-value ${xpdrClass}">${xpdrStatus}</span>
        </div>

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
      </div>

      <!-- RADIO Section -->
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
            <input type="text" class="comms-input" id="input-hail-target"
                   placeholder="Target ID" />
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

      <!-- DISTRESS BEACON Section -->
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

      <!-- MESSAGE LOG Section -->
      <div class="section">
        <div class="section-title">Message Log (${comms.message_count || 0})</div>
        <div class="message-log" id="message-log">
          ${this._renderMessages(comms.recent_messages)}
        </div>
      </div>
    `;

    // Bind interactive elements
    this._bindControls(comms);
  }

  /**
   * Render recent messages into the log.
   * Format: [time] TYPE: from -> to: message
   */
  _renderMessages(messages) {
    if (!messages || messages.length === 0) {
      return '<div class="msg-empty">No messages</div>';
    }

    // Show newest first
    return messages
      .slice()
      .reverse()
      .map(msg => {
        const time = msg.time != null ? this._formatTime(msg.time) : "--:--";
        const type = (msg.type || "system").toLowerCase();
        const from = msg.from || "?";
        const to = msg.to || "ALL";
        const body = msg.message || "";

        return `
          <div class="msg-entry">
            <span class="msg-time">[${time}]</span>
            <span class="msg-type ${type}">${type.toUpperCase()}</span><span class="msg-route">: ${from} &rarr; ${to}:</span>
            <span class="msg-body">${this._escapeHtml(body)}</span>
          </div>`;
      })
      .join("");
  }

  /**
   * Format a time value for display.
   * Accepts seconds (float) or an already-formatted string.
   */
  _formatTime(t) {
    if (typeof t === "string") return t;
    if (typeof t === "number") {
      const mins = Math.floor(t / 60);
      const secs = Math.floor(t % 60);
      return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return "--:--";
  }

  /**
   * Basic HTML escaping to prevent injection in message display.
   */
  _escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  _bindControls(comms) {
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
      btnSetIFF.addEventListener("click", () => {
        const code = inputIFF.value.trim();
        if (code) {
          this._sendCommand("set_transponder", { code });
        }
      });
      // Also allow Enter key in the IFF input
      inputIFF.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          const code = inputIFF.value.trim();
          if (code) {
            this._sendCommand("set_transponder", { code });
          }
        }
      });
    }

    // Hail contact
    const btnHail = this.shadowRoot.getElementById("btn-hail");
    const inputHailTarget = this.shadowRoot.getElementById("input-hail-target");
    if (btnHail && inputHailTarget) {
      btnHail.addEventListener("click", () => {
        const target = inputHailTarget.value.trim();
        if (target) {
          this._sendCommand("hail_contact", { target, message: "Hailing..." });
          inputHailTarget.value = "";
        }
      });
      inputHailTarget.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          const target = inputHailTarget.value.trim();
          if (target) {
            this._sendCommand("hail_contact", { target, message: "Hailing..." });
            inputHailTarget.value = "";
          }
        }
      });
    }

    // Broadcast message
    const btnBroadcast = this.shadowRoot.getElementById("btn-broadcast");
    const inputBroadcastMsg = this.shadowRoot.getElementById("input-broadcast-msg");
    const selectChannel = this.shadowRoot.getElementById("select-channel");
    if (btnBroadcast && inputBroadcastMsg && selectChannel) {
      btnBroadcast.addEventListener("click", () => {
        const message = inputBroadcastMsg.value.trim();
        const channel = selectChannel.value;
        if (message) {
          this._sendCommand("broadcast_message", { message, channel });
          inputBroadcastMsg.value = "";
        }
      });
      inputBroadcastMsg.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          const message = inputBroadcastMsg.value.trim();
          const channel = selectChannel.value;
          if (message) {
            this._sendCommand("broadcast_message", { message, channel });
            inputBroadcastMsg.value = "";
          }
        }
      });
    }

    // Distress beacon toggle
    const btnDistress = this.shadowRoot.getElementById("btn-distress");
    if (btnDistress) {
      btnDistress.addEventListener("click", () => {
        this._sendCommand("set_distress", { enabled: !comms.distress_beacon_enabled });
      });
    }

    // Auto-scroll message log to bottom (newest messages shown first, so scroll to top)
    const logEl = this.shadowRoot.getElementById("message-log");
    if (logEl) {
      logEl.scrollTop = 0;
    }
  }
}

customElements.define("comms-control-panel", CommsControlPanel);
export { CommsControlPanel };
