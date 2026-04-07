/**
 * Thermal Management Display
 * Shows hull temperature, heat balance, radiator status, and heat sink state.
 * Temperature bar color shifts from blue (cold) through green (nominal) to
 * yellow (warning) and red (emergency) as hull temperature rises.
 *
 * Tier-aware rendering:
 * - MANUAL/RAW: Raw temperature in Kelvin, dissipation in watts, radiator area
 *               in m-squared, coolant level. Full heat balance breakdown.
 * - ARCADE:     Temperature as % of thermal limit, "TIME TO OVERHEAT" countdown,
 *               simplified radiator status (deployed/retracted + efficiency %).
 * - CPU-ASSIST: Thermal summary badge — "NOMINAL" / "WARNING" / "CRITICAL"
 *               with auto-recommendations.
 */

import { stateManager } from "../js/state-manager.js";

class ThermalDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tierHandler = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    // Listen for tier changes — same pattern as flight-computer-panel
    this._tierHandler = () => this._updateDisplay();
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
    this._unsubscribe = stateManager.subscribe("thermal", () => {
      this._updateDisplay();
    });
  }

  /** Get the current control tier. */
  _getTier() {
    return window.controlTier || "raw";
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

        /* --- Temperature headline --- */
        .temp-headline {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          margin-bottom: 12px;
        }

        .temp-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.6rem;
          font-weight: 700;
          line-height: 1;
        }

        .temp-value.nominal  { color: var(--status-nominal, #00ff88); }
        .temp-value.elevated { color: var(--status-info, #00aaff); }
        .temp-value.warning  { color: var(--status-warning, #ffaa00); }
        .temp-value.critical { color: var(--status-critical, #ff4444); }

        .temp-unit {
          font-size: 0.85rem;
          color: var(--text-secondary, #888899);
          margin-left: 2px;
        }

        .status-badge {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          padding: 3px 10px;
          border-radius: 4px;
        }

        .status-badge.nominal {
          background: rgba(0, 255, 136, 0.15);
          color: var(--status-nominal, #00ff88);
        }

        .status-badge.elevated {
          background: rgba(0, 170, 255, 0.15);
          color: var(--status-info, #00aaff);
        }

        .status-badge.warning {
          background: rgba(255, 170, 0, 0.2);
          color: var(--status-warning, #ffaa00);
          animation: pulse 1.2s ease-in-out infinite;
        }

        .status-badge.emergency {
          background: rgba(255, 68, 68, 0.2);
          color: var(--status-critical, #ff4444);
          animation: pulse 0.6s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.5; }
        }

        /* --- Temperature bar --- */
        .temp-bar-container {
          margin-bottom: 16px;
        }

        .temp-bar-labels {
          display: flex;
          justify-content: space-between;
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          margin-bottom: 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .temp-bar {
          height: 10px;
          background: var(--bg-input, #1a1a24);
          border-radius: 5px;
          overflow: hidden;
          position: relative;
        }

        .temp-bar-fill {
          height: 100%;
          border-radius: 5px;
          transition: width 0.4s ease, background 0.4s ease;
        }

        /* Warning threshold marker on the bar */
        .temp-bar-marker {
          position: absolute;
          top: 0;
          height: 100%;
          width: 2px;
          background: rgba(255, 170, 0, 0.6);
        }

        /* --- Section dividers --- */
        .section {
          padding: 10px 0;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .section:first-of-type {
          border-top: none;
          padding-top: 0;
        }

        .section-title {
          font-size: 0.65rem;
          font-weight: 600;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 8px;
        }

        /* --- Key-value rows --- */
        .detail-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 2px 0;
        }

        .detail-label {
          color: var(--text-secondary, #888899);
          font-size: 0.75rem;
        }

        .detail-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        .detail-value.positive { color: var(--status-critical, #ff4444); }
        .detail-value.negative { color: var(--status-nominal, #00ff88); }
        .detail-value.zero     { color: var(--text-secondary, #888899); }
        .detail-value.warning  { color: var(--status-warning, #ffaa00); }

        /* --- Heat balance summary row --- */
        .heat-balance {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
          margin-top: 8px;
        }

        .heat-balance-label {
          font-size: 0.65rem;
          font-weight: 600;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .heat-balance-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          font-weight: 700;
        }

        /* --- Heat sink bar --- */
        .sink-bar {
          height: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
          margin-top: 4px;
        }

        .sink-bar-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s ease;
        }

        .sink-bar-fill.nominal  { background: var(--status-nominal, #00ff88); }
        .sink-bar-fill.warning  { background: var(--status-warning, #ffaa00); }
        .sink-bar-fill.critical { background: var(--status-critical, #ff4444); }

        /* --- Active indicator dot --- */
        .active-dot {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          margin-right: 6px;
          vertical-align: middle;
        }

        .active-dot.on {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 6px var(--status-nominal, #00ff88);
        }

        .active-dot.off {
          background: var(--status-offline, #555566);
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }

        /* --- CPU-ASSIST hero badge --- */
        .thermal-hero-badge {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 20px;
          border-radius: 8px;
          border: 1px solid var(--border-default, #2a2a3a);
          margin-bottom: 12px;
          text-align: center;
        }

        .thermal-hero-badge.nominal {
          background: rgba(0, 255, 136, 0.06);
          border-color: rgba(0, 255, 136, 0.2);
        }

        .thermal-hero-badge.warning {
          background: rgba(255, 170, 0, 0.08);
          border-color: rgba(255, 170, 0, 0.3);
          animation: pulse 1.2s ease-in-out infinite;
        }

        .thermal-hero-badge.critical {
          background: rgba(255, 68, 68, 0.1);
          border-color: rgba(255, 68, 68, 0.4);
          animation: pulse 0.6s ease-in-out infinite;
        }

        .hero-badge-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.4rem;
          font-weight: 700;
          letter-spacing: 1px;
        }

        .hero-badge-label.nominal  { color: var(--status-nominal, #00ff88); }
        .hero-badge-label.warning  { color: var(--status-warning, #ffaa00); }
        .hero-badge-label.critical { color: var(--status-critical, #ff4444); }

        .hero-badge-sub {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
          margin-top: 4px;
        }

        /* Recommendation card */
        .recommendation {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          border-radius: 4px;
          font-size: 0.7rem;
          margin-top: 8px;
        }

        .recommendation.action {
          background: rgba(255, 170, 0, 0.1);
          border: 1px solid rgba(255, 170, 0, 0.3);
          color: var(--status-warning, #ffaa00);
        }

        .recommendation.info {
          background: rgba(0, 170, 255, 0.08);
          border: 1px solid rgba(0, 170, 255, 0.2);
          color: var(--status-info, #00aaff);
        }

        .rec-icon {
          font-size: 0.9rem;
          flex-shrink: 0;
        }

        /* Arcade radiator status */
        .rad-status-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 6px 10px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          border: 1px solid var(--border-default, #2a2a3a);
          margin-top: 8px;
        }

        .rad-status-label {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
        }

        .rad-status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 600;
        }

        @media (max-width: 768px) {
          .temp-value {
            font-size: 1.3rem;
          }
          .hero-badge-label {
            font-size: 1.1rem;
          }
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for thermal data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const thermal = ship?.thermal;
    const content = this.shadowRoot.getElementById("content");

    if (!thermal || !thermal.enabled) {
      content.innerHTML = '<div class="empty-state">Thermal system offline</div>';
      return;
    }

    const tier = this._getTier();

    switch (tier) {
      case "arcade":
        this._renderArcade(content, thermal);
        break;
      case "cpu-assist":
        this._renderCpuAssist(content, thermal);
        break;
      default: // "manual" and "raw" share the same detailed view
        this._renderRaw(content, thermal);
        break;
    }
  }

  // =========================================================================
  // MANUAL + RAW: Full raw thermal data in physical units
  // =========================================================================
  _renderRaw(content, thermal) {
    const hullTemp = thermal.hull_temperature ?? 0;
    const maxTemp = thermal.max_temperature ?? 500;
    const warnTemp = thermal.warning_temperature ?? 400;
    const nominalTemp = thermal.nominal_temperature ?? 300;
    const percent = thermal.temperature_percent ?? ((hullTemp / maxTemp) * 100);
    const status = (thermal.status || "nominal").toLowerCase();
    const statusClass = this._statusClass(status, thermal);
    const barColor = this._tempBarColor(hullTemp, nominalTemp, warnTemp, maxTemp);
    const warnMarkerPct = (warnTemp / maxTemp) * 100;

    // Heat balance in watts
    const heatGen = thermal.heat_generated ?? 0;
    const heatRad = thermal.heat_radiated ?? 0;
    const heatSinkDumped = thermal.heat_sink_dumped ?? 0;
    const netRate = thermal.net_heat_rate ?? (heatGen - heatRad - heatSinkDumped);
    const netClass = netRate > 0 ? "positive" : netRate < 0 ? "negative" : "zero";

    // Dissipation rate in watts
    const dissipation = heatRad;

    // Radiator area in m-squared
    const radArea = thermal.radiator_area ?? 0;
    const radFactor = thermal.radiator_factor ?? 1;
    const radEffective = thermal.radiator_effective_area ?? (radArea * radFactor);

    // Coolant level
    const coolantLevel = thermal.coolant_level ?? thermal.heat_sink_remaining ?? 0;
    const coolantMax = thermal.coolant_capacity ?? thermal.heat_sink_capacity ?? 0;
    const coolantPercent = coolantMax > 0 ? (coolantLevel / coolantMax) * 100 : 0;

    // Heat sink
    const sinkRemaining = thermal.heat_sink_remaining ?? 0;
    const sinkCapacity = thermal.heat_sink_capacity ?? 0;
    const sinkActive = thermal.heat_sink_active ?? false;
    const sinkPercent = sinkCapacity > 0 ? (sinkRemaining / sinkCapacity) * 100 : 0;
    const sinkBarClass = sinkPercent > 50 ? "nominal" : sinkPercent > 20 ? "warning" : "critical";

    content.innerHTML = `
      <!-- Temperature headline -->
      <div class="temp-headline">
        <div>
          <span class="temp-value ${statusClass}">${hullTemp.toFixed(1)}</span>
          <span class="temp-unit">K</span>
        </div>
        <span class="status-badge ${statusClass}">${this._statusLabel(status, thermal)}</span>
      </div>

      <!-- Temperature bar -->
      <div class="temp-bar-container">
        <div class="temp-bar-labels">
          <span>0 K</span>
          <span>${maxTemp.toFixed(0)} K</span>
        </div>
        <div class="temp-bar">
          <div class="temp-bar-fill" style="width: ${Math.min(percent, 100)}%; background: ${barColor};"></div>
          <div class="temp-bar-marker" style="left: ${warnMarkerPct}%;" title="Warning: ${warnTemp} K"></div>
        </div>
      </div>

      <!-- Heat balance section -->
      <div class="section">
        <div class="section-title">Heat Balance</div>
        <div class="detail-row">
          <span class="detail-label">Generated</span>
          <span class="detail-value">${this._formatWatts(heatGen)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Dissipation</span>
          <span class="detail-value">${this._formatWatts(dissipation)}</span>
        </div>
        ${heatSinkDumped > 0 ? `
        <div class="detail-row">
          <span class="detail-label">Sink Dumped</span>
          <span class="detail-value">${this._formatWatts(heatSinkDumped)}</span>
        </div>
        ` : ""}
        <div class="heat-balance">
          <span class="heat-balance-label">Net Heat Rate</span>
          <span class="heat-balance-value ${netClass}">${netRate >= 0 ? "+" : ""}${this._formatWatts(netRate)}</span>
        </div>
      </div>

      <!-- Radiator section -->
      <div class="section">
        <div class="section-title">Radiators</div>
        <div class="detail-row">
          <span class="detail-label">Area</span>
          <span class="detail-value">${radArea.toFixed(1)} m\u00B2</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Effectiveness</span>
          <span class="detail-value ${radFactor < 0.5 ? 'warning' : ''}">${(radFactor * 100).toFixed(0)}%</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Effective Area</span>
          <span class="detail-value">${radEffective.toFixed(1)} m\u00B2</span>
        </div>
      </div>

      <!-- Coolant level -->
      <div class="section">
        <div class="section-title">Coolant</div>
        <div class="detail-row">
          <span class="detail-label">Level</span>
          <span class="detail-value ${coolantPercent < 20 ? 'warning' : ''}">${this._formatJoules(coolantLevel)} / ${this._formatJoules(coolantMax)}</span>
        </div>
        <div class="sink-bar">
          <div class="sink-bar-fill ${coolantPercent > 50 ? 'nominal' : coolantPercent > 20 ? 'warning' : 'critical'}" style="width: ${coolantPercent}%"></div>
        </div>
      </div>

      <!-- Heat sink section -->
      <div class="section">
        <div class="section-title">Heat Sink</div>
        <div class="detail-row">
          <span class="detail-label">
            <span class="active-dot ${sinkActive ? 'on' : 'off'}"></span>
            Status
          </span>
          <span class="detail-value ${sinkActive ? '' : 'zero'}">${sinkActive ? "ACTIVE" : "STANDBY"}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Remaining</span>
          <span class="detail-value ${sinkBarClass}">${this._formatJoules(sinkRemaining)} / ${this._formatJoules(sinkCapacity)}</span>
        </div>
        <div class="sink-bar">
          <div class="sink-bar-fill ${sinkBarClass}" style="width: ${sinkPercent}%"></div>
        </div>
      </div>
    `;
  }

  // =========================================================================
  // ARCADE: Simplified thermal view with % and countdown
  // =========================================================================
  _renderArcade(content, thermal) {
    const hullTemp = thermal.hull_temperature ?? 0;
    const maxTemp = thermal.max_temperature ?? 500;
    const warnTemp = thermal.warning_temperature ?? 400;
    const nominalTemp = thermal.nominal_temperature ?? 300;
    const status = (thermal.status || "nominal").toLowerCase();
    const statusClass = this._statusClass(status, thermal);

    // Temperature as % of thermal limit
    const tempPercent = maxTemp > 0 ? (hullTemp / maxTemp) * 100 : 0;
    const barColor = this._tempBarColor(hullTemp, nominalTemp, warnTemp, maxTemp);

    // Net heat rate for "time to overheat" calculation
    const netRate = thermal.net_heat_rate ?? 0;
    const tempRising = netRate > 0;
    // Approximate seconds to overheat if temperature is rising
    // netRate is typically in internal units; use temperature percent delta as proxy
    let timeToOverheat = Infinity;
    if (tempRising && hullTemp < maxTemp && netRate > 0) {
      // Use a rough estimate: net_heat_rate drives temp change proportionally
      // We compute the remaining temperature gap in Kelvin and divide by the
      // net rate (which is effectively kelvin-per-second when thermal mass is 1)
      const tempGap = maxTemp - hullTemp;
      timeToOverheat = tempGap / (netRate * 0.001 || 0.01);
    }

    // Radiator status
    const eng = stateManager.getShipState()?.engineering || {};
    const radDeployed = eng.radiators_deployed ?? true;
    const radFactor = thermal.radiator_factor ?? 1;
    const radEffPct = (radFactor * 100).toFixed(0);

    content.innerHTML = `
      <!-- Temperature headline -->
      <div class="temp-headline">
        <div>
          <span class="temp-value ${statusClass}">${tempPercent.toFixed(0)}</span>
          <span class="temp-unit">%</span>
        </div>
        <span class="status-badge ${statusClass}">${this._statusLabel(status, thermal)}</span>
      </div>

      <!-- Temperature bar -->
      <div class="temp-bar-container">
        <div class="temp-bar-labels">
          <span>0%</span>
          <span>100%</span>
        </div>
        <div class="temp-bar">
          <div class="temp-bar-fill" style="width: ${Math.min(tempPercent, 100)}%; background: ${barColor};"></div>
        </div>
      </div>

      ${tempRising && isFinite(timeToOverheat) && timeToOverheat < 600 ? `
      <!-- Time to overheat countdown -->
      <div class="section">
        <div class="section-title">Time to Overheat</div>
        <div class="detail-row">
          <span class="detail-label">ETA</span>
          <span class="detail-value ${timeToOverheat < 60 ? 'positive' : 'warning'}">${this._formatTime(timeToOverheat)}</span>
        </div>
      </div>
      ` : ""}

      <!-- Radiator status (simplified) -->
      <div class="section">
        <div class="section-title">Radiators</div>
        <div class="rad-status-row">
          <span class="rad-status-label">Status</span>
          <span class="rad-status-value" style="color: ${radDeployed ? 'var(--status-nominal, #00ff88)' : 'var(--status-warning, #ffaa00)'}">
            ${radDeployed ? "DEPLOYED" : "RETRACTED"}
          </span>
        </div>
        <div class="rad-status-row">
          <span class="rad-status-label">Efficiency</span>
          <span class="rad-status-value ${radFactor < 0.5 ? 'warning' : ''}" style="color: var(--text-primary, #e0e0e0)">${radEffPct}%</span>
        </div>
      </div>
    `;
  }

  // =========================================================================
  // CPU-ASSIST: Thermal summary badge with auto-recommendations
  // =========================================================================
  _renderCpuAssist(content, thermal) {
    const hullTemp = thermal.hull_temperature ?? 0;
    const maxTemp = thermal.max_temperature ?? 500;
    const warnTemp = thermal.warning_temperature ?? 400;
    const status = (thermal.status || "nominal").toLowerCase();
    const netRate = thermal.net_heat_rate ?? 0;
    const tempPercent = maxTemp > 0 ? (hullTemp / maxTemp) * 100 : 0;

    // Determine badge level
    let badgeLevel, badgeLabel;
    if (thermal.is_emergency || hullTemp >= maxTemp * 0.95) {
      badgeLevel = "critical";
      badgeLabel = "CRITICAL";
    } else if (thermal.is_overheating || hullTemp >= warnTemp) {
      badgeLevel = "warning";
      badgeLabel = "WARNING";
    } else {
      badgeLevel = "nominal";
      badgeLabel = "NOMINAL";
    }

    // Radiator info for recommendations
    const eng = stateManager.getShipState()?.engineering || {};
    const radDeployed = eng.radiators_deployed ?? true;
    const reactorOutput = eng.reactor_percent ?? ((eng.reactor_output ?? 1.0) * 100);

    // Build recommendation list
    const recommendations = [];
    if (badgeLevel === "critical" && !radDeployed) {
      recommendations.push({ type: "action", text: "Deploy radiators immediately" });
    } else if (badgeLevel === "warning" && !radDeployed) {
      recommendations.push({ type: "action", text: "Deploy radiators" });
    }
    if (badgeLevel !== "nominal" && reactorOutput > 80) {
      recommendations.push({ type: "action", text: "Reduce reactor output" });
    }
    if (badgeLevel === "nominal" && netRate < 0) {
      recommendations.push({ type: "info", text: "Thermal balance stable" });
    }
    if (badgeLevel === "nominal" && netRate >= 0 && netRate < 10) {
      recommendations.push({ type: "info", text: "Heat generation near equilibrium" });
    }

    let recsHtml = "";
    recommendations.forEach(r => {
      const icon = r.type === "action" ? "!" : "i";
      recsHtml += `
        <div class="recommendation ${r.type}">
          <span class="rec-icon">${icon}</span>
          <span>${r.text}</span>
        </div>
      `;
    });

    content.innerHTML = `
      <!-- Hero badge -->
      <div class="thermal-hero-badge ${badgeLevel}">
        <span class="hero-badge-label ${badgeLevel}">${badgeLabel}</span>
        <span class="hero-badge-sub">${tempPercent.toFixed(0)}% thermal load</span>
      </div>

      ${recsHtml}
    `;
  }

  // =========================================================================
  // Helpers (shared across tiers)
  // =========================================================================

  _statusClass(status, thermal) {
    if (thermal.is_emergency) return "critical";
    if (thermal.is_overheating) return "warning";
    if (status === "elevated") return "elevated";
    return "nominal";
  }

  _statusLabel(status, thermal) {
    if (thermal.is_emergency) return "EMERGENCY";
    if (thermal.is_overheating) return "WARNING";
    if (status === "elevated") return "ELEVATED";
    return "NOMINAL";
  }

  /**
   * Compute a CSS color string for the temperature bar fill.
   * Cold (below nominal): blue-cyan
   * Nominal zone: green
   * Warning zone: yellow-orange
   * Emergency zone: red
   */
  _tempBarColor(temp, nominal, warning, max) {
    if (temp <= nominal) {
      const t = nominal > 0 ? Math.max(0, temp / nominal) : 0;
      const r = Math.round(0 * (1 - t) + 0 * t);
      const g = Math.round(120 * (1 - t) + 255 * t);
      const b = Math.round(255 * (1 - t) + 136 * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else if (temp <= warning) {
      const t = (temp - nominal) / (warning - nominal || 1);
      const r = Math.round(0 + 255 * t);
      const g = Math.round(255 - 85 * t);
      const b = Math.round(136 * (1 - t));
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const t = Math.min(1, (temp - warning) / (max - warning || 1));
      const r = 255;
      const g = Math.round(170 * (1 - t));
      const b = Math.round(0);
      return `rgb(${r}, ${g}, ${b})`;
    }
  }

  _formatWatts(w) {
    const abs = Math.abs(w);
    const sign = w < 0 ? "-" : "";
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)} MW`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)} kW`;
    return `${sign}${abs.toFixed(0)} W`;
  }

  _formatJoules(j) {
    const abs = Math.abs(j);
    if (abs >= 1e6) return `${(j / 1e6).toFixed(1)} MJ`;
    if (abs >= 1e3) return `${(j / 1e3).toFixed(1)} kJ`;
    return `${j.toFixed(0)} J`;
  }

  _formatTime(seconds) {
    if (!isFinite(seconds) || seconds <= 0) return "--:--";
    if (seconds >= 3600) {
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      return `${h}h ${m.toString().padStart(2, "0")}m`;
    }
    if (seconds >= 60) {
      const m = Math.floor(seconds / 60);
      const s = Math.floor(seconds % 60);
      return `${m}m ${s.toString().padStart(2, "0")}s`;
    }
    return seconds.toFixed(0) + "s";
  }
}

customElements.define("thermal-display", ThermalDisplay);
export { ThermalDisplay };
