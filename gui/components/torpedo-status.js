/**
 * Torpedo Status Panel
 * Displays torpedo magazine state, active (outbound) torpedoes, and
 * incoming torpedo threats targeting this ship.
 */

import { stateManager } from "../js/state-manager.js";

const TORPEDO_MASS_KG = 250;

class TorpedoStatus extends HTMLElement {
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

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 16px;
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

        .detail-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 2px 0;
          font-size: 0.75rem;
        }

        .detail-label {
          color: var(--text-secondary, #888899);
        }

        .detail-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
        }

        .bar {
          height: 10px;
          background: var(--bg-input, #1a1a24);
          border-radius: 5px;
          overflow: hidden;
          margin-top: 4px;
        }

        .bar-fill {
          height: 100%;
          border-radius: 5px;
          transition: width 0.3s ease;
        }

        .bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .bar-fill.critical { background: var(--status-critical, #ff4444); }

        /* Torpedo list items */
        .torp-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 8px;
          margin-bottom: 4px;
          border-radius: 4px;
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid var(--border-default, #2a2a3a);
          font-size: 0.7rem;
        }

        .torp-id {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
          min-width: 60px;
        }

        .torp-state {
          padding: 1px 6px;
          border-radius: 3px;
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
        }

        .torp-state.boost {
          background: rgba(0, 255, 136, 0.2);
          color: var(--status-nominal, #00ff88);
        }

        .torp-state.midcourse {
          background: rgba(0, 170, 255, 0.2);
          color: var(--status-info, #00aaff);
        }

        .torp-state.terminal {
          background: rgba(255, 68, 68, 0.2);
          color: var(--status-critical, #ff4444);
          animation: pulse 0.6s ease-in-out infinite;
        }

        .torp-stats {
          display: flex;
          gap: 8px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-secondary, #888899);
          font-size: 0.65rem;
        }

        /* Incoming threat styling */
        .torp-item.incoming {
          border-color: rgba(255, 68, 68, 0.4);
          background: rgba(255, 68, 68, 0.08);
        }

        .threat-label {
          color: var(--status-critical, #ff4444);
          font-weight: 700;
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .no-threats {
          text-align: center;
          color: var(--status-nominal, #00ff88);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 600;
          padding: 8px;
          opacity: 0.7;
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }

        .cooldown-text {
          color: var(--status-warning, #ffaa00);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for torpedo data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const state = stateManager.getState();
    const ship = stateManager.getShipState();
    const weapons = stateManager.getWeapons();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for torpedo data...</div>';
      return;
    }

    // Magazine data from weapons telemetry
    const torpData = weapons?.torpedoes || weapons?.torpedo || ship?.torpedoes || {};
    const loaded = torpData.loaded ?? torpData.count ?? torpData.ammo ?? 0;
    const capacity = torpData.max ?? torpData.capacity ?? torpData.ammo_capacity ?? 0;
    const cooldown = torpData.cooldown ?? torpData.reload_time ?? null;
    const launched = torpData.launched ?? torpData.in_flight ?? 0;

    // All in-flight torpedoes from top-level state
    const allTorpedoes = state?.torpedoes || [];

    // Determine our ship ID
    const shipId = ship?.id || stateManager.getPlayerShipId() || state?.ship || "";

    // Split into outbound (ours) and incoming (targeting us)
    const outbound = allTorpedoes.filter(t => t.shooter === shipId && t.alive !== false);
    const incoming = allTorpedoes.filter(t => t.target === shipId && t.alive !== false);

    const pct = capacity > 0 ? (loaded / capacity) * 100 : 0;
    const barClass = pct > 50 ? "nominal" : pct > 20 ? "warning" : "critical";
    const totalMass = loaded * TORPEDO_MASS_KG;

    content.innerHTML = `
      <!-- Magazine -->
      <div class="section">
        <div class="section-title">Torpedo Magazine</div>
        <div class="detail-row">
          <span class="detail-label">Loaded</span>
          <span class="detail-value">${loaded}/${capacity}</span>
        </div>
        <div class="bar">
          <div class="bar-fill ${barClass}" style="width: ${pct}%"></div>
        </div>
        <div class="detail-row" style="margin-top: 6px">
          <span class="detail-label">Magazine Mass</span>
          <span class="detail-value">${totalMass.toFixed(0)} kg</span>
        </div>
        ${cooldown ? `
        <div class="detail-row">
          <span class="detail-label">Tube Cooldown</span>
          <span class="cooldown-text">${typeof cooldown === "number" ? cooldown.toFixed(1) + "s" : cooldown}</span>
        </div>` : ""}
        ${launched > 0 ? `
        <div class="detail-row">
          <span class="detail-label">Launched</span>
          <span class="detail-value">${launched}</span>
        </div>` : ""}
      </div>

      <!-- Active (outbound) torpedoes -->
      <div class="section">
        <div class="section-title">Active Torpedoes (${outbound.length})</div>
        ${outbound.length > 0 ? outbound.map(t => this._renderTorpedo(t, false)).join("") : '<div class="empty-state" style="padding:8px">None in flight</div>'}
      </div>

      <!-- Incoming threats -->
      <div class="section">
        <div class="section-title threat-label">Incoming Threats (${incoming.length})</div>
        ${incoming.length > 0 ? incoming.map(t => this._renderTorpedo(t, true)).join("") : '<div class="no-threats">NO THREATS</div>'}
      </div>
    `;
  }

  _renderTorpedo(t, isIncoming) {
    const stateVal = (t.state || "unknown").toLowerCase();
    const stateClass = stateVal === "boost" ? "boost" : stateVal === "terminal" ? "terminal" : "midcourse";
    const fuelPct = (t.fuel_percent ?? 0).toFixed(0);
    const hull = (t.hull_health ?? 100).toFixed(0);

    return `
      <div class="torp-item ${isIncoming ? "incoming" : ""}">
        <span class="torp-id">${t.id}</span>
        <span class="torp-state ${stateClass}">${stateVal}</span>
        <span class="torp-stats">
          <span title="Fuel">F:${fuelPct}%</span>
          <span title="Hull">H:${hull}</span>
          <span title="Target">T:${isIncoming ? (t.shooter || "?") : (t.target || "?")}</span>
        </span>
      </div>
    `;
  }
}

customElements.define("torpedo-status", TorpedoStatus);
export { TorpedoStatus };
