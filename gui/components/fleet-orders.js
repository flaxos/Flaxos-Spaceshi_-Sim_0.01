/**
 * Fleet Orders — maneuver command panel.
 * Sends fleet_maneuver commands to the server via wsClient.
 */

import { wsClient } from "../js/ws-client.js";

const MANEUVERS = [
  { id: "intercept", label: "INTERCEPT", desc: "Pursue and engage target", color: "#ffaa00" },
  { id: "match_velocity", label: "MATCH VELOCITY", desc: "Match target velocity vector", color: "#4488ff" },
  { id: "hold", label: "HOLD POSITION", desc: "Maintain current position", color: "#00ff88" },
  { id: "evasive", label: "EVASIVE", desc: "Random evasive maneuvers", color: "#ff4444" },
];

class FleetOrders extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._active = null;
    this._pulseInterval = null;
  }

  connectedCallback() {
    this._render();
    this._bind();
  }

  disconnectedCallback() {
    clearInterval(this._pulseInterval);
    this._pulseInterval = null;
  }

  _render() {
    const buttons = MANEUVERS.map(m => `
      <button class="btn" data-maneuver="${m.id}" style="--btn-color: ${m.color}">
        <span class="btn-label">${m.label}</span>
        <span class="btn-desc">${m.desc}</span>
      </button>
    `).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          background: var(--bg-panel, #12121a);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          padding: 12px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }
        .status {
          font-size: 0.75rem;
          color: var(--text-dim, #666680);
          margin-bottom: 10px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .status span {
          color: var(--text-primary, #e0e0e0);
        }
        .grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }
        .btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          padding: 14px 8px;
          background: var(--bg-input, #1a1a2e);
          border: 2px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          cursor: pointer;
          transition: border-color 0.15s, background 0.15s;
        }
        .btn:hover {
          border-color: var(--btn-color);
          background: color-mix(in srgb, var(--btn-color) 8%, var(--bg-input, #1a1a2e));
        }
        .btn.active {
          border-color: var(--btn-color);
          animation: pulse 1.5s ease-in-out infinite;
        }
        .btn-label {
          font-size: 0.85rem;
          font-weight: 700;
          color: var(--btn-color);
        }
        .btn-desc {
          font-size: 0.65rem;
          color: var(--text-secondary, #a0a0b0);
        }
        @keyframes pulse {
          0%, 100% { box-shadow: 0 0 0 0 transparent; }
          50% { box-shadow: 0 0 8px 2px var(--btn-color); }
        }
      </style>
      <div class="status">Maneuver: <span id="current">NONE</span></div>
      <div class="grid">${buttons}</div>
    `;
  }

  _bind() {
    this.shadowRoot.querySelectorAll(".btn").forEach(btn => {
      btn.addEventListener("click", () => this._execute(btn.dataset.maneuver));
    });
  }

  async _execute(maneuver) {
    const fleetId = this.getAttribute("fleet-id") || "default";
    try {
      await wsClient.sendShipCommand("fleet_maneuver", {
        fleet_id: fleetId,
        maneuver,
        position: null,
        velocity: null,
      });
      this._setActive(maneuver);
    } catch (err) {
      console.error("Fleet maneuver failed:", err);
    }
  }

  _setActive(maneuver) {
    this._active = maneuver;
    const meta = MANEUVERS.find(m => m.id === maneuver);
    this.shadowRoot.getElementById("current").textContent = meta ? meta.label : "NONE";
    this.shadowRoot.querySelectorAll(".btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.maneuver === maneuver);
    });
  }
}

customElements.define("fleet-orders", FleetOrders);
export { FleetOrders };
