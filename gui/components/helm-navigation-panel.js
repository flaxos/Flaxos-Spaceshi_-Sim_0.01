/**
 * Helm Navigation Panel
 * Shows trajectory projections, fuel/delta-v budget, velocity vector,
 * and provides quick-action buttons for helm navigation commands:
 * execute-burn, plot-intercept, flip-and-burn, emergency-burn.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class HelmNavigationPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();
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

  _setupInteraction() {
    const root = this.shadowRoot;

    root.getElementById("btn-flip-burn")?.addEventListener("click", () => {
      this._executeFlipAndBurn();
    });

    root.getElementById("btn-emergency")?.addEventListener("click", () => {
      this._executeEmergencyBurn();
    });

    root.getElementById("btn-execute-burn")?.addEventListener("click", () => {
      this._showBurnDialog();
    });

    root.getElementById("btn-plot")?.addEventListener("click", () => {
      this._plotIntercept();
    });

    // Burn dialog submit
    root.getElementById("burn-submit")?.addEventListener("click", () => {
      this._submitBurn();
    });

    root.getElementById("burn-cancel")?.addEventListener("click", () => {
      this._hideBurnDialog();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 12px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.78rem;
        }

        .section {
          margin-bottom: 12px;
        }

        .section-title {
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 6px;
        }

        .data-grid {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 3px 12px;
        }

        .data-label {
          color: var(--text-dim, #555566);
          font-size: 0.72rem;
        }

        .data-value {
          color: var(--text-primary, #e0e0e0);
          text-align: right;
          font-size: 0.72rem;
        }

        .data-value.info { color: var(--status-info, #00aaff); }
        .data-value.nominal { color: var(--status-nominal, #00ff88); }
        .data-value.warning { color: var(--status-warning, #ffaa00); }
        .data-value.critical { color: var(--status-critical, #ff4444); }

        .velocity-primary {
          font-size: 1.4rem;
          font-weight: 700;
          color: var(--status-info, #00aaff);
          text-align: center;
          padding: 6px 0;
        }

        .heading-row {
          display: flex;
          justify-content: center;
          gap: 16px;
          padding: 4px 0;
          color: var(--text-secondary, #888899);
        }

        .heading-row span { font-size: 0.8rem; }

        .action-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
        }

        .action-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 10px 6px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          cursor: pointer;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.7rem;
          font-weight: 500;
          transition: all 0.15s ease;
          min-height: 48px;
        }

        .action-btn:hover {
          background: rgba(0, 170, 255, 0.1);
          border-color: var(--status-info, #00aaff);
        }

        .action-btn:active {
          transform: scale(0.97);
        }

        .action-btn.emergency {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .action-btn.emergency:hover {
          background: rgba(255, 68, 68, 0.15);
          border-color: var(--status-critical, #ff4444);
        }

        .action-btn .icon {
          font-size: 1.1rem;
          margin-bottom: 2px;
        }

        .burn-dialog {
          display: none;
          padding: 10px;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 6px;
          margin-top: 8px;
        }

        .burn-dialog.visible {
          display: block;
        }

        .burn-dialog label {
          display: block;
          font-size: 0.65rem;
          color: var(--text-secondary, #888899);
          margin: 6px 0 2px;
        }

        .burn-dialog input {
          width: 100%;
          padding: 6px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, monospace);
          font-size: 0.75rem;
          box-sizing: border-box;
        }

        .burn-dialog .btn-row {
          display: flex;
          gap: 6px;
          margin-top: 8px;
        }

        .burn-dialog button {
          flex: 1;
          padding: 6px;
          background: rgba(0, 170, 255, 0.2);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 4px;
          color: var(--status-info, #00aaff);
          cursor: pointer;
          font-size: 0.7rem;
          font-weight: 600;
        }

        .burn-dialog button.cancel {
          background: rgba(0, 0, 0, 0.3);
          border-color: var(--border-default, #2a2a3a);
          color: var(--text-secondary, #888899);
        }

        .projection-list {
          font-size: 0.68rem;
          color: var(--text-dim, #555566);
        }

        .projection-item {
          display: flex;
          justify-content: space-between;
          padding: 2px 0;
        }

        .projection-time {
          color: var(--text-secondary, #888899);
        }

        .ponr-bar {
          height: 4px;
          background: var(--bg-input, #1a1a24);
          border-radius: 2px;
          overflow: hidden;
          margin-top: 4px;
        }

        .ponr-fill {
          height: 100%;
          transition: width 0.3s ease;
        }

        .ponr-fill.safe { background: var(--status-nominal, #00ff88); }
        .ponr-fill.warn { background: var(--status-warning, #ffaa00); }
        .ponr-fill.crit { background: var(--status-critical, #ff4444); }

        .response-area {
          margin-top: 8px;
          padding: 8px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 4px;
          font-size: 0.68rem;
          color: var(--text-secondary, #888899);
          display: none;
        }

        .response-area.visible {
          display: block;
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 16px;
          font-style: italic;
          font-size: 0.75rem;
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for navigation data...</div>
      </div>

      <div class="burn-dialog" id="burn-dialog">
        <div class="section-title">Execute Burn</div>
        <label>Duration (s)</label>
        <input type="number" id="burn-duration" value="10" min="0.1" max="3600" step="1">
        <label>Throttle (0-1)</label>
        <input type="number" id="burn-throttle" value="1.0" min="0" max="1" step="0.1">
        <div class="btn-row">
          <button id="burn-submit">BURN</button>
          <button id="burn-cancel" class="cancel">Cancel</button>
        </div>
      </div>

      <div class="response-area" id="response-area"></div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for navigation data...</div>';
      return;
    }

    const vel = ship.velocity_magnitude || 0;
    const accel = ship.acceleration_magnitude || 0;
    const orientation = ship.orientation || { pitch: 0, yaw: 0, roll: 0 };
    const fuel = ship.fuel || { level: 0, max: 1, percent: 0 };
    const dv = ship.delta_v_remaining || 0;
    const ponr = ship.ponr || {};
    const trajectory = ship.trajectory || {};
    const velHeading = trajectory.velocity_heading || { pitch: 0, yaw: 0 };
    const drift = trajectory.drift_angle || 0;
    const projections = trajectory.projected_positions || [];
    const maxAccelG = trajectory.max_accel_g || 0;
    const timeToZero = trajectory.time_to_zero;

    // PONR status
    const ponrPast = ponr.past_ponr || false;
    const marginPct = ponr.margin_percent || 100;
    const ponrClass = ponrPast ? "crit" : (marginPct < 25 ? "warn" : "safe");
    const ponrLabel = ponrPast ? "PAST PONR" : `${marginPct.toFixed(0)}% margin`;

    // Drift class
    const driftClass = drift < 5 ? "nominal" : drift < 30 ? "warning" : "critical";

    content.innerHTML = `
      <div class="velocity-primary">${this._fmtVel(vel)}</div>
      <div class="heading-row">
        <span>P ${this._fmtAngle(orientation.pitch)}</span>
        <span>Y ${this._fmtAngle(orientation.yaw)}</span>
        <span>R ${this._fmtAngle(orientation.roll)}</span>
      </div>

      <div class="section">
        <div class="section-title">Navigation</div>
        <div class="data-grid">
          <span class="data-label">Vel Heading:</span>
          <span class="data-value">${this._fmtAngle(velHeading.pitch)} / ${this._fmtAngle(velHeading.yaw)}</span>
          <span class="data-label">Drift Angle:</span>
          <span class="data-value ${driftClass}">${drift < 1 ? 'ON-AXIS' : drift.toFixed(1) + '\u00B0'}</span>
          <span class="data-label">Accel:</span>
          <span class="data-value info">${accel.toFixed(2)} m/s\u00B2 (${(accel / 9.81).toFixed(2)}G)</span>
          <span class="data-label">Max Accel:</span>
          <span class="data-value">${maxAccelG.toFixed(2)}G</span>
          ${timeToZero !== null && timeToZero !== undefined ? `
            <span class="data-label">Time to Zero:</span>
            <span class="data-value ${ponrPast ? 'critical' : 'info'}">${this._fmtDuration(timeToZero)}</span>
          ` : ''}
        </div>
      </div>

      <div class="section">
        <div class="section-title">Fuel & Delta-V</div>
        <div class="data-grid">
          <span class="data-label">Fuel:</span>
          <span class="data-value ${fuel.percent < 20 ? 'warning' : 'nominal'}">${fuel.percent?.toFixed(1) || 0}% (${fuel.level?.toFixed(0) || 0}kg)</span>
          <span class="data-label">\u0394v Remaining:</span>
          <span class="data-value info">${this._fmtVel(dv)}</span>
          <span class="data-label">PONR:</span>
          <span class="data-value ${ponrPast ? 'critical' : marginPct < 25 ? 'warning' : 'nominal'}">${ponrLabel}</span>
        </div>
        <div class="ponr-bar">
          <div class="ponr-fill ${ponrClass}" style="width: ${Math.min(100, Math.max(0, marginPct))}%"></div>
        </div>
      </div>

      ${projections.length > 0 ? `
        <div class="section">
          <div class="section-title">Trajectory Projection</div>
          <div class="projection-list">
            ${projections.map(p => `
              <div class="projection-item">
                <span class="projection-time">T+${p.t}s</span>
                <span>${this._fmtPos(p.position)}</span>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      <div class="section">
        <div class="section-title">Helm Commands</div>
        <div class="action-grid">
          <button class="action-btn" id="btn-execute-burn">
            <span class="icon">\u{1F525}</span>
            Execute Burn
          </button>
          <button class="action-btn" id="btn-plot">
            <span class="icon">\u{1F4CD}</span>
            Plot Intercept
          </button>
          <button class="action-btn" id="btn-flip-burn">
            <span class="icon">\u21C5</span>
            Flip & Burn
          </button>
          <button class="action-btn emergency" id="btn-emergency">
            <span class="icon">\u26A0</span>
            Emergency Burn
          </button>
        </div>
      </div>
    `;

    // Re-attach event listeners after render
    this._setupInteraction();
  }

  async _executeFlipAndBurn() {
    try {
      const resp = await wsClient.sendShipCommandAsync("flip_and_burn", {
        auto_burn: false,
      });
      this._showResponse(resp);
    } catch (e) {
      this._showResponse({ error: e.message });
    }
  }

  async _executeEmergencyBurn() {
    try {
      const resp = await wsClient.sendShipCommandAsync("emergency_burn", {});
      this._showResponse(resp);
    } catch (e) {
      this._showResponse({ error: e.message });
    }
  }

  async _plotIntercept() {
    const ship = stateManager.getShipState();
    const targetId = ship?.target_id;
    const params = {};

    if (targetId) {
      params.target = targetId;
    } else {
      // No target locked - try first sensor contact
      const contacts = ship?.sensors?.contacts || [];
      if (contacts.length > 0) {
        params.target = contacts[0].id;
      } else {
        this._showResponse({ error: "No target available for intercept plot" });
        return;
      }
    }

    try {
      const resp = await wsClient.sendShipCommandAsync("plot_intercept", params);
      this._showResponse(resp);
    } catch (e) {
      this._showResponse({ error: e.message });
    }
  }

  _showBurnDialog() {
    const dialog = this.shadowRoot.getElementById("burn-dialog");
    if (dialog) dialog.classList.add("visible");
  }

  _hideBurnDialog() {
    const dialog = this.shadowRoot.getElementById("burn-dialog");
    if (dialog) dialog.classList.remove("visible");
  }

  async _submitBurn() {
    const duration = parseFloat(this.shadowRoot.getElementById("burn-duration")?.value || "10");
    const throttle = parseFloat(this.shadowRoot.getElementById("burn-throttle")?.value || "1.0");

    this._hideBurnDialog();

    try {
      const resp = await wsClient.sendShipCommandAsync("execute_burn", {
        duration,
        throttle,
      });
      this._showResponse(resp);
    } catch (e) {
      this._showResponse({ error: e.message });
    }
  }

  _showResponse(resp) {
    const area = this.shadowRoot.getElementById("response-area");
    if (!area) return;

    if (resp?.error) {
      area.textContent = `Error: ${resp.error}`;
      area.style.color = "var(--status-critical, #ff4444)";
    } else {
      const status = resp?.status || "OK";
      const plan = resp?.plan || resp?.burn_estimate || resp?.burn;
      let text = status;
      if (plan) {
        if (plan.delta_v) text += ` | \u0394v: ${plan.delta_v?.toFixed?.(0) || plan.delta_v}m/s`;
        if (plan.fuel_cost) text += ` | Fuel: ${plan.fuel_cost?.toFixed?.(0) || plan.fuel_cost}kg`;
        if (plan.estimated_time) text += ` | ETA: ${this._fmtDuration(plan.estimated_time)}`;
        if (plan.estimated_delta_v) text += ` | \u0394v: ${plan.estimated_delta_v}m/s`;
        if (plan.estimated_fuel) text += ` | Fuel: ${plan.estimated_fuel}kg`;
      }
      area.textContent = text;
      area.style.color = "var(--status-nominal, #00ff88)";
    }

    area.classList.add("visible");
    clearTimeout(this._responseTimeout);
    this._responseTimeout = setTimeout(() => {
      area.classList.remove("visible");
    }, 8000);
  }

  // --- Formatters ---

  _fmtVel(mps) {
    const abs = Math.abs(mps);
    if (abs >= 1000) return `${(abs / 1000).toFixed(2)} km/s`;
    return `${abs.toFixed(1)} m/s`;
  }

  _fmtAngle(deg) {
    const d = deg || 0;
    return `${d >= 0 ? '+' : ''}${d.toFixed(1)}\u00B0`;
  }

  _fmtPos(pos) {
    if (!pos) return "---";
    const x = (pos.x / 1000).toFixed(1);
    const y = (pos.y / 1000).toFixed(1);
    const z = (pos.z / 1000).toFixed(1);
    return `${x}, ${y}, ${z} km`;
  }

  _fmtDuration(seconds) {
    if (seconds == null || !Number.isFinite(seconds)) return "---";
    const s = Math.max(0, Math.floor(seconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
    if (m > 0) return `${m}m ${String(sec).padStart(2, '0')}s`;
    return `${sec}s`;
  }
}

customElements.define("helm-navigation-panel", HelmNavigationPanel);
export { HelmNavigationPanel };
