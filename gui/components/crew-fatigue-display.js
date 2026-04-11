/**
 * Crew Fatigue Display Component
 * Shows crew fatigue level, g-load status, performance metrics,
 * and per-station performance breakdown. Provides rest order controls.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class CrewFatigueDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
  }

  connectedCallback() {
    this._render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._update();
    });
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
          padding: 12px;
        }

        .section-title {
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 1px;
          margin-bottom: 8px;
          font-weight: 600;
        }

        .crew-panel {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .status-card {
          background: var(--bg-input, #1a1a2e);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          padding: 10px 12px;
        }

        .status-card.alert-blackout {
          border-color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.08);
        }

        .status-card.alert-exhausted {
          border-color: var(--status-critical, #ff4444);
        }

        .status-card.alert-heavy {
          border-color: var(--status-warning, #ffaa00);
        }

        .metric-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }

        .metric-label {
          width: 80px;
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .metric-bar {
          flex: 1;
          height: 12px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 3px;
          overflow: hidden;
          position: relative;
        }

        .metric-fill {
          height: 100%;
          transition: width 0.5s ease;
          border-radius: 3px;
        }

        .metric-fill.nominal { background: var(--status-nominal, #00ff88); }
        .metric-fill.warning { background: var(--status-warning, #ffaa00); }
        .metric-fill.critical { background: var(--status-critical, #ff4444); }
        .metric-fill.info { background: var(--status-info, #00aaff); }

        .metric-value {
          width: 48px;
          text-align: right;
          font-size: 0.75rem;
          font-weight: 600;
        }

        .metric-value.nominal { color: var(--status-nominal, #00ff88); }
        .metric-value.warning { color: var(--status-warning, #ffaa00); }
        .metric-value.critical { color: var(--status-critical, #ff4444); }
        .metric-value.info { color: var(--status-info, #00aaff); }

        .g-display {
          display: flex;
          align-items: baseline;
          gap: 6px;
          margin-bottom: 8px;
        }

        .g-value {
          font-size: 1.6rem;
          font-weight: 700;
          line-height: 1;
        }

        .g-unit {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
        }

        .perf-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .perf-value {
          font-size: 1.2rem;
          font-weight: 700;
        }

        .station-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 6px;
        }

        .station-item {
          text-align: center;
          padding: 6px 4px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          border: 1px solid transparent;
        }

        .station-item.degraded {
          border-color: var(--status-warning, #ffaa00);
        }

        .station-item.impaired {
          border-color: var(--status-critical, #ff4444);
        }

        .station-name {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .station-perf {
          font-size: 0.85rem;
          font-weight: 600;
          margin-top: 2px;
        }

        .controls {
          display: flex;
          gap: 8px;
          margin-top: 8px;
        }

        button {
          font-family: inherit;
          font-size: 0.7rem;
          padding: 6px 12px;
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          background: var(--bg-panel, #12121a);
          color: var(--text-primary, #e0e0e0);
          cursor: pointer;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        button:hover {
          border-color: var(--status-info, #00aaff);
        }

        button.active {
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        button.warning {
          border-color: var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .status-badge {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 3px;
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .status-badge.nominal { background: rgba(0, 255, 136, 0.15); color: var(--status-nominal, #00ff88); }
        .status-badge.warning { background: rgba(255, 170, 0, 0.15); color: var(--status-warning, #ffaa00); }
        .status-badge.critical { background: rgba(255, 68, 68, 0.15); color: var(--status-critical, #ff4444); }
        .status-badge.info { background: rgba(0, 170, 255, 0.15); color: var(--status-info, #00aaff); }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }

        .blackout-overlay {
          text-align: center;
          padding: 16px;
          font-size: 1.1rem;
          font-weight: 700;
          color: var(--status-critical, #ff4444);
          text-transform: uppercase;
          letter-spacing: 2px;
          animation: pulse 1s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      </style>

      <div class="crew-panel" id="content">
        <div class="empty-state">Awaiting crew fatigue data...</div>
      </div>
    `;
  }

  _update() {
    if (!this.offsetParent) return;
    const ship = stateManager.getShipState();
    const el = this.shadowRoot.getElementById("content");
    if (!ship) return;

    const cf = ship.crew_fatigue || ship.systems?.crew_fatigue;
    if (!cf || !cf.enabled) {
      el.innerHTML = '<div class="empty-state">Crew fatigue system offline</div>';
      return;
    }

    const fatigue = cf.fatigue ?? 0;
    const gLoad = cf.g_load ?? 0;
    const perf = cf.performance ?? 1;
    const isBlackedOut = cf.is_blacked_out ?? false;
    const restOrdered = cf.rest_ordered ?? false;
    const status = cf.status ?? "nominal";

    const alertClass = isBlackedOut ? "alert-blackout"
      : status === "exhausted" ? "alert-exhausted"
      : status === "heavy_fatigue" ? "alert-heavy"
      : "";

    const fatigueClass = fatigue > 0.7 ? "critical" : fatigue > 0.4 ? "warning" : "nominal";
    const gClass = gLoad > 7 ? "critical" : gLoad > 5 ? "warning" : gLoad > 3 ? "info" : "nominal";
    const perfClass = perf < 0.5 ? "critical" : perf < 0.75 ? "warning" : "nominal";
    const statusBadgeClass = isBlackedOut ? "critical"
      : status === "exhausted" || status === "heavy_fatigue" ? "warning"
      : status === "g_impaired" ? "info"
      : "nominal";

    el.innerHTML = `
      ${isBlackedOut ? '<div class="blackout-overlay">CREW BLACKOUT - ALL MANUAL OPS SUSPENDED</div>' : ''}

      <div class="status-card ${alertClass}">
        <div class="perf-header">
          <div>
            <span class="section-title">G-LOAD</span>
            <div class="g-display">
              <span class="g-value ${gClass}">${gLoad.toFixed(1)}</span>
              <span class="g-unit">g</span>
            </div>
          </div>
          <div style="text-align: right;">
            <span class="section-title">CREW STATUS</span>
            <div><span class="status-badge ${statusBadgeClass}">${status.replace("_", " ")}</span></div>
          </div>
        </div>

        ${this._renderMetric("FATIGUE", fatigue, fatigueClass, `${(fatigue * 100).toFixed(0)}%`, true)}
        ${this._renderMetric("PERF", perf, perfClass, `${(perf * 100).toFixed(0)}%`, false)}
        ${cf.g_dose !== undefined ? this._renderMetric("G-DOSE", cf.g_dose, cf.g_dose > 0.5 ? "warning" : "nominal", `${(cf.g_dose * 100).toFixed(0)}%`, true) : ''}

        ${isBlackedOut && cf.blackout_timer ? `
          <div class="metric-row" style="margin-top: 4px;">
            <span class="metric-label" style="color: var(--status-critical);">RECOVERY</span>
            <span class="metric-value critical">${(cf.blackout_recovery ?? 0).toFixed(0)}s</span>
          </div>
        ` : ''}
      </div>

      <div class="status-card">
        <div class="perf-header">
          <span class="section-title">STATION PERFORMANCE</span>
          <span class="perf-value ${perfClass}">${(perf * 100).toFixed(0)}%</span>
        </div>
        <div class="station-grid">
          ${this._renderStations(cf, perf)}
        </div>
      </div>

      <div class="controls">
        <button class="${restOrdered ? 'active' : 'warning'}" id="btn-rest">
          ${restOrdered ? 'RESTING' : 'ORDER REST'}
        </button>
        ${restOrdered ? '<button id="btn-cancel-rest">CANCEL REST</button>' : ''}
      </div>
    `;

    this._bindControls();
  }

  _renderMetric(label, value, cls, text, invert) {
    const pct = Math.max(0, Math.min(100, (value ?? 0) * 100));
    return `
      <div class="metric-row">
        <span class="metric-label">${label}</span>
        <div class="metric-bar">
          <div class="metric-fill ${cls}" style="width: ${pct}%"></div>
        </div>
        <span class="metric-value ${cls}">${text}</span>
      </div>
    `;
  }

  _renderStations(cf, overallPerf) {
    const stations = [
      { key: "helm", label: "HELM" },
      { key: "tactical", label: "TAC" },
      { key: "ops", label: "OPS" },
      { key: "engineering", label: "ENG" },
      { key: "comms", label: "COM" },
      { key: "science", label: "SCI" },
    ];

    return stations.map(s => {
      const val = overallPerf;
      const cls = val < 0.5 ? "impaired" : val < 0.75 ? "degraded" : "";
      const perfCls = val < 0.5 ? "critical" : val < 0.75 ? "warning" : "nominal";
      return `
        <div class="station-item ${cls}">
          <div class="station-name">${s.label}</div>
          <div class="station-perf ${perfCls}">${(val * 100).toFixed(0)}%</div>
        </div>
      `;
    }).join("");
  }

  _bindControls() {
    const restBtn = this.shadowRoot.getElementById("btn-rest");
    const cancelBtn = this.shadowRoot.getElementById("btn-cancel-rest");

    if (restBtn) {
      restBtn.addEventListener("click", async () => {
        try {
          await wsClient.sendShipCommand("crew_rest");
        } catch (e) {
          console.error("crew_rest failed:", e);
        }
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener("click", async () => {
        try {
          await wsClient.sendShipCommand("cancel_rest");
        } catch (e) {
          console.error("cancel_rest failed:", e);
        }
      });
    }
  }
}

customElements.define("crew-fatigue-display", CrewFatigueDisplay);
export { CrewFatigueDisplay };
