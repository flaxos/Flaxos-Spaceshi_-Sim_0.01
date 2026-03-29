/**
 * Subsystem Status Panel
 * Displays all ship subsystems with health integrity, heat levels,
 * cascade effects, and mission kill status. Color-coded for quick reading.
 */

import { stateManager } from "../js/state-manager.js";

// Display names and ordering for subsystems
const SUBSYSTEM_ORDER = [
  "reactor",
  "propulsion",
  "rcs",
  "sensors",
  "targeting",
  "weapons",
  "life_support",
  "radiators",
];

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

// Estimated repair times (seconds) based on damage severity
function estimateRepairTime(healthPercent, status) {
  if (status === "destroyed") return null; // Cannot repair
  if (status === "online") return 0;
  // Auto-repair rate: 0.5 hp/s, max 100 hp
  const hpMissing = 100 - healthPercent;
  const repairRate = 0.5; // hp/s from DamageModel.AUTO_REPAIR_RATE
  return Math.ceil(hpMissing / repairRate);
}

function formatTime(seconds) {
  if (seconds === null) return "N/A";
  if (seconds <= 0) return "--";
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

class SubsystemStatusPanel extends HTMLElement {
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
          padding: 0;
        }

        /* Mission kill banner */
        .mission-kill-banner {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          margin-bottom: 12px;
          border-radius: 6px;
          font-weight: 600;
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          animation: pulse 1s ease-in-out infinite;
        }

        .mission-kill-banner.critical {
          background: rgba(255, 68, 68, 0.15);
          border: 1px solid var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .mission-kill-banner.mobility {
          background: rgba(255, 170, 0, 0.15);
          border: 1px solid var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .mission-kill-banner.firepower {
          background: rgba(255, 170, 0, 0.15);
          border: 1px solid var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .banner-icon {
          font-size: 1rem;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        /* Subsystem rows */
        .subsystem-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .subsystem-row {
          padding: 8px 10px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
          border-left: 3px solid var(--status-nominal, #00ff88);
        }

        .subsystem-row.status-online {
          border-left-color: var(--status-nominal, #00ff88);
        }

        .subsystem-row.status-damaged {
          border-left-color: var(--status-warning, #ffaa00);
        }

        .subsystem-row.status-offline {
          border-left-color: var(--status-offline, #555566);
        }

        .subsystem-row.status-destroyed {
          border-left-color: var(--status-critical, #ff4444);
        }

        /* Header: name + status badge */
        .subsystem-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 6px;
        }

        .subsystem-name {
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
        }

        .subsystem-badge {
          font-size: 0.65rem;
          padding: 2px 6px;
          border-radius: 3px;
          text-transform: uppercase;
          font-weight: 600;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .subsystem-badge.online {
          background: rgba(0, 255, 136, 0.15);
          color: var(--status-nominal, #00ff88);
        }

        .subsystem-badge.damaged {
          background: rgba(255, 170, 0, 0.15);
          color: var(--status-warning, #ffaa00);
        }

        .subsystem-badge.offline {
          background: rgba(85, 85, 102, 0.15);
          color: var(--text-dim, #555566);
        }

        .subsystem-badge.destroyed {
          background: rgba(255, 68, 68, 0.15);
          color: var(--status-critical, #ff4444);
        }

        /* Health bar */
        .bar-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
        }

        .bar-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          width: 32px;
          flex-shrink: 0;
        }

        .bar {
          flex: 1;
          height: 10px;
          background: var(--bg-input, #1a1a24);
          border-radius: 5px;
          overflow: hidden;
        }

        .bar-fill {
          height: 100%;
          transition: width 0.3s ease;
          border-radius: 5px;
        }

        .bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .bar-fill.critical { background: var(--status-critical, #ff4444); }
        .bar-fill.heat { background: linear-gradient(90deg, var(--status-warning, #ffaa00), var(--status-critical, #ff4444)); }
        
        .bar-fill.destroyed {
          background: repeating-linear-gradient(
            -45deg,
            var(--status-critical, #ff4444),
            var(--status-critical, #ff4444) 4px,
            rgba(255, 68, 68, 0.3) 4px,
            rgba(255, 68, 68, 0.3) 8px
          );
          animation: pulse 1.5s ease-in-out infinite;
        }

        .bar-fill.overheated {
          animation: pulse 0.8s ease-in-out infinite;
        }

        .bar-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
          width: 36px;
          text-align: right;
          flex-shrink: 0;
        }

        .bar-value.nominal { color: var(--status-nominal, #00ff88); }
        .bar-value.warning { color: var(--status-warning, #ffaa00); }
        .bar-value.critical { color: var(--status-critical, #ff4444); }

        .cascade-badge {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.55rem;
          color: var(--status-critical, #ff4444);
          border: 1px solid var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.15);
          padding: 1px 4px;
          border-radius: 3px;
          margin-left: 6px;
          vertical-align: middle;
        }

        /* Subsystem details row */
        .subsystem-details {
          display: flex;
          gap: 12px;
          font-size: 0.7rem;
          margin-top: 4px;
        }

        .detail-item {
          display: flex;
          gap: 4px;
        }

        .detail-key {
          color: var(--text-dim, #555566);
        }

        .detail-val {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-secondary, #888899);
        }

        .detail-val.warning { color: var(--status-warning, #ffaa00); }
        .detail-val.critical { color: var(--status-critical, #ff4444); }

        /* Cascade effects section */
        .cascade-section {
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .cascade-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--status-warning, #ffaa00);
          margin-bottom: 8px;
        }

        .cascade-item {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 4px 0;
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
        }

        .cascade-icon {
          color: var(--status-warning, #ffaa00);
          flex-shrink: 0;
          margin-top: 1px;
        }

        .cascade-desc {
          color: var(--status-warning, #ffaa00);
          font-weight: 500;
        }

        .cascade-factor {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-dim, #555566);
          margin-left: auto;
          flex-shrink: 0;
        }

        /* NO SENSOR DATA overlay */
        .no-data-overlay {
          padding: 6px 10px;
          margin-top: 4px;
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid rgba(255, 68, 68, 0.3);
          border-radius: 4px;
          color: var(--status-critical, #ff4444);
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for subsystem data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for subsystem data...</div>';
      return;
    }

    const subsystemHealth = ship.subsystem_health;
    const cascadeEffects = ship.cascade_effects;

    if (!subsystemHealth?.subsystems || Object.keys(subsystemHealth.subsystems).length === 0) {
      content.innerHTML = '<div class="empty-state">No subsystem data available</div>';
      return;
    }

    const subs = subsystemHealth.subsystems;
    const cascadeFactors = cascadeEffects?.factors || {};
    const activeCascades = cascadeEffects?.active_cascades || [];

    let html = "";

    // Mission kill banner
    html += this._renderMissionKillBanner(subsystemHealth);

    // Subsystem rows
    html += '<div class="subsystem-list">';

    // Render in defined order, then any extras
    const renderedNames = new Set();
    for (const name of SUBSYSTEM_ORDER) {
      if (subs[name]) {
        html += this._renderSubsystem(name, subs[name], cascadeFactors[name], activeCascades);
        renderedNames.add(name);
      }
    }
    // Render any subsystems not in SUBSYSTEM_ORDER
    for (const [name, report] of Object.entries(subs)) {
      if (!renderedNames.has(name)) {
        html += this._renderSubsystem(name, report, cascadeFactors[name], activeCascades);
      }
    }

    html += "</div>";

    // Cascade effects summary
    if (activeCascades.length > 0) {
      html += this._renderCascadeSection(activeCascades);
    }

    content.innerHTML = html;
  }

  _renderMissionKillBanner(subsystemHealth) {
    const { mission_kill, mobility_kill, firepower_kill, mission_kill_reason } = subsystemHealth;

    if (!mission_kill) return "";

    if (mobility_kill && firepower_kill) {
      return `
        <div class="mission-kill-banner critical">
          <span class="banner-icon">!!</span>
          MISSION KILL - ${mission_kill_reason || "mobility + firepower compromised"}
        </div>`;
    }
    if (mobility_kill) {
      return `
        <div class="mission-kill-banner mobility">
          <span class="banner-icon">!</span>
          MOBILITY KILL - Cannot maneuver
        </div>`;
    }
    if (firepower_kill) {
      return `
        <div class="mission-kill-banner firepower">
          <span class="banner-icon">!</span>
          FIREPOWER KILL - Weapons offline
        </div>`;
    }
    return "";
  }

  _renderSubsystem(name, report, cascadeFactor, activeCascades) {
    const label = SUBSYSTEM_LABELS[name] || name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    const status = report.status || "online";
    const healthPct = report.health_percent ?? 100;
    const heatPct = report.heat_percent ?? 0;
    const overheated = report.overheated || false;
    const isCritical = report.is_critical || false;

    // Health bar gradient color
    let healthColorObj = "";
    if (healthPct > 50) {
      healthColorObj = `color-mix(in srgb, var(--status-nominal, #00ff88) ${(healthPct - 50) * 2}%, var(--status-warning, #ffaa00))`;
    } else {
      healthColorObj = `color-mix(in srgb, var(--status-warning, #ffaa00) ${(healthPct) * 2}%, var(--status-critical, #ff4444))`;
    }
    
    // Health bar class / inline style
    const isDestroyed = status === "destroyed";
    const healthBarClassStr = isDestroyed ? "destroyed" : "";
    const healthBarStyleStr = isDestroyed ? `width: 100%` : `width: ${healthPct}%; background: ${healthColorObj}`;
    const healthValueClass = healthPct > 75 ? "nominal" : healthPct > 25 ? "warning" : "critical";

    // Heat bar
    const showHeat = heatPct > 0;
    const heatBarClass = overheated ? "heat overheated" : "heat";

    // Cascade-specific overlays (e.g., targeting affected by sensors)
    const cascadesAffecting = activeCascades.filter(c => c.dependent === name);
    const hasCascade = cascadeFactor !== undefined && cascadeFactor < 1.0;
    const cascadeBadgeHTML = hasCascade ? `<span class="cascade-badge">[CASCADE]</span>` : "";

    // Repair time estimate
    const repairTime = estimateRepairTime(healthPct, status);

    // Effective performance = combined_factor (damage * heat) * cascade
    const combinedFactor = report.combined_factor ?? 1.0;
    const effectiveFactor = hasCascade ? combinedFactor * cascadeFactor : combinedFactor;

    let detailsHtml = '<div class="subsystem-details">';

    // Show effective performance if degraded
    if (effectiveFactor < 1.0) {
      const perfClass = effectiveFactor > 0.5 ? "warning" : "critical";
      detailsHtml += `
        <div class="detail-item">
          <span class="detail-key">Perf:</span>
          <span class="detail-val ${perfClass}">${(effectiveFactor * 100).toFixed(0)}%</span>
        </div>`;
    }

    // Repair time
    if (repairTime !== null && repairTime > 0) {
      detailsHtml += `
        <div class="detail-item">
          <span class="detail-key">Repair:</span>
          <span class="detail-val">${formatTime(repairTime)}</span>
        </div>`;
    }

    // Overheated indicator
    if (overheated) {
      detailsHtml += `
        <div class="detail-item">
          <span class="detail-val critical">OVERHEATED</span>
        </div>`;
    }

    // Critical indicator
    if (isCritical) {
      detailsHtml += `
        <div class="detail-item">
          <span class="detail-val critical">CRITICAL</span>
        </div>`;
    }

    detailsHtml += "</div>";

    // Cascade-driven "NO DATA" overlays for specific subsystems
    let cascadeOverlay = "";
    if (name === "targeting" && cascadesAffecting.some(c => c.source === "sensors")) {
      const sensorCascade = cascadesAffecting.find(c => c.source === "sensors");
      if (sensorCascade && sensorCascade.cascade_factor <= 0) {
        cascadeOverlay = '<div class="no-data-overlay">NO SENSOR DATA</div>';
      }
    }

    return `
      <div class="subsystem-row status-${status}">
        <div class="subsystem-header">
          <span class="subsystem-name">${label}${cascadeBadgeHTML}</span>
          <span class="subsystem-badge ${status}">${status}</span>
        </div>
        <div class="bar-row">
          <span class="bar-label">HP</span>
          <div class="bar">
            <div class="bar-fill ${healthBarClassStr}" style="${healthBarStyleStr}"></div>
          </div>
          <span class="bar-value ${healthValueClass}">${healthPct.toFixed(0)}%</span>
        </div>
        ${showHeat ? `
        <div class="bar-row">
          <span class="bar-label">Heat</span>
          <div class="bar">
            <div class="bar-fill ${heatBarClass}" style="width: ${heatPct}%"></div>
          </div>
          <span class="bar-value${overheated ? ' critical' : ''}">${heatPct.toFixed(0)}%</span>
        </div>` : ""}
        ${detailsHtml}
        ${cascadeOverlay}
      </div>`;
  }

  _renderCascadeSection(activeCascades) {
    let html = `
      <div class="cascade-section">
        <div class="cascade-title">Cascade Effects</div>`;

    for (const cascade of activeCascades) {
      const factorPct = ((cascade.cascade_factor ?? 1) * 100).toFixed(0);
      html += `
        <div class="cascade-item">
          <span class="cascade-icon">></span>
          <span class="cascade-desc">${cascade.description}</span>
          <span class="cascade-factor">${factorPct}%</span>
        </div>`;
    }

    html += "</div>";
    return html;
  }
}

customElements.define("subsystem-status-panel", SubsystemStatusPanel);
export { SubsystemStatusPanel };
