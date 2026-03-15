/**
 * Station Chat Component
 * Inter-station text messaging for crew coordination.
 * Polls server for new messages and allows sending to specific stations or all.
 */

import { wsClient } from "../js/ws-client.js";

const STATION_COLORS = {
  captain: "#ffcc00",
  helm: "#00aaff",
  tactical: "#ff4444",
  ops: "#00ff88",
  engineering: "#ff8800",
  comms: "#aa88ff",
  science: "#44ddff",
  fleet_commander: "#ff66cc",
};

const POLL_INTERVAL_MS = 1000;

class StationChat extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._messages = [];
    this._latestId = 0;
    this._pollTimer = null;
    this._targetStation = "all";
  }

  connectedCallback() {
    this.render();
    this._bindEvents();
    this._startPolling();
  }

  disconnectedCallback() {
    this._stopPolling();
  }

  _startPolling() {
    this._stopPolling();
    this._poll();
    this._pollTimer = setInterval(() => this._poll(), POLL_INTERVAL_MS);
  }

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  async _poll() {
    if (!wsClient.isConnected) return;
    try {
      const resp = await wsClient.send("get_station_messages", {
        since_id: this._latestId,
      });
      if (resp && resp.ok !== false && resp.messages) {
        const newMsgs = resp.messages;
        if (newMsgs.length > 0) {
          this._messages.push(...newMsgs);
          // Keep only last 100 in UI
          if (this._messages.length > 100) {
            this._messages = this._messages.slice(-100);
          }
          this._latestId = newMsgs[newMsgs.length - 1].id;
          this._renderMessages();
        }
      }
    } catch {
      // Polling failures are non-critical
    }
  }

  async _sendMessage() {
    const input = this.shadowRoot.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;

    try {
      await wsClient.send("station_message", {
        to: this._targetStation,
        text,
      });
      input.value = "";
    } catch (err) {
      console.error("Failed to send station message:", err);
    }
  }

  _bindEvents() {
    const input = this.shadowRoot.getElementById("chat-input");
    const sendBtn = this.shadowRoot.getElementById("send-btn");
    const targetSelect = this.shadowRoot.getElementById("target-select");

    sendBtn.addEventListener("click", () => this._sendMessage());
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this._sendMessage();
      }
    });
    targetSelect.addEventListener("change", (e) => {
      this._targetStation = e.target.value;
    });
  }

  _renderMessages() {
    const container = this.shadowRoot.getElementById("messages");
    if (!container) return;

    // Only render last 50 for performance
    const visible = this._messages.slice(-50);
    container.innerHTML = visible.map((m) => {
      const color = STATION_COLORS[m.from_station] || "#888899";
      const label = m.from_station.toUpperCase();
      const target = m.to === "all" ? "" : ` > ${m.to.toUpperCase()}`;
      const time = new Date(m.timestamp * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      return `<div class="msg">
        <span class="time">${time}</span>
        <span class="station" style="color:${color}">[${label}${target}]</span>
        <span class="text">${this._escapeHtml(m.text)}</span>
      </div>`;
    }).join("");

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;
  }

  _escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  render() {
    const stationOptions = [
      '<option value="all">ALL STATIONS</option>',
      ...Object.keys(STATION_COLORS).map(
        (s) => `<option value="${s}">${s.toUpperCase()}</option>`
      ),
    ].join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          height: 100%;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          color: var(--text-primary, #e0e0e0);
        }

        .messages {
          flex: 1;
          overflow-y: auto;
          padding: 8px;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .msg {
          display: flex;
          gap: 6px;
          line-height: 1.4;
          padding: 2px 0;
        }

        .time {
          color: var(--text-dim, #555566);
          flex-shrink: 0;
        }

        .station {
          font-weight: 600;
          flex-shrink: 0;
        }

        .text {
          word-break: break-word;
        }

        .input-row {
          display: flex;
          gap: 4px;
          padding: 8px;
          border-top: 1px solid var(--border-default, #2a2a3a);
          background: var(--bg-input, #1a1a24);
        }

        select {
          background: var(--bg-panel, #12121a);
          color: var(--text-primary, #e0e0e0);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          padding: 4px 6px;
          font-family: inherit;
          font-size: 0.7rem;
          min-width: 80px;
        }

        input {
          flex: 1;
          background: var(--bg-panel, #12121a);
          color: var(--text-primary, #e0e0e0);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          padding: 6px 8px;
          font-family: inherit;
          font-size: 0.75rem;
          outline: none;
        }

        input:focus {
          border-color: var(--status-info, #00aaff);
        }

        button {
          background: var(--status-info, #00aaff);
          color: #000;
          border: none;
          border-radius: 4px;
          padding: 6px 12px;
          font-family: inherit;
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
        }

        button:hover {
          opacity: 0.9;
        }

        .empty {
          color: var(--text-dim, #555566);
          text-align: center;
          padding: 24px;
          font-style: italic;
        }
      </style>

      <div class="messages" id="messages">
        <div class="empty">No messages yet. Coordinate with your crew.</div>
      </div>

      <div class="input-row">
        <select id="target-select">${stationOptions}</select>
        <input type="text" id="chat-input" placeholder="Message..." maxlength="500" />
        <button id="send-btn">SEND</button>
      </div>
    `;
  }
}

customElements.define("station-chat", StationChat);
export { StationChat };
