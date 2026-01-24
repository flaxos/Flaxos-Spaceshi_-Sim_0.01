/**
 * Connection Status Component
 * Displays WebSocket and TCP connection status with server info
 */

import { wsClient } from "../js/ws-client.js";

class ConnectionStatus extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this.render();
    this._bindEvents();
    this._updateDisplay();
  }

  disconnectedCallback() {
    this._unbindEvents();
  }

  _bindEvents() {
    this._onStatusChange = (e) => this._updateDisplay();
    this._onConnectionStatus = (e) => this._updateDisplay();
    this._onLatency = (e) => this._updateLatency(e.detail.latency);

    wsClient.addEventListener("status_change", this._onStatusChange);
    wsClient.addEventListener("connection_status", this._onConnectionStatus);
    wsClient.addEventListener("latency", this._onLatency);
  }

  _unbindEvents() {
    wsClient.removeEventListener("status_change", this._onStatusChange);
    wsClient.removeEventListener("connection_status", this._onConnectionStatus);
    wsClient.removeEventListener("latency", this._onLatency);
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          align-items: center;
          gap: 16px;
          font-family: var(--font-sans, "Inter", system-ui, sans-serif);
          font-size: 0.85rem;
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .status-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: #555566;
          box-shadow: 0 0 4px rgba(0, 0, 0, 0.3);
          transition: all 0.3s ease;
        }

        .status-dot.connected {
          background: #00ff88;
          box-shadow: 0 0 8px #00ff88;
        }

        .status-dot.connecting {
          background: #ffaa00;
          box-shadow: 0 0 8px #ffaa00;
          animation: pulse 1.5s ease-in-out infinite;
        }

        .status-dot.disconnected {
          background: #555566;
        }

        .status-dot.error {
          background: #ff4444;
          box-shadow: 0 0 8px #ff4444;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        .status-label {
          color: #e0e0e0;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .server-info {
          color: #888899;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
        }

        .latency {
          color: #888899;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
        }

        .latency.good { color: #00ff88; }
        .latency.medium { color: #ffaa00; }
        .latency.bad { color: #ff4444; }

        .actions {
          display: flex;
          gap: 8px;
        }

        button {
          font-family: inherit;
          font-size: 0.75rem;
          padding: 4px 12px;
          background: #1a1a24;
          border: 1px solid #2a2a3a;
          border-radius: 4px;
          color: #e0e0e0;
          cursor: pointer;
          transition: all 0.1s ease;
        }

        button:hover {
          background: #22222e;
          border-color: #3a3a4a;
        }

        button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .tcp-status {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          font-size: 0.75rem;
        }

        .tcp-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #555566;
        }

        .tcp-dot.connected {
          background: #00ff88;
        }
      </style>

      <div class="status-indicator">
        <span class="status-dot disconnected" id="ws-dot"></span>
        <span class="status-label" id="status-text">DISCONNECTED</span>
      </div>

      <div class="server-info" id="server-info">--</div>

      <div class="tcp-status">
        <span class="tcp-dot" id="tcp-dot"></span>
        <span id="tcp-text">TCP: --</span>
      </div>

      <div class="latency" id="latency">--</div>

      <div class="actions">
        <button id="connect-btn">Connect</button>
        <button id="disconnect-btn" disabled>Disconnect</button>
      </div>
    `;

    this._setupButtons();
  }

  _setupButtons() {
    const connectBtn = this.shadowRoot.getElementById("connect-btn");
    const disconnectBtn = this.shadowRoot.getElementById("disconnect-btn");

    connectBtn.addEventListener("click", async () => {
      connectBtn.disabled = true;
      try {
        await wsClient.connect();
      } catch (error) {
        console.error("Connection failed:", error);
      }
      this._updateDisplay();
    });

    disconnectBtn.addEventListener("click", () => {
      wsClient.disconnect();
      this._updateDisplay();
    });
  }

  _updateDisplay() {
    const info = wsClient.getConnectionInfo();
    const wsDot = this.shadowRoot.getElementById("ws-dot");
    const statusText = this.shadowRoot.getElementById("status-text");
    const serverInfo = this.shadowRoot.getElementById("server-info");
    const tcpDot = this.shadowRoot.getElementById("tcp-dot");
    const tcpText = this.shadowRoot.getElementById("tcp-text");
    const connectBtn = this.shadowRoot.getElementById("connect-btn");
    const disconnectBtn = this.shadowRoot.getElementById("disconnect-btn");

    // Update WebSocket status
    wsDot.className = `status-dot ${info.status}`;
    statusText.textContent = info.status.toUpperCase();

    // Update server info
    if (info.tcpHost && info.tcpPort) {
      serverInfo.textContent = `Server: ${info.tcpHost}:${info.tcpPort}`;
    } else {
      serverInfo.textContent = `Bridge: ${info.url}`;
    }

    // Update TCP status
    tcpDot.className = `tcp-dot ${info.tcpConnected ? "connected" : ""}`;
    tcpText.textContent = info.tcpConnected ? "TCP: OK" : "TCP: --";

    // Update buttons
    connectBtn.disabled = info.status === "connected" || info.status === "connecting";
    disconnectBtn.disabled = info.status === "disconnected";
  }

  _updateLatency(latency) {
    const latencyEl = this.shadowRoot.getElementById("latency");
    if (latency === null) {
      latencyEl.textContent = "--";
      latencyEl.className = "latency";
      return;
    }

    latencyEl.textContent = `${latency}ms`;

    if (latency < 50) {
      latencyEl.className = "latency good";
    } else if (latency < 150) {
      latencyEl.className = "latency medium";
    } else {
      latencyEl.className = "latency bad";
    }
  }
}

customElements.define("connection-status", ConnectionStatus);
export { ConnectionStatus };
