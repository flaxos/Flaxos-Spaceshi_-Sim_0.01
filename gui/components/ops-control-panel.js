/**
 * Ops Control Panel
 * Provides interactive controls for OPS station commands:
 * - Power allocation sliders per subsystem
 * - Repair team dispatch buttons
 * - System priority controls
 * - Emergency shutdown/restart
 * - Full status readout
 */

import { stateManager } from "../js/state-manager.js";

const SUBSYSTEM_LABELS = {
  reactor: "Reactor",
  propulsion: "Propulsion",
  rcs: "RCS",
  sensors: "Sensors",
  targeting: "Targeting",
  weapons: "Weapons",
  life_support: "Life Support",
  radiators: "Radiators",
};

class OpsControlPanel extends HTMLElement {
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

        /* Repair teams section */
        .repair-team {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 8px;
          margin-bottom: 6px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          border-left: 3px solid var(--text-dim, #555566);
        }

        .repair-team.idle {
          border-left-color: var(--status-nominal, #00ff88);
        }

        .repair-team.en_route {
          border-left-color: var(--status-info, #00aaff);
        }

        .repair-team.repairing {
          border-left-color: var(--status-warning, #ffaa00);
        }

        .team-id {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-weight: 600;
          font-size: 0.75rem;
          color: var(--text-primary, #e0e0e0);
          min-width: 36px;
        }

        .team-status {
          font-size: 0.7rem;
          padding: 2px 6px;
          border-radius: 3px;
          text-transform: uppercase;
          font-weight: 600;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .team-status.idle {
          background: rgba(0, 255, 136, 0.15);
          color: var(--status-nominal, #00ff88);
        }

        .team-status.en_route {
          background: rgba(0, 170, 255, 0.15);
          color: var(--status-info, #00aaff);
        }

        .team-status.repairing {
          background: rgba(255, 170, 0, 0.15);
          color: var(--status-warning, #ffaa00);
        }

        .team-target {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
          flex: 1;
        }

        .team-eta {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
        }

        /* Dispatch buttons */
        .dispatch-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 4px;
          margin-top: 8px;
        }

        .dispatch-btn {
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid rgba(0, 170, 255, 0.3);
          border-radius: 4px;
          color: var(--status-info, #00aaff);
          padding: 4px 6px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          cursor: pointer;
          text-transform: uppercase;
          min-height: 28px;
          transition: all 0.15s ease;
        }

        .dispatch-btn:hover {
          background: rgba(0, 170, 255, 0.2);
          border-color: var(--status-info, #00aaff);
        }

        .dispatch-btn.damaged {
          border-color: rgba(255, 170, 0, 0.5);
          color: var(--status-warning, #ffaa00);
          background: rgba(255, 170, 0, 0.1);
        }

        .dispatch-btn.offline {
          border-color: rgba(255, 68, 68, 0.5);
          color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.1);
        }

        .dispatch-btn.healthy {
          border-color: rgba(0, 255, 136, 0.2);
          color: var(--text-dim, #555566);
          cursor: default;
        }

        /* Shutdown controls */
        .shutdown-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 4px;
        }

        .shutdown-btn {
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid rgba(255, 68, 68, 0.3);
          border-radius: 4px;
          color: var(--status-critical, #ff4444);
          padding: 4px 6px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          cursor: pointer;
          text-transform: uppercase;
          min-height: 28px;
          transition: all 0.15s ease;
        }

        .shutdown-btn:hover {
          background: rgba(255, 68, 68, 0.25);
        }

        .shutdown-btn.is-shutdown {
          background: rgba(255, 68, 68, 0.3);
          border-color: var(--status-critical, #ff4444);
        }

        .restart-btn {
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid rgba(0, 255, 136, 0.3);
          border-radius: 4px;
          color: var(--status-nominal, #00ff88);
          padding: 4px 6px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          cursor: pointer;
          text-transform: uppercase;
          min-height: 28px;
          transition: all 0.15s ease;
        }

        .restart-btn:hover {
          background: rgba(0, 255, 136, 0.25);
        }

        /* Power allocation summary */
        .power-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 4px;
        }

        .power-label {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
          width: 70px;
          flex-shrink: 0;
        }

        .power-bar {
          flex: 1;
          height: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
        }

        .power-fill {
          height: 100%;
          background: var(--status-info, #00aaff);
          border-radius: 4px;
          transition: width 0.3s ease;
        }

        .power-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          width: 32px;
          text-align: right;
          flex-shrink: 0;
        }

        /* Priority display */
        .priority-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 3px;
        }

        .priority-label {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
          width: 70px;
          flex-shrink: 0;
        }

        .priority-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--status-info, #00aaff);
          width: 20px;
          text-align: center;
        }

        .priority-bar {
          flex: 1;
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          overflow: hidden;
        }

        .priority-fill {
          height: 100%;
          background: var(--status-info, #00aaff);
          border-radius: 3px;
          opacity: 0.6;
        }

        /* Status info */
        .stat-row {
          display: flex;
          justify-content: space-between;
          padding: 2px 0;
          font-size: 0.75rem;
        }

        .stat-label {
          color: var(--text-dim, #555566);
        }

        .stat-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-secondary, #888899);
        }

        .stat-value.warning { color: var(--status-warning, #ffaa00); }
        .stat-value.critical { color: var(--status-critical, #ff4444); }
        .stat-value.nominal { color: var(--status-nominal, #00ff88); }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 16px;
          font-style: italic;
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for OPS data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for OPS data...</div>';
      return;
    }

    const ops = ship.ops;
    const subsystemHealth = ship.subsystem_health;

    let html = "";

    // --- Repair Teams ---
    html += '<div class="section">';
    html += '<div class="section-title">Damage Control Teams</div>';

    if (ops && ops.repair_teams && ops.repair_teams.length > 0) {
      for (const team of ops.repair_teams) {
        const statusClass = team.status || "idle";
        const target = team.assigned_subsystem
          ? (SUBSYSTEM_LABELS[team.assigned_subsystem] || team.assigned_subsystem)
          : "Standby";
        const eta = team.status === "en_route"
          ? `ETA ${team.transit_remaining.toFixed(0)}s`
          : "";

        html += `
          <div class="repair-team ${statusClass}">
            <span class="team-id">${team.team_id}</span>
            <span class="team-status ${statusClass}">${team.status.replace("_", " ")}</span>
            <span class="team-target">${target}</span>
            <span class="team-eta">${eta}</span>
          </div>`;
      }
    } else {
      html += '<div class="empty-state">No repair teams available</div>';
    }

    // Dispatch buttons (only for damaged subsystems)
    if (subsystemHealth && subsystemHealth.subsystems) {
      html += '<div class="dispatch-grid">';
      const subs = subsystemHealth.subsystems;
      for (const [name, report] of Object.entries(subs)) {
        const label = SUBSYSTEM_LABELS[name] || name;
        const status = report.status || "online";
        const healthPct = report.health_percent ?? 100;

        let btnClass = "healthy";
        if (status === "destroyed") btnClass = "offline";
        else if (status === "offline" || healthPct < 25) btnClass = "offline";
        else if (status === "damaged" || healthPct < 75) btnClass = "damaged";

        const canRepair = status !== "destroyed" && healthPct < 100;
        html += `
          <button class="dispatch-btn ${btnClass}"
                  data-subsystem="${name}"
                  data-action="dispatch"
                  ${!canRepair ? "disabled" : ""}
                  title="${canRepair ? `Dispatch team to ${label}` : `${label} ${status}`}">
            ${label} ${healthPct.toFixed(0)}%
          </button>`;
      }
      html += "</div>";
    }

    html += "</div>";

    // --- Emergency Shutdown / Restart ---
    html += '<div class="section">';
    html += '<div class="section-title">Emergency Shutdown</div>';

    const shutdownSystems = ops?.shutdown_systems || [];

    if (subsystemHealth && subsystemHealth.subsystems) {
      html += '<div class="shutdown-grid">';
      for (const [name, report] of Object.entries(subsystemHealth.subsystems)) {
        if (name === "reactor") continue; // Can't shutdown reactor from OPS
        const label = SUBSYSTEM_LABELS[name] || name;
        const isShutdown = shutdownSystems.includes(name);

        if (isShutdown) {
          html += `
            <button class="restart-btn" data-subsystem="${name}" data-action="restart"
                    title="Restart ${label}">
              ${label} [restart]
            </button>`;
        } else {
          html += `
            <button class="shutdown-btn" data-subsystem="${name}" data-action="shutdown"
                    title="Emergency shutdown ${label}">
              ${label}
            </button>`;
        }
      }
      html += "</div>";
    }

    html += "</div>";

    // --- Power Allocation ---
    if (ops && ops.power_allocation) {
      html += '<div class="section">';
      html += '<div class="section-title">Power Allocation</div>';

      const alloc = ops.power_allocation;
      const sorted = Object.entries(alloc).sort((a, b) => b[1] - a[1]);
      for (const [name, fraction] of sorted) {
        const label = SUBSYSTEM_LABELS[name] || name;
        const pct = (fraction * 100).toFixed(0);
        html += `
          <div class="power-row">
            <span class="power-label">${label}</span>
            <div class="power-bar">
              <div class="power-fill" style="width: ${pct}%"></div>
            </div>
            <span class="power-value">${pct}%</span>
          </div>`;
      }
      html += "</div>";
    }

    // --- System Priorities ---
    if (ops && ops.system_priorities) {
      html += '<div class="section">';
      html += '<div class="section-title">System Priorities</div>';

      const priorities = Object.entries(ops.system_priorities)
        .sort((a, b) => b[1] - a[1]);
      for (const [name, prio] of priorities) {
        const label = SUBSYSTEM_LABELS[name] || name;
        html += `
          <div class="priority-row">
            <span class="priority-label">${label}</span>
            <span class="priority-value">${prio}</span>
            <div class="priority-bar">
              <div class="priority-fill" style="width: ${prio * 10}%"></div>
            </div>
          </div>`;
      }
      html += "</div>";
    }

    // --- Stats ---
    if (ops) {
      html += '<div class="section">';
      html += '<div class="section-title">Statistics</div>';
      html += `
        <div class="stat-row">
          <span class="stat-label">Total Repairs Applied</span>
          <span class="stat-value">${(ops.total_repairs_applied || 0).toFixed(1)} HP</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Systems Shutdown</span>
          <span class="stat-value ${shutdownSystems.length > 0 ? 'warning' : ''}">${shutdownSystems.length}</span>
        </div>`;
      html += "</div>";
    }

    content.innerHTML = html;

    // Attach event listeners
    this._attachListeners();
  }

  _attachListeners() {
    // Dispatch repair buttons
    this.shadowRoot.querySelectorAll("[data-action='dispatch']").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const subsystem = e.currentTarget.dataset.subsystem;
        this._sendCommand("dispatch_repair", { subsystem });
      });
    });

    // Emergency shutdown buttons
    this.shadowRoot.querySelectorAll("[data-action='shutdown']").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const subsystem = e.currentTarget.dataset.subsystem;
        this._sendCommand("emergency_shutdown", { subsystem });
      });
    });

    // Restart buttons
    this.shadowRoot.querySelectorAll("[data-action='restart']").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const subsystem = e.currentTarget.dataset.subsystem;
        this._sendCommand("restart_system", { subsystem });
      });
    });
  }
}

customElements.define("ops-control-panel", OpsControlPanel);
export { OpsControlPanel };
