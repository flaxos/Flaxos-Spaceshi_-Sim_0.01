/**
 * Subsystem Status Panel
 * Displays all ship subsystems with health integrity, heat levels,
 * cascade effects, and mission kill status. Color-coded for quick reading.
 *
 * Tier awareness:
 *   MANUAL:     Raw HP numbers (e.g., "2847/4000 HP"). Heat in joules. Status as 0.0-1.0 factor.
 *   RAW:        Health bars + exact percentages + numeric readouts. Heat gauges with temperature. Criticality.
 *   ARCADE:     Status chips only: NOMINAL/IMPAIRED/OFFLINE/DESTROYED. Simple health bar. No numbers.
 *   CPU-ASSIST: High-level summary ("3 nominal, 1 impaired"). Auto-repair priority list.
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

/** Map status strings to ARCADE-style chip labels */
function statusToChipLabel(status) {
  const s = (status || "online").toLowerCase();
  if (s === "online" || s === "nominal" || s === "active") return "NOMINAL";
  if (s === "damaged" || s === "impaired" || s === "degraded") return "IMPAIRED";
  if (s === "offline" || s === "disabled") return "OFFLINE";
  if (s === "destroyed") return "DESTROYED";
  return "NOMINAL";
}

/** Map status strings to chip CSS class */
function statusToChipClass(status) {
  const label = statusToChipLabel(status);
  return label.toLowerCase();
}

class SubsystemStatusPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tierHandler = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._applyTier();
    this._tierHandler = () => this._applyTier();
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("subsystem_health", () => {
      this._updateDisplay();
    });
  }

  _getTier() {
    return window.controlTier || "arcade";
  }

  /** Full re-render when tier changes (layout differs per tier) */
  _applyTier() {
    this.render();
    this._updateDisplay();
  }

  render() {
    const tier = this._getTier();
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._tierStyles(tier)}</style>
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

    const tier = this._getTier();
    if (tier === "manual") {
      this._renderManual(content, subsystemHealth, cascadeEffects);
    } else if (tier === "raw") {
      this._renderRaw(content, subsystemHealth, cascadeEffects);
    } else if (tier === "cpu-assist") {
      this._renderCpuAssist(content, subsystemHealth, cascadeEffects);
    } else {
      this._renderArcade(content, subsystemHealth, cascadeEffects);
    }
  }

  // ---------------------------------------------------------------------------
  // MANUAL tier: raw HP, heat in joules, status as 0.0-1.0 factor
  // ---------------------------------------------------------------------------

  _renderManual(content, subsystemHealth, cascadeEffects) {
    const subs = subsystemHealth.subsystems;
    const cascadeFactors = cascadeEffects?.factors || {};
    let html = "";

    html += this._renderMissionKillBanner(subsystemHealth);
    html += '<div class="subsystem-list">';

    const orderedNames = this._getOrderedNames(subs);
    for (const name of orderedNames) {
      const report = subs[name];
      const label = SUBSYSTEM_LABELS[name] || name.replace(/_/g, " ").toUpperCase();
      const healthPct = report.health_percent ?? 100;
      const heatPct = report.heat_percent ?? 0;
      const status = report.status || "online";
      const combinedFactor = report.combined_factor ?? 1.0;
      const cascadeFactor = cascadeFactors[name];
      const effectiveFactor = cascadeFactor !== undefined && cascadeFactor < 1.0
        ? combinedFactor * cascadeFactor : combinedFactor;

      // Raw HP: assume 100 HP max, scale to display
      const maxHp = 4000;
      const currentHp = Math.round((healthPct / 100) * maxHp);
      // Heat as joules (derived from percentage, assume 1000J thermal budget)
      const heatJoules = Math.round((heatPct / 100) * 1000);
      const maxHeatJ = 1000;

      html += `
        <div class="subsystem-row manual-row">
          <div class="manual-header">
            <span class="manual-name">${label}</span>
            <span class="manual-factor">${effectiveFactor.toFixed(3)}</span>
          </div>
          <div class="manual-stat">
            <span class="manual-key">HP</span>
            <span class="manual-val">${currentHp} / ${maxHp}</span>
          </div>
          <div class="manual-stat">
            <span class="manual-key">HEAT</span>
            <span class="manual-val${heatPct > 80 ? ' critical' : heatPct > 50 ? ' warning' : ''}">${heatJoules} / ${maxHeatJ} J</span>
          </div>
          <div class="manual-stat">
            <span class="manual-key">STATUS</span>
            <span class="manual-val">${effectiveFactor.toFixed(2)}</span>
          </div>
          ${cascadeFactor !== undefined && cascadeFactor < 1.0 ? `
          <div class="manual-stat">
            <span class="manual-key">CASCADE</span>
            <span class="manual-val warning">${cascadeFactor.toFixed(3)}</span>
          </div>` : ""}
        </div>`;
    }

    html += "</div>";
    content.innerHTML = html;
  }

  // ---------------------------------------------------------------------------
  // RAW tier: health bars + exact percentages, heat gauges, criticality
  // This is the original detailed view with all numeric readouts.
  // ---------------------------------------------------------------------------

  _renderRaw(content, subsystemHealth, cascadeEffects) {
    const subs = subsystemHealth.subsystems;
    const cascadeFactors = cascadeEffects?.factors || {};
    const activeCascades = cascadeEffects?.active_cascades || [];
    let html = "";

    html += this._renderMissionKillBanner(subsystemHealth);
    html += '<div class="subsystem-list">';

    const orderedNames = this._getOrderedNames(subs);
    for (const name of orderedNames) {
      html += this._renderSubsystemRaw(name, subs[name], cascadeFactors[name], activeCascades);
    }

    html += "</div>";

    if (activeCascades.length > 0) {
      html += this._renderCascadeSection(activeCascades);
    }

    content.innerHTML = html;
  }

  /** Detailed subsystem row (RAW tier) — identical to the original render */
  _renderSubsystemRaw(name, report, cascadeFactor, activeCascades) {
    const label = SUBSYSTEM_LABELS[name] || name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    const status = report.status || "online";
    const healthPct = report.health_percent ?? 100;
    const heatPct = report.heat_percent ?? 0;
    const overheated = report.overheated || false;
    const isCritical = report.is_critical || false;

    let healthColorObj = "";
    if (healthPct > 50) {
      healthColorObj = `color-mix(in srgb, var(--status-nominal, #00ff88) ${(healthPct - 50) * 2}%, var(--status-warning, #ffaa00))`;
    } else {
      healthColorObj = `color-mix(in srgb, var(--status-warning, #ffaa00) ${(healthPct) * 2}%, var(--status-critical, #ff4444))`;
    }

    const isDestroyed = status === "destroyed";
    const healthBarClassStr = isDestroyed ? "destroyed" : "";
    const healthBarStyleStr = isDestroyed ? `width: 100%` : `width: ${healthPct}%; background: ${healthColorObj}`;
    const healthValueClass = healthPct > 75 ? "nominal" : healthPct > 25 ? "warning" : "critical";

    const showHeat = heatPct > 0;
    const heatBarClass = overheated ? "heat overheated" : "heat";

    const cascadesAffecting = activeCascades.filter(c => c.dependent === name);
    const hasCascade = cascadeFactor !== undefined && cascadeFactor < 1.0;
    const cascadeBadgeHTML = hasCascade ? `<span class="cascade-badge">[CASCADE]</span>` : "";

    const repairTime = estimateRepairTime(healthPct, status);

    const combinedFactor = report.combined_factor ?? 1.0;
    const effectiveFactor = hasCascade ? combinedFactor * cascadeFactor : combinedFactor;

    let detailsHtml = '<div class="subsystem-details">';

    if (effectiveFactor < 1.0) {
      const perfClass = effectiveFactor > 0.5 ? "warning" : "critical";
      detailsHtml += `
        <div class="detail-item">
          <span class="detail-key">Perf:</span>
          <span class="detail-val ${perfClass}">${(effectiveFactor * 100).toFixed(0)}%</span>
        </div>`;
    }

    if (repairTime !== null && repairTime > 0) {
      detailsHtml += `
        <div class="detail-item">
          <span class="detail-key">Repair:</span>
          <span class="detail-val">${formatTime(repairTime)}</span>
        </div>`;
    }

    if (overheated) {
      detailsHtml += `<div class="detail-item"><span class="detail-val critical">OVERHEATED</span></div>`;
    }

    if (isCritical) {
      detailsHtml += `<div class="detail-item"><span class="detail-val critical">CRITICAL</span></div>`;
    }

    detailsHtml += "</div>";

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

  // ---------------------------------------------------------------------------
  // ARCADE tier: status chips (NOMINAL/IMPAIRED/OFFLINE/DESTROYED) + simple bar
  // ---------------------------------------------------------------------------

  _renderArcade(content, subsystemHealth, cascadeEffects) {
    const subs = subsystemHealth.subsystems;
    let html = "";

    html += this._renderMissionKillBanner(subsystemHealth);
    html += '<div class="subsystem-list">';

    const orderedNames = this._getOrderedNames(subs);
    for (const name of orderedNames) {
      const report = subs[name];
      const label = SUBSYSTEM_LABELS[name] || name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
      const status = report.status || "online";
      const healthPct = report.health_percent ?? 100;
      const chipLabel = statusToChipLabel(status);
      const chipClass = statusToChipClass(status);

      // Simple health bar color
      let barColor = "var(--status-nominal, #00ff88)";
      if (chipClass === "impaired") barColor = "var(--status-warning, #ffaa00)";
      else if (chipClass === "offline") barColor = "var(--status-offline, #555566)";
      else if (chipClass === "destroyed") barColor = "var(--status-critical, #ff4444)";

      html += `
        <div class="subsystem-row arcade-row status-${status}">
          <div class="arcade-header">
            <span class="subsystem-name">${label}</span>
            <span class="arcade-chip ${chipClass}">${chipLabel}</span>
          </div>
          <div class="arcade-bar">
            <div class="arcade-bar-fill" style="width:${healthPct}%; background:${barColor}"></div>
          </div>
        </div>`;
    }

    html += "</div>";
    content.innerHTML = html;
  }

  // ---------------------------------------------------------------------------
  // CPU-ASSIST tier: high-level summary + auto-repair priority list
  // ---------------------------------------------------------------------------

  _renderCpuAssist(content, subsystemHealth, cascadeEffects) {
    const subs = subsystemHealth.subsystems;
    let html = "";

    html += this._renderMissionKillBanner(subsystemHealth);

    // Count by status category
    let nominalCount = 0;
    let impairedCount = 0;
    let offlineCount = 0;
    let destroyedCount = 0;
    const needsRepair = [];

    const orderedNames = this._getOrderedNames(subs);
    for (const name of orderedNames) {
      const report = subs[name];
      const chip = statusToChipLabel(report.status);
      const healthPct = report.health_percent ?? 100;
      const label = SUBSYSTEM_LABELS[name] || name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());

      if (chip === "NOMINAL") nominalCount++;
      else if (chip === "IMPAIRED") impairedCount++;
      else if (chip === "OFFLINE") offlineCount++;
      else if (chip === "DESTROYED") destroyedCount++;

      if (chip !== "NOMINAL" && chip !== "DESTROYED" && healthPct < 100) {
        const repairTime = estimateRepairTime(healthPct, report.status);
        needsRepair.push({ name, label, healthPct, repairTime, status: chip });
      }
    }

    // Summary line
    const parts = [];
    if (nominalCount > 0) parts.push(`<span class="summary-count nominal">${nominalCount} nominal</span>`);
    if (impairedCount > 0) parts.push(`<span class="summary-count impaired">${impairedCount} impaired</span>`);
    if (offlineCount > 0) parts.push(`<span class="summary-count offline">${offlineCount} offline</span>`);
    if (destroyedCount > 0) parts.push(`<span class="summary-count destroyed">${destroyedCount} destroyed</span>`);

    html += `<div class="assist-summary">${parts.join('<span class="summary-sep">,</span> ')}</div>`;

    // Quick status grid: one chip per subsystem
    html += '<div class="assist-grid">';
    for (const name of orderedNames) {
      const report = subs[name];
      const label = SUBSYSTEM_LABELS[name] || name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
      const chipClass = statusToChipClass(report.status);
      const chipLabel = statusToChipLabel(report.status);
      html += `
        <div class="assist-chip-row">
          <span class="assist-label">${label}</span>
          <span class="arcade-chip ${chipClass}">${chipLabel}</span>
        </div>`;
    }
    html += '</div>';

    // Auto-repair priority list
    if (needsRepair.length > 0) {
      // Sort by health ascending (worst first)
      needsRepair.sort((a, b) => a.healthPct - b.healthPct);
      html += '<div class="assist-repair-section">';
      html += '<div class="assist-repair-title">Auto-Repair Priority</div>';
      for (const item of needsRepair) {
        const eta = item.repairTime !== null ? formatTime(item.repairTime) : "N/A";
        html += `
          <div class="assist-repair-row">
            <span class="assist-repair-rank">${needsRepair.indexOf(item) + 1}.</span>
            <span class="assist-repair-name">${item.label}</span>
            <span class="assist-repair-pct ${item.healthPct < 30 ? 'critical' : 'warning'}">${item.healthPct.toFixed(0)}%</span>
            <span class="assist-repair-eta">ETA ${eta}</span>
          </div>`;
      }
      html += '</div>';
    } else {
      html += '<div class="assist-all-clear">All systems nominal. No repairs needed.</div>';
    }

    content.innerHTML = html;
  }

  // ---------------------------------------------------------------------------
  // Shared renderers
  // ---------------------------------------------------------------------------

  /** Get subsystem names in defined order, then extras */
  _getOrderedNames(subs) {
    const names = [];
    const seen = new Set();
    for (const name of SUBSYSTEM_ORDER) {
      if (subs[name]) { names.push(name); seen.add(name); }
    }
    for (const name of Object.keys(subs)) {
      if (!seen.has(name)) names.push(name);
    }
    return names;
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

  // ---------------------------------------------------------------------------
  // Styles
  // ---------------------------------------------------------------------------

  _baseStyles() {
    return `
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
      .banner-icon { font-size: 1rem; }

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
      .subsystem-row.status-online { border-left-color: var(--status-nominal, #00ff88); }
      .subsystem-row.status-damaged { border-left-color: var(--status-warning, #ffaa00); }
      .subsystem-row.status-offline { border-left-color: var(--status-offline, #555566); }
      .subsystem-row.status-destroyed { border-left-color: var(--status-critical, #ff4444); }

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
      .bar-fill.overheated { animation: pulse 0.8s ease-in-out infinite; }

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
      .detail-item { display: flex; gap: 4px; }
      .detail-key { color: var(--text-dim, #555566); }
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
    `;
  }

  _tierStyles(tier) {
    if (tier === "manual") return this._manualStyles();
    if (tier === "raw") return this._rawStyles();
    if (tier === "arcade") return this._arcadeStyles();
    if (tier === "cpu-assist") return this._cpuAssistStyles();
    return "";
  }

  _manualStyles() {
    return `
      :host {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: #ffe0b0;
      }
      .subsystem-list { gap: 6px; }
      .manual-row {
        border-radius: 0;
        border-left: 2px solid #ff8800;
        padding: 6px 8px;
        background: rgba(255, 136, 0, 0.04);
      }
      .manual-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
      }
      .manual-name {
        font-weight: 700;
        font-size: 0.75rem;
        text-transform: uppercase;
        color: #ffe0b0;
      }
      .manual-factor {
        font-size: 0.7rem;
        color: #ff880088;
      }
      .manual-stat {
        display: flex;
        justify-content: space-between;
        font-size: 0.7rem;
        padding: 1px 0;
      }
      .manual-key {
        color: #ff880066;
        text-transform: uppercase;
        width: 60px;
        flex-shrink: 0;
      }
      .manual-val {
        color: #ffe0b0;
        text-align: right;
      }
      .manual-val.warning { color: var(--status-warning, #ffaa00); }
      .manual-val.critical { color: var(--status-critical, #ff4444); }
      .mission-kill-banner { border-radius: 0; }
    `;
  }

  _rawStyles() {
    return `
      :host {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
      }
      .subsystem-row { border-radius: 0; }
      .subsystem-name { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; }
      .bar { border-radius: 0; }
      .bar-fill { border-radius: 0; }
      .mission-kill-banner { border-radius: 0; }
    `;
  }

  _arcadeStyles() {
    return `
      .arcade-row {
        border-left: none;
        border-radius: 8px;
        padding: 10px 12px;
        background: rgba(68, 136, 255, 0.03);
      }
      .arcade-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
      }
      .arcade-chip {
        font-size: 0.7rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .arcade-chip.nominal {
        background: rgba(0, 255, 136, 0.15);
        color: var(--status-nominal, #00ff88);
      }
      .arcade-chip.impaired {
        background: rgba(255, 170, 0, 0.15);
        color: var(--status-warning, #ffaa00);
      }
      .arcade-chip.offline {
        background: rgba(85, 85, 102, 0.2);
        color: var(--text-dim, #555566);
      }
      .arcade-chip.destroyed {
        background: rgba(255, 68, 68, 0.2);
        color: var(--status-critical, #ff4444);
      }
      .arcade-bar {
        height: 6px;
        background: var(--bg-input, #1a1a24);
        border-radius: 3px;
        overflow: hidden;
      }
      .arcade-bar-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.3s ease;
      }
    `;
  }

  _cpuAssistStyles() {
    return `
      .assist-summary {
        font-size: 1rem;
        font-weight: 600;
        padding: 10px 0 14px;
        text-align: center;
      }
      .summary-count {
        font-weight: 700;
      }
      .summary-count.nominal { color: var(--status-nominal, #00ff88); }
      .summary-count.impaired { color: var(--status-warning, #ffaa00); }
      .summary-count.offline { color: var(--text-dim, #555566); }
      .summary-count.destroyed { color: var(--status-critical, #ff4444); }
      .summary-sep { color: var(--text-dim, #444); }

      .assist-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px;
        margin-bottom: 16px;
      }
      .assist-chip-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 6px 10px;
        background: rgba(128, 0, 255, 0.04);
        border-radius: 6px;
      }
      .assist-label {
        font-size: 0.8rem;
        color: var(--text-primary, #e0e0e0);
      }
      .arcade-chip {
        font-size: 0.65rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 10px;
        text-transform: uppercase;
      }
      .arcade-chip.nominal {
        background: rgba(0, 255, 136, 0.15);
        color: var(--status-nominal, #00ff88);
      }
      .arcade-chip.impaired {
        background: rgba(255, 170, 0, 0.15);
        color: var(--status-warning, #ffaa00);
      }
      .arcade-chip.offline {
        background: rgba(85, 85, 102, 0.2);
        color: var(--text-dim, #555566);
      }
      .arcade-chip.destroyed {
        background: rgba(255, 68, 68, 0.2);
        color: var(--status-critical, #ff4444);
      }

      .assist-repair-section {
        padding-top: 12px;
        border-top: 1px solid rgba(128, 0, 255, 0.15);
      }
      .assist-repair-title {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #bb88ff;
        margin-bottom: 8px;
      }
      .assist-repair-row {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 5px 8px;
        margin-bottom: 4px;
        background: rgba(128, 0, 255, 0.04);
        border-radius: 4px;
      }
      .assist-repair-rank {
        font-weight: 700;
        font-size: 0.75rem;
        color: #bb88ff;
        width: 18px;
        flex-shrink: 0;
      }
      .assist-repair-name {
        flex: 1;
        font-size: 0.8rem;
        color: var(--text-primary, #e0e0e0);
      }
      .assist-repair-pct {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.75rem;
        font-weight: 600;
        width: 35px;
        text-align: right;
        flex-shrink: 0;
      }
      .assist-repair-pct.warning { color: var(--status-warning, #ffaa00); }
      .assist-repair-pct.critical { color: var(--status-critical, #ff4444); }
      .assist-repair-eta {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        color: var(--text-dim, #666);
        width: 65px;
        flex-shrink: 0;
      }

      .assist-all-clear {
        text-align: center;
        color: var(--status-nominal, #00ff88);
        font-size: 0.85rem;
        font-weight: 500;
        padding: 16px 0;
      }
    `;
  }
}

customElements.define("subsystem-status-panel", SubsystemStatusPanel);
export { SubsystemStatusPanel };
