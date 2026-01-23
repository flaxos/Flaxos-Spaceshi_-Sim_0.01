/**
 * Quick Actions Bar
 * Common actions: refuel, e-stop, status, reconnect
 */

import { wsClient } from "../js/ws-client.js";

class QuickActions extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this.render();
    this._setupActions();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          gap: 8px;
          padding: 12px 16px;
          background: var(--bg-panel, #12121a);
          border-top: 1px solid var(--border-default, #2a2a3a);
          flex-wrap: wrap;
          justify-content: center;
        }

        .action-btn {
          padding: 10px 16px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          cursor: pointer;
          min-height: 44px;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          transition: all 0.1s ease;
        }

        .action-btn:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--border-active, #3a3a4a);
        }

        .action-btn:active {
          transform: scale(0.98);
        }

        .action-btn.danger {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .action-btn.danger:hover {
          background: rgba(255, 68, 68, 0.1);
        }

        .action-btn.success {
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .action-btn.success:hover {
          background: rgba(0, 255, 136, 0.1);
        }

        .action-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .action-btn.pending {
          opacity: 0.7;
          pointer-events: none;
        }

        .action-btn.pending::after {
          content: '...';
        }
      </style>

      <button class="action-btn success" id="refuel-btn">
        ⛽ Refuel
      </button>
      <button class="action-btn" id="status-btn">
        📊 Status
      </button>
      <button class="action-btn" id="contacts-btn">
        📡 Contacts
      </button>
      <button class="action-btn" id="ping-btn">
        🔊 Ping
      </button>
      <button class="action-btn danger" id="estop-btn">
        🛑 E-STOP
      </button>
      <button class="action-btn" id="reconnect-btn">
        🔄 Reconnect
      </button>
    `;
  }

  _setupActions() {
    const actions = {
      "refuel-btn": () => this._sendCommand("refuel"),
      "status-btn": () => this._sendCommand("status"),
      "contacts-btn": () => this._sendCommand("contacts"),
      "ping-btn": () => this._sendCommand("ping"),
      "estop-btn": () => this._emergencyStop(),
      "reconnect-btn": () => this._reconnect(),
    };

    for (const [id, handler] of Object.entries(actions)) {
      const btn = this.shadowRoot.getElementById(id);
      if (btn) {
        btn.addEventListener("click", handler);
      }
    }
  }

  async _sendCommand(cmd, args = {}) {
    const btn = this.shadowRoot.querySelector(`[id$="-btn"]`);

    try {
      await wsClient.send(cmd, args);
      this._flashSuccess();
    } catch (error) {
      console.error(`Command ${cmd} failed:`, error);
    }
  }

  async _emergencyStop() {
    if (!confirm("Execute emergency stop?")) {
      return;
    }

    const btn = this.shadowRoot.getElementById("estop-btn");
    btn.classList.add("pending");

    try {
      await wsClient.send("emergency_stop", {});
      this._showMessage("Emergency stop executed", "warning");
    } catch (error) {
      console.error("Emergency stop failed:", error);
      this._showMessage("Emergency stop failed", "error");
    } finally {
      btn.classList.remove("pending");
    }
  }

  _reconnect() {
    const btn = this.shadowRoot.getElementById("reconnect-btn");
    btn.classList.add("pending");

    wsClient.disconnect();
    setTimeout(async () => {
      try {
        await wsClient.connect();
        this._showMessage("Reconnected", "success");
      } catch (error) {
        this._showMessage("Connection failed", "error");
      } finally {
        btn.classList.remove("pending");
      }
    }, 500);
  }

  _flashSuccess() {
    // Brief visual feedback
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages && systemMessages.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("quick-actions", QuickActions);
export { QuickActions };
