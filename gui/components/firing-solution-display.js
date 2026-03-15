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

    // 1. Confidence cone SVG
    html += this._renderCone(bestSol);

    // 2. Cone stats row
    const confPct = Math.round((bestSol.confidence || 0) * 100);
    const confClass = confPct > 70 ? "high" : confPct > 40 ? "mid" : "low";
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

    // 3. Factor breakdown
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
