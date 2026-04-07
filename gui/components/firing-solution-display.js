/**
 * Firing Solution Display
 *
 * Shows the detailed confidence breakdown for firing solutions,
 * including the five physical factors that compose confidence and
 * a visual confidence cone showing the dispersion area at target range.
 *
 * Also displays causal combat feedback from projectile impacts —
 * the player always knows WHY a slug hit or missed.
 */

import { stateManager } from "../js/state-manager.js";

class FiringSolutionDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._feedbackLog = []; // Ring buffer of causal feedback messages
    this._maxFeedback = 20;
    this._tier = window.controlTier || "arcade";
  }

  connectedCallback() {
    this.render();
    this._subscribe();

    // Tier-change listener: re-render for tier-specific solution display
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._updateDisplay();
    };
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("targeting", () => {
      this._checkForFeedback();
      this._updateDisplay();
    });
  }

  _checkForFeedback() {
    // Check recent events for projectile_impact feedback
    const state = stateManager.getState();
    const events = state?.events || [];
    for (const event of events) {
      if (event.type === "projectile_impact" && event.feedback) {
        const id = event.projectile_id;
        if (!this._feedbackLog.some((f) => f.id === id)) {
          this._feedbackLog.unshift({
            id,
            feedback: event.feedback,
            hit: event.hit,
            time: event.sim_time,
            confidence: event.confidence_at_fire,
          });
          if (this._feedbackLog.length > this._maxFeedback) {
            this._feedbackLog.pop();
          }
        }
      }
      if (event.type === "projectile_expired" && event.feedback) {
        const id = event.projectile_id;
        if (!this._feedbackLog.some((f) => f.id === id)) {
          this._feedbackLog.unshift({
            id,
            feedback: event.feedback,
            hit: false,
            time: 0,
            confidence: event.confidence_at_fire,
          });
          if (this._feedbackLog.length > this._maxFeedback) {
            this._feedbackLog.pop();
          }
        }
      }
    }
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

        .no-solution {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        /* Confidence cone visualisation */
        .cone-container {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 16px;
          margin-bottom: 16px;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 8px;
        }

        .cone-svg {
          max-width: 200px;
          max-height: 120px;
        }

        .cone-stats {
          display: flex;
          justify-content: space-around;
          margin-bottom: 16px;
        }

        .cone-stat {
          text-align: center;
        }

        .cone-stat-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1rem;
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        .cone-stat-value.high { color: var(--status-nominal, #00ff88); }
        .cone-stat-value.mid { color: var(--status-warning, #ffaa00); }
        .cone-stat-value.low { color: var(--status-critical, #ff4444); }

        .cone-stat-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-top: 2px;
        }

        /* Factor breakdown bars */
        .factor-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-bottom: 16px;
        }

        .factor-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .factor-label {
          flex: 0 0 90px;
          font-size: 0.65rem;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
        }

        .factor-bar-bg {
          flex: 1;
          height: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
        }

        .factor-bar-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s ease;
        }

        .factor-bar-fill.high { background: var(--status-nominal, #00ff88); }
        .factor-bar-fill.mid { background: var(--status-warning, #ffaa00); }
        .factor-bar-fill.low { background: var(--status-critical, #ff4444); }

        .factor-value {
          flex: 0 0 32px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          color: var(--text-primary, #e0e0e0);
          text-align: right;
        }

        /* Combat feedback log */
        .feedback-section {
          margin-top: 16px;
          border-top: 1px solid var(--border-default, #2a2a3a);
          padding-top: 12px;
        }

        .feedback-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
          max-height: 200px;
          overflow-y: auto;
        }

        .feedback-entry {
          padding: 8px 10px;
          border-radius: 6px;
          font-size: 0.72rem;
          line-height: 1.4;
          border-left: 3px solid;
        }

        .feedback-entry.hit {
          background: rgba(0, 255, 136, 0.06);
          border-color: var(--status-nominal, #00ff88);
          color: var(--text-primary, #e0e0e0);
        }

        .feedback-entry.miss {
          background: rgba(255, 170, 0, 0.06);
          border-color: var(--status-warning, #ffaa00);
          color: var(--text-secondary, #888899);
        }

        .feedback-tag {
          display: inline-block;
          font-size: 0.6rem;
          font-weight: 700;
          text-transform: uppercase;
          padding: 1px 5px;
          border-radius: 3px;
          margin-right: 6px;
        }

        .feedback-tag.hit {
          background: rgba(0, 255, 136, 0.2);
          color: var(--status-nominal, #00ff88);
        }

        .feedback-tag.miss {
          background: rgba(255, 170, 0, 0.2);
          color: var(--status-warning, #ffaa00);
        }

        /* === MANUAL tier: raw deflection numbers === */
        .manual-solution-grid {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 3px 12px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 4px;
          margin-bottom: 12px;
        }
        .manual-solution-grid .ms-label {
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          font-size: 0.65rem;
          letter-spacing: 0.5px;
        }
        .manual-solution-grid .ms-value {
          color: var(--text-primary, #e0e0e0);
          text-align: right;
        }

        /* === ARCADE tier: simplified confidence bar === */
        .arcade-conf-bar {
          padding: 12px;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 8px;
          margin-bottom: 12px;
        }
        .arcade-conf-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 6px;
        }
        .arcade-conf-label {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: var(--text-secondary, #888899);
        }
        .arcade-conf-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.2rem;
          font-weight: 700;
        }
        .arcade-conf-value.high { color: var(--status-nominal, #00ff88); }
        .arcade-conf-value.mid { color: var(--status-warning, #ffaa00); }
        .arcade-conf-value.low { color: var(--status-critical, #ff4444); }
        .arcade-range-row {
          display: flex;
          justify-content: space-around;
          margin-top: 8px;
          font-size: 0.75rem;
        }
        .arcade-range-item {
          text-align: center;
        }
        .arcade-range-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }
        .arcade-range-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }
        .arcade-ready-chip {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 10px;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          margin-bottom: 12px;
        }
        .arcade-ready-chip.ready {
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }
        .arcade-ready-chip.not-ready {
          background: rgba(85, 85, 102, 0.1);
          border: 1px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }

        /* === CPU-ASSIST tier: minimal indicator === */
        .cpuassist-status {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          padding: 16px;
          border-radius: 8px;
          font-size: 1rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1.5px;
        }
        .cpuassist-status.valid {
          background: rgba(0, 255, 136, 0.08);
          border: 2px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }
        .cpuassist-status.invalid {
          background: rgba(85, 85, 102, 0.1);
          border: 2px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }
        .cpuassist-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: currentColor;
        }
        .cpuassist-status.valid .cpuassist-dot {
          animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      </style>

      <div id="content">
        <div class="no-solution">Waiting for firing solution data...</div>
      </div>
    `;
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    const lockState = targeting?.lock_state || "none";
    const tier = this._tier;

    if (lockState !== "locked") {
      // Show feedback log even without a lock
      if (this._feedbackLog.length > 0) {
        content.innerHTML = `
          <div class="no-solution">No active firing solution</div>
          ${this._renderFeedbackSection()}
        `;
      } else {
        content.innerHTML = '<div class="no-solution">No active firing solution</div>';
      }
      return;
    }

    // Find the best solution across weapons
    const solutions = targeting?.solutions || {};
    let bestSol = null;
    let bestWeaponId = null;

    for (const [wid, sol] of Object.entries(solutions)) {
      if (sol.confidence != null) {
        if (!bestSol || sol.confidence > bestSol.confidence) {
          bestSol = sol;
          bestWeaponId = wid;
        }
      }
    }

    if (!bestSol) {
      content.innerHTML = `
        <div class="no-solution">Computing firing solution...</div>
        ${this._renderFeedbackSection()}
      `;
      return;
    }

    let html = "";
    const confPct = Math.round((bestSol.confidence || 0) * 100);
    const confClass = confPct > 70 ? "high" : confPct > 40 ? "mid" : "low";

    // --- MANUAL tier: full physics diagnostics — every intermediate value ---
    if (tier === "manual") {
      const tof = bestSol.time_of_flight ?? 0;
      const rangeM = bestSol.range ?? bestSol.range_m ?? 0;
      const closing = bestSol.closing_speed ?? bestSol.closing_rate ?? 0;
      const lead = bestSol.lead_angle || {};
      const intercept = bestSol.intercept_point || {};
      const tgtAccel = bestSol.target_accel_magnitude ?? 0;
      const latVel = bestSol.lateral_velocity ?? 0;
      const cf = bestSol.confidence_factors || {};
      const hitProb = bestSol.hit_probability ?? 0;

      html += `
        <div class="section-title">ENGAGEMENT GEOMETRY</div>
        <div class="manual-solution-grid" data-testid="manual-solution">
          <span class="ms-label">RANGE</span>
          <span class="ms-value">${rangeM.toFixed(0)} m</span>
          <span class="ms-label">CLOSING</span>
          <span class="ms-value">${closing.toFixed(1)} m/s</span>
          <span class="ms-label">LEAD YAW</span>
          <span class="ms-value">${(lead.yaw ?? 0).toFixed(3)}°</span>
          <span class="ms-label">LEAD PITCH</span>
          <span class="ms-value">${(lead.pitch ?? 0).toFixed(3)}°</span>
          <span class="ms-label">TOF</span>
          <span class="ms-value">${tof.toFixed(3)} s</span>
          <span class="ms-label">INTERCEPT X</span>
          <span class="ms-value">${(intercept.x ?? 0).toFixed(0)} m</span>
          <span class="ms-label">INTERCEPT Y</span>
          <span class="ms-value">${(intercept.y ?? 0).toFixed(0)} m</span>
          <span class="ms-label">INTERCEPT Z</span>
          <span class="ms-value">${(intercept.z ?? 0).toFixed(0)} m</span>
          <span class="ms-label">TGT ACCEL</span>
          <span class="ms-value">${tgtAccel.toFixed(2)} m/s²</span>
          <span class="ms-label">LATERAL VEL</span>
          <span class="ms-value">${latVel.toFixed(1)} m/s</span>
          <span class="ms-label">IN ARC</span>
          <span class="ms-value">${bestSol.in_arc === false ? 'NO' : bestSol.in_arc === true ? 'YES' : '---'}</span>
          <span class="ms-label">IN RANGE</span>
          <span class="ms-value">${bestSol.in_range === false ? 'NO' : bestSol.in_range === true ? 'YES' : '---'}</span>
        </div>

        <div class="section-title">CONFIDENCE FACTORS</div>
        <div class="factor-list">
          ${this._renderFactorRow("TRACK QUALITY", cf.track_quality)}
          ${this._renderFactorRow("RANGE FACTOR", cf.range_factor)}
          ${this._renderFactorRow("TGT ACCEL", cf.target_accel)}
          ${this._renderFactorRow("OWN ROTATION", cf.own_rotation)}
          ${this._renderFactorRow("WEAPON HEALTH", cf.weapon_health)}
          ${this._renderFactorRow("TIME OF FLIGHT", cf.time_of_flight)}
        </div>

        <div class="section-title">DISPERSION</div>
        <div class="manual-solution-grid">
          <span class="ms-label">CONE ANGLE</span>
          <span class="ms-value">${(bestSol.cone_angle_deg || 0).toFixed(3)}°</span>
          <span class="ms-label">CONE RADIUS</span>
          <span class="ms-value">${(bestSol.cone_radius_m || 0).toFixed(0)} m</span>
          <span class="ms-label">HIT PROB</span>
          <span class="ms-value">${(hitProb * 100).toFixed(1)}%</span>
          <span class="ms-label">CONFIDENCE</span>
          <span class="ms-value">${(bestSol.confidence || 0).toFixed(4)}</span>
        </div>
      `;
      html += this._renderFeedbackSection();
      content.innerHTML = html;
      return;
    }

    // --- ARCADE tier: single confidence bar + READY indicator, range in km ---
    if (tier === "arcade") {
      const isReady = confPct > 50;
      const rangeKm = (bestSol.range_m ?? 0) / 1000;
      const closingKmS = Math.abs(bestSol.closing_rate ?? 0) / 1000;

      html += `
        <div class="arcade-ready-chip ${isReady ? 'ready' : 'not-ready'}">
          ${isReady ? 'READY' : 'COMPUTING'}
        </div>
        <div class="arcade-conf-bar">
          <div class="arcade-conf-header">
            <span class="arcade-conf-label">SOLUTION CONFIDENCE</span>
            <span class="arcade-conf-value ${confClass}">${confPct}%</span>
          </div>
          <div class="factor-bar-bg" style="height:12px; border-radius:6px;">
            <div class="factor-bar-fill ${confClass}" style="width:${confPct}%; height:100%; border-radius:6px;"></div>
          </div>
        </div>
        <div class="arcade-range-row">
          <div class="arcade-range-item">
            <div class="arcade-range-value">${rangeKm.toFixed(1)} km</div>
            <div class="arcade-range-label">Range</div>
          </div>
          <div class="arcade-range-item">
            <div class="arcade-range-value">${closingKmS.toFixed(1)} km/s</div>
            <div class="arcade-range-label">Closure</div>
          </div>
        </div>
      `;

      // Arc warning
      if (bestSol.in_arc === false) {
        const reason = bestSol.reason || "Target outside firing arc";
        html += `
          <div data-testid="arc-warning" style="
            background: rgba(255, 68, 68, 0.1);
            border: 1px solid var(--status-critical, #ff4444);
            border-radius: 6px;
            padding: 8px 12px;
            margin-top: 12px;
            text-align: center;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--status-critical, #ff4444);
            text-transform: uppercase;
          ">${reason}</div>
        `;
      }

      html += this._renderFeedbackSection();
      content.innerHTML = html;
      return;
    }

    // --- CPU-ASSIST tier: minimal "SOLUTION VALID" / "NO SOLUTION" indicator ---
    if (tier === "cpu-assist") {
      const isValid = confPct > 30;
      html += `
        <div class="cpuassist-status ${isValid ? 'valid' : 'invalid'}">
          <div class="cpuassist-dot"></div>
          ${isValid ? 'SOLUTION VALID' : 'NO SOLUTION'}
        </div>
      `;
      html += this._renderFeedbackSection();
      content.innerHTML = html;
      return;
    }

    // --- RAW tier (default): full factor breakdown table with exact values ---

    // 1. Confidence cone SVG
    html += this._renderCone(bestSol);

    // 2. Cone stats row
    const coneRadius = bestSol.cone_radius_m || 0;
    const coneAngle = bestSol.cone_angle_deg || 0;

    html += `
      <div class="cone-stats" data-testid="cone-stats">
        <div class="cone-stat">
          <div class="cone-stat-value ${confClass}">${confPct}%</div>
          <div class="cone-stat-label">Confidence</div>
        </div>
        <div class="cone-stat">
          <div class="cone-stat-value">${this._formatConeRadius(coneRadius)}</div>
          <div class="cone-stat-label">Cone Radius</div>
        </div>
        <div class="cone-stat">
          <div class="cone-stat-value">${coneAngle.toFixed(1)}&deg;</div>
          <div class="cone-stat-label">Spread</div>
        </div>
      </div>
    `;

    // 2b. Firing arc warning
    if (bestSol.in_arc === false) {
      const reason = bestSol.reason || "Target outside firing arc";
      html += `
        <div data-testid="arc-warning" style="
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid var(--status-critical, #ff4444);
          border-radius: 6px;
          padding: 8px 12px;
          margin-bottom: 12px;
          text-align: center;
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--status-critical, #ff4444);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        ">${reason}</div>
      `;
    }

    // 3. Factor breakdown — RAW shows exact values per factor
    const factors = bestSol.confidence_factors;
    if (factors && Object.keys(factors).length > 0) {
      html += `<div class="section-title">Confidence Factors</div>`;
      html += `<div class="factor-list" data-testid="confidence-factors">`;

      const factorLabels = {
        track_quality: "Track",
        range_factor: "Range",
        target_accel: "Tgt Accel",
        own_rotation: "Ship Stab",
        weapon_health: "Wpn Health",
        time_of_flight: "ToF",
      };

      for (const [key, label] of Object.entries(factorLabels)) {
        const val = factors[key] ?? 0;
        const pct = Math.round(val * 100);
        const barClass = pct > 70 ? "high" : pct > 40 ? "mid" : "low";

        html += `
          <div class="factor-row" data-factor="${key}">
            <span class="factor-label">${label}</span>
            <div class="factor-bar-bg">
              <div class="factor-bar-fill ${barClass}" style="width: ${pct}%"></div>
            </div>
            <span class="factor-value">${pct}%</span>
          </div>
        `;
      }

      html += `</div>`;
    }

    // 4. Combat feedback log
    html += this._renderFeedbackSection();

    content.innerHTML = html;
  }

  _renderFactorRow(label, value) {
    const val = value ?? 0;
    const pct = Math.round(val * 100);
    const barClass = pct > 70 ? "high" : pct > 40 ? "mid" : "low";
    return `
      <div class="factor-row">
        <span class="factor-label">${label}</span>
        <div class="factor-bar-bg">
          <div class="factor-bar-fill ${barClass}" style="width:${pct}%"></div>
        </div>
        <span class="factor-value">${val.toFixed(3)}</span>
      </div>
    `;
  }

  _renderCone(sol) {
    const confidence = sol.confidence || 0;
    const coneAngle = sol.cone_angle_deg || 0;

    // SVG cone: narrow cone = high confidence, wide = low
    // Angle is half-angle, so full cone opening = 2 * coneAngle
    const svgW = 200;
    const svgH = 100;
    const originX = 10;
    const originY = svgH / 2;
    const endX = svgW - 10;
    const halfSpread = Math.min(coneAngle, 15); // Cap visual at 15 degrees

    // Y offset at the end based on angle (visual exaggeration for small angles)
    const yOffset = Math.max(3, (halfSpread / 15) * (svgH / 2 - 5));

    // Colour based on confidence
    let strokeColor, fillColor;
    if (confidence > 0.7) {
      strokeColor = "#00ff88";
      fillColor = "rgba(0, 255, 136, 0.12)";
    } else if (confidence > 0.4) {
      strokeColor = "#ffaa00";
      fillColor = "rgba(255, 170, 0, 0.1)";
    } else {
      strokeColor = "#ff4444";
      fillColor = "rgba(255, 68, 68, 0.1)";
    }

    // Center dot (target area)
    const targetDotR = Math.max(2, 6 - halfSpread * 0.3);

    return `
      <div class="cone-container" data-testid="confidence-cone">
        <svg class="cone-svg" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">
          <!-- Cone body -->
          <polygon
            points="${originX},${originY} ${endX},${originY - yOffset} ${endX},${originY + yOffset}"
            fill="${fillColor}"
            stroke="${strokeColor}"
            stroke-width="1"
            opacity="0.8"
          />
          <!-- Center line (aim axis) -->
          <line
            x1="${originX}" y1="${originY}"
            x2="${endX}" y2="${originY}"
            stroke="${strokeColor}"
            stroke-width="0.5"
            stroke-dasharray="4,3"
            opacity="0.5"
          />
          <!-- Origin dot (weapon) -->
          <circle cx="${originX}" cy="${originY}" r="3"
            fill="${strokeColor}" />
          <!-- Target area circle -->
          <circle cx="${endX}" cy="${originY}" r="${targetDotR}"
            fill="none" stroke="${strokeColor}" stroke-width="1.5" />
          <!-- Dispersion arc at target end -->
          <line
            x1="${endX}" y1="${originY - yOffset}"
            x2="${endX}" y2="${originY + yOffset}"
            stroke="${strokeColor}"
            stroke-width="1.5"
            opacity="0.6"
          />
        </svg>
      </div>
    `;
  }

  _renderFeedbackSection() {
    if (this._feedbackLog.length === 0) return "";

    let html = `
      <div class="feedback-section">
        <div class="section-title">Combat Feedback</div>
        <div class="feedback-list" data-testid="combat-feedback">
    `;

    for (const entry of this._feedbackLog) {
      const hitClass = entry.hit ? "hit" : "miss";
      const tagText = entry.hit ? "HIT" : "MISS";

      html += `
        <div class="feedback-entry ${hitClass}">
          <span class="feedback-tag ${hitClass}">${tagText}</span>
          ${entry.feedback}
        </div>
      `;
    }

    html += `</div></div>`;
    return html;
  }

  _formatConeRadius(meters) {
    if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
    return `${meters.toFixed(0)} m`;
  }
}

customElements.define("firing-solution-display", FiringSolutionDisplay);
export { FiringSolutionDisplay };
