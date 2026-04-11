/**
 * Drone Control Panel
 * OPS station panel for managing the drone bay:
 * - Bay capacity and stored drone inventory
 * - Launch buttons per drone type
 * - Active drone status (fuel, distance, hull, AI role)
 * - Recall buttons for deployed drones
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const DRONE_TYPE_LABELS = {
  drone_sensor: "Sensor",
  drone_combat: "Combat",
  drone_decoy: "Decoy",
};

const DRONE_TYPE_ICONS = {
  drone_sensor: "S",
  drone_combat: "C",
  drone_decoy: "D",
};

class DroneControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._pollInterval = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    // Poll drone status every 2s since it is not in standard telemetry
    this._pollInterval = setInterval(() => this._pollStatus(), 2000);
    this._pollStatus();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
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

  async _pollStatus() {
    try {
      const resp = await this._sendCommand("drone_status");
      if (resp && resp.ok !== false) {
        this._lastStatus = resp;
        this._updateDisplay();
      }
    } catch (e) {
      // Silently ignore — ship may not have a drone bay
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          color: var(--text, #e0e0e0);
        }
        .section-label {
          font-size: 0.65rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-dim, #888);
          margin: 0.6rem 0 0.3rem;
        }
        .bay-summary {
          display: flex;
          gap: 1rem;
          align-items: center;
          padding: 0.4rem 0;
          border-bottom: 1px solid var(--border, #333);
          margin-bottom: 0.5rem;
        }
        .bay-summary .stat {
          font-size: 0.75rem;
        }
        .bay-summary .stat .val {
          font-weight: 600;
          color: var(--accent, #4fc3f7);
        }
        .stored-row {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.25rem 0;
        }
        .stored-row .type-badge {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 1.4rem;
          height: 1.4rem;
          border-radius: 3px;
          font-size: 0.7rem;
          font-weight: 700;
          color: #fff;
        }
        .type-badge.drone_sensor  { background: #2e7d32; }
        .type-badge.drone_combat  { background: #c62828; }
        .type-badge.drone_decoy   { background: #f57f17; }
        .launch-btn {
          margin-left: auto;
          padding: 0.2rem 0.6rem;
          border: 1px solid var(--accent, #4fc3f7);
          background: transparent;
          color: var(--accent, #4fc3f7);
          font-size: 0.7rem;
          cursor: pointer;
          border-radius: 3px;
          text-transform: uppercase;
        }
        .launch-btn:hover {
          background: var(--accent, #4fc3f7);
          color: #000;
        }
        .launch-btn:disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }
        .active-drone {
          display: grid;
          grid-template-columns: 1.4rem 1fr auto;
          gap: 0.4rem;
          align-items: center;
          padding: 0.35rem 0;
          border-bottom: 1px solid var(--border-faint, #222);
        }
        .drone-info {
          display: flex;
          flex-direction: column;
          gap: 0.1rem;
        }
        .drone-info .drone-id {
          font-size: 0.7rem;
          color: var(--text-dim, #888);
          font-family: monospace;
        }
        .drone-info .drone-stats {
          display: flex;
          gap: 0.6rem;
          font-size: 0.7rem;
        }
        .drone-stats .fuel { color: #4caf50; }
        .drone-stats .hull { color: #ff9800; }
        .drone-stats .dist { color: #90caf9; }
        .recall-btn {
          padding: 0.15rem 0.5rem;
          border: 1px solid #ef5350;
          background: transparent;
          color: #ef5350;
          font-size: 0.65rem;
          cursor: pointer;
          border-radius: 3px;
          text-transform: uppercase;
        }
        .recall-btn:hover {
          background: #ef5350;
          color: #000;
        }
        .empty-state {
          font-size: 0.75rem;
          color: var(--text-dim, #666);
          font-style: italic;
          padding: 0.5rem 0;
        }
      </style>
      <div class="bay-summary" id="bay-summary">
        <span class="stat">Capacity: <span class="val" id="capacity">--</span></span>
        <span class="stat">Stored: <span class="val" id="stored-count">--</span></span>
        <span class="stat">Active: <span class="val" id="active-count">--</span></span>
      </div>

      <div class="section-label">Stored Drones</div>
      <div id="stored-list"><span class="empty-state">No drones in bay</span></div>

      <div class="section-label">Active Drones</div>
      <div id="active-list"><span class="empty-state">No drones deployed</span></div>
    `;
  }

  _updateDisplay() {
    if (!this.offsetParent) return;
    const status = this._lastStatus;
    if (!status) return;

    // Bay summary
    const capacityEl = this.shadowRoot.getElementById("capacity");
    const storedEl = this.shadowRoot.getElementById("stored-count");
    const activeEl = this.shadowRoot.getElementById("active-count");
    if (capacityEl) capacityEl.textContent = status.capacity ?? "--";
    if (storedEl) storedEl.textContent = status.stored_count ?? "--";
    if (activeEl) activeEl.textContent = status.active_count ?? "--";

    // Stored drones
    const storedList = this.shadowRoot.getElementById("stored-list");
    if (storedList) {
      const stored = status.stored_drones || [];
      if (stored.length === 0) {
        storedList.innerHTML = '<span class="empty-state">No drones in bay</span>';
      } else {
        // Group by type for compact display
        const grouped = {};
        for (const s of stored) {
          const t = s.drone_type;
          grouped[t] = (grouped[t] || 0) + 1;
        }
        storedList.innerHTML = Object.entries(grouped).map(([type, count]) => `
          <div class="stored-row">
            <span class="type-badge ${type}">${DRONE_TYPE_ICONS[type] || "?"}</span>
            <span>${DRONE_TYPE_LABELS[type] || type} x${count}</span>
            <button class="launch-btn" data-type="${type}">Launch</button>
          </div>
        `).join("");

        storedList.querySelectorAll(".launch-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            this._sendCommand("launch_drone", { drone_type: btn.dataset.type });
            // Re-poll immediately after launch
            setTimeout(() => this._pollStatus(), 500);
          });
        });
      }
    }

    // Active drones
    const activeList = this.shadowRoot.getElementById("active-list");
    if (activeList) {
      const active = status.active_drones || [];
      if (active.length === 0) {
        activeList.innerHTML = '<span class="empty-state">No drones deployed</span>';
      } else {
        activeList.innerHTML = active.map(d => {
          const type = d.drone_type || "unknown";
          const fuelStr = d.fuel_pct != null ? `${d.fuel_pct.toFixed(0)}%` : "--";
          const hullStr = d.hull_pct != null ? `${d.hull_pct.toFixed(0)}%` : "--";
          const distStr = d.distance_m != null ? this._formatDist(d.distance_m) : "--";
          const roleStr = d.ai_role || "?";
          const lost = d.status === "lost";

          return `
            <div class="active-drone">
              <span class="type-badge ${type}">${DRONE_TYPE_ICONS[type] || "?"}</span>
              <div class="drone-info">
                <span class="drone-id">${d.drone_id}${lost ? " [LOST]" : ""} (${roleStr})</span>
                <span class="drone-stats">
                  <span class="fuel">F: ${fuelStr}</span>
                  <span class="hull">H: ${hullStr}</span>
                  <span class="dist">D: ${distStr}</span>
                </span>
              </div>
              ${lost ? "" : `<button class="recall-btn" data-id="${d.drone_id}">Recall</button>`}
            </div>
          `;
        }).join("");

        activeList.querySelectorAll(".recall-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            this._sendCommand("recall_drone", { drone_id: btn.dataset.id });
            setTimeout(() => this._pollStatus(), 500);
          });
        });
      }
    }
  }

  _formatDist(m) {
    if (m >= 1000) return `${(m / 1000).toFixed(1)}km`;
    return `${m.toFixed(0)}m`;
  }
}

customElements.define("drone-control-panel", DroneControlPanel);
export default DroneControlPanel;
