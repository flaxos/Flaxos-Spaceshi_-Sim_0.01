/**
 * Targeting Computer Display
 * Shows target lock status, firing solution, TCA/CPA
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class TargetingDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._contactSelectedHandler = null;
    this._solutionData = null;
    this._solutionInterval = null;
    this._wasLocked = false;
  }

  connectedCallback() {
    this.render();
    this._subscribe();

    // Listen for contact selection from sensor panel
    this._contactSelectedHandler = (e) => {
      this._onContactSelected(e.detail.contactId);
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    if (this._contactSelectedHandler) {
      document.removeEventListener("contact-selected", this._contactSelectedHandler);
      this._contactSelectedHandler = null;
    }
    this._stopSolutionPolling();
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  _onContactSelected(contactId) {
    // Highlight selected but don't auto-lock
    this._selectedContact = contactId;
    this._updateDisplay();
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

        .no-lock {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px;
          color: var(--text-dim, #555566);
        }

        .no-lock-icon {
          font-size: 2rem;
          margin-bottom: 8px;
          opacity: 0.5;
        }

        .no-lock-text {
          font-size: 0.9rem;
          margin-bottom: 8px;
        }

        .no-lock-hint {
          font-size: 0.7rem;
          font-style: italic;
        }

        .locked-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 8px;
          margin-bottom: 16px;
        }

        .lock-indicator {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: var(--status-info, #00aaff);
          box-shadow: 0 0 12px var(--status-info, #00aaff);
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 12px var(--status-info, #00aaff); }
          50% { opacity: 0.7; box-shadow: 0 0 6px var(--status-info, #00aaff); }
        }

        .lock-text {
          font-weight: 600;
          color: var(--status-info, #00aaff);
        }

        .target-id {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
        }

        .target-details {
          display: grid;
          gap: 8px;
          margin-bottom: 16px;
        }

        .detail-row {
          display: flex;
          justify-content: space-between;
          padding: 4px 0;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .detail-row:last-child {
          border-bottom: none;
        }

        .detail-label {
          color: var(--text-secondary, #888899);
          font-size: 0.75rem;
        }

        .detail-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
        }

        .closure-value.closing {
          color: var(--status-critical, #ff4444);
        }

        .closure-value.opening {
          color: var(--status-nominal, #00ff88);
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .solution-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-bottom: 16px;
        }

        .solution-item {
          text-align: center;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }

        .solution-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.1rem;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 4px;
        }

        .solution-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .lock-quality {
          margin-bottom: 12px;
        }

        .lock-bar {
          height: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 6px;
          overflow: hidden;
          margin-top: 8px;
        }

        .lock-fill {
          height: 100%;
          background: var(--status-info, #00aaff);
          transition: width 0.3s ease;
        }

        .lock-fill.strong {
          background: var(--status-nominal, #00ff88);
        }

        .lock-fill.weak {
          background: var(--status-warning, #ffaa00);
        }

        .warning-box {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 12px;
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid var(--status-critical, #ff4444);
          border-radius: 6px;
          color: var(--status-critical, #ff4444);
          font-size: 0.8rem;
          margin-top: 12px;
        }

        .warning-icon {
          font-size: 1rem;
        }

        /* Firing solution breakdown */
        .solution-section {
          margin-top: 16px;
        }

        .solution-quality-badge {
          display: inline-block;
          padding: 4px 10px;
          border-radius: 4px;
          font-size: 0.7rem;
          font-weight: 700;
          letter-spacing: 0.5px;
          text-transform: uppercase;
          margin-bottom: 12px;
        }

        .solution-quality-badge.good {
          background: rgba(0, 255, 136, 0.15);
          border: 1px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .solution-quality-badge.good.valid-pulse {
          animation: solution-pulse 2s ease-in-out infinite;
        }

        .solution-quality-badge.marginal {
          background: rgba(255, 170, 0, 0.15);
          border: 1px solid var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .solution-quality-badge.none {
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        @keyframes solution-pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 8px rgba(0, 255, 136, 0.3); }
          50% { opacity: 0.8; box-shadow: 0 0 16px rgba(0, 255, 136, 0.5); }
        }

        .confidence-bar-container {
          margin-bottom: 12px;
        }

        .confidence-bar {
          height: 16px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          overflow: hidden;
          margin-top: 6px;
          position: relative;
        }

        .confidence-fill {
          height: 100%;
          transition: width 0.3s ease, background 0.3s ease;
          border-radius: 8px;
        }

        .confidence-fill.high { background: var(--status-nominal, #00ff88); }
        .confidence-fill.mid { background: var(--status-warning, #ffaa00); }
        .confidence-fill.low { background: var(--status-critical, #ff4444); }

        .confidence-label {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          color: var(--text-primary, #e0e0e0);
          text-shadow: 0 0 4px rgba(0, 0, 0, 0.8);
        }

        .weapon-solutions {
          display: flex;
          flex-direction: column;
          gap: 10px;
          margin-top: 12px;
        }

        .weapon-card {
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
        }

        .weapon-card.ready {
          border-color: var(--status-nominal, #00ff88);
        }

        .weapon-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .weapon-name {
          font-weight: 600;
          font-size: 0.75rem;
          text-transform: uppercase;
          color: var(--text-primary, #e0e0e0);
        }

        .weapon-ready-tag {
          font-size: 0.6rem;
          padding: 2px 6px;
          border-radius: 3px;
          font-weight: 600;
        }

        .weapon-ready-tag.ready {
          background: rgba(0, 255, 136, 0.15);
          color: var(--status-nominal, #00ff88);
        }

        .weapon-ready-tag.not-ready {
          background: rgba(255, 68, 68, 0.1);
          color: var(--status-critical, #ff4444);
        }

        .weapon-stats {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
        }

        .weapon-stat {
          display: flex;
          flex-direction: column;
        }

        .weapon-stat-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .weapon-stat-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
        }

        .weapon-stat-value.high { color: var(--status-nominal, #00ff88); }
        .weapon-stat-value.mid { color: var(--status-warning, #ffaa00); }
        .weapon-stat-value.low { color: var(--status-critical, #ff4444); }

        .subsystem-section {
          margin-top: 16px;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
        }

        .subsystem-target {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .subsystem-name {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--status-info, #00aaff);
          text-transform: uppercase;
        }

        .subsystem-health {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
        }

        .request-solution-btn {
          display: block;
          width: 100%;
          margin-top: 12px;
          padding: 8px;
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 6px;
          color: var(--status-info, #00aaff);
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          transition: background 0.2s ease;
        }

        .request-solution-btn:hover {
          background: rgba(0, 170, 255, 0.2);
        }

        .request-solution-btn:active {
          background: rgba(0, 170, 255, 0.3);
        }
      </style>

      <div id="content">
        <div class="no-lock">
          <div class="no-lock-icon">○</div>
          <div class="no-lock-text">NO TARGET LOCK</div>
          <div class="no-lock-hint">Select a contact from Sensors panel</div>
        </div>
      </div>
    `;
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    // Check for target lock
    const hasLock = targeting && (targeting.locked || targeting.target_locked || targeting.target_id);

    if (!hasLock) {
      // Stop polling when lock is lost
      if (this._wasLocked) {
        this._stopSolutionPolling();
        this._solutionData = null;
        this._wasLocked = false;
      }
      content.innerHTML = `
        <div class="no-lock">
          <div class="no-lock-icon">○</div>
          <div class="no-lock-text">NO TARGET LOCK</div>
          <div class="no-lock-hint">Select a contact from Sensors panel</div>
        </div>
      `;
      return;
    }

    // Start polling for firing solution when lock is first acquired
    if (!this._wasLocked) {
      this._wasLocked = true;
      this._startSolutionPolling();
    }

    // Extract targeting data
    const targetId = targeting.target_id || targeting.id || "???";
    const targetClass = targeting.target_class || targeting.classification || "UNKNOWN";
    const bearing = targeting.bearing ?? "---";
    const range = targeting.range ?? 0;
    const rangeRate = targeting.range_rate ?? targeting.closure ?? 0;
    const tca = targeting.tca ?? targeting.time_to_closest ?? null;
    const cpa = targeting.cpa ?? targeting.closest_approach ?? null;
    const lockQuality = targeting.lock_quality ?? targeting.lock ?? 85;
    const collisionWarning = targeting.collision_warning || targeting.collision || false;

    const closureClass = rangeRate < 0 ? "closing" : rangeRate > 0 ? "opening" : "";
    const closureText = rangeRate < 0 ? "CLOSING" : rangeRate > 0 ? "OPENING" : "STABLE";
    const lockClass = lockQuality > 80 ? "strong" : lockQuality > 50 ? "" : "weak";

    content.innerHTML = `
      <div class="locked-header">
        <div class="lock-indicator"></div>
        <span class="lock-text">TARGET LOCKED:</span>
        <span class="target-id">${targetId}</span>
      </div>

      <div class="target-details">
        <div class="detail-row">
          <span class="detail-label">CLASS</span>
          <span class="detail-value">${targetClass}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">BEARING</span>
          <span class="detail-value">${this._formatBearing(bearing)}°</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">RANGE</span>
          <span class="detail-value">${this._formatRange(range)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">CLOSURE</span>
          <span class="detail-value closure-value ${closureClass}">
            ${Math.abs(rangeRate).toFixed(0)} m/s (${closureText})
          </span>
        </div>
      </div>

      <div class="section-title">Firing Solution</div>
      <div class="solution-grid">
        <div class="solution-item">
          <div class="solution-value">${tca !== null ? tca.toFixed(0) + 's' : '--'}</div>
          <div class="solution-label">TCA</div>
        </div>
        <div class="solution-item">
          <div class="solution-value">${cpa !== null ? this._formatRange(cpa) : '--'}</div>
          <div class="solution-label">CPA</div>
        </div>
      </div>

      <div class="lock-quality">
        <div class="section-title">Lock Quality</div>
        <div class="lock-bar">
          <div class="lock-fill ${lockClass}" style="width: ${lockQuality}%"></div>
        </div>
      </div>

      ${collisionWarning ? `
        <div class="warning-box">
          <span class="warning-icon">⚠</span>
          <span>COLLISION COURSE</span>
        </div>
      ` : ''}

      ${this._renderFiringSolutionSection(targeting)}
      ${this._renderSubsystemSection(targeting)}

      <button class="request-solution-btn" id="request-solution-btn">
        REQUEST SOLUTION UPDATE
      </button>
    `;

    // Bind the manual request button
    const reqBtn = this.shadowRoot.getElementById("request-solution-btn");
    if (reqBtn) {
      reqBtn.addEventListener("click", () => this._requestSolution());
    }
  }

  // -- Firing solution polling --

  _startSolutionPolling() {
    this._stopSolutionPolling();
    // Request an initial solution immediately, then every 1.5s
    this._requestSolution();
    this._solutionInterval = setInterval(() => this._requestSolution(), 1500);
  }

  _stopSolutionPolling() {
    if (this._solutionInterval) {
      clearInterval(this._solutionInterval);
      this._solutionInterval = null;
    }
  }

  async _requestSolution() {
    try {
      const response = await wsClient.sendShipCommand("get_target_solution", {});
      if (response && response.ok) {
        this._solutionData = response;
        this._updateDisplay();
      }
    } catch (err) {
      // Non-fatal: solution unavailable, display will use stateManager data
      console.debug("Firing solution request failed:", err.message);
    }
  }

  // -- Rendering helpers for the firing solution breakdown --

  /**
   * Merge solution data from stateManager targeting state and the
   * polled get_target_solution response. The polled data takes priority.
   */
  _getMergedSolution(targeting) {
    const sol = this._solutionData || {};
    const fallback = targeting.solution || targeting.firing_solution || {};
    return {
      weapons: sol.weapons || fallback.weapons || {},
      confidence: sol.lock_quality ?? fallback.confidence ?? targeting.confidence ?? null,
      target_subsystem: sol.target_subsystem ?? fallback.target_subsystem ?? targeting.target_subsystem ?? null,
    };
  }

  _renderFiringSolutionSection(targeting) {
    const merged = this._getMergedSolution(targeting);
    const weapons = merged.weapons;
    const weaponIds = Object.keys(weapons);
    const confidence = merged.confidence;

    // Determine overall solution quality from best weapon confidence,
    // falling back to lock_quality-based confidence.
    let bestConfidence = confidence;
    for (const wid of weaponIds) {
      const wc = weapons[wid].confidence;
      if (wc != null && (bestConfidence == null || wc > bestConfidence)) {
        bestConfidence = wc;
      }
    }

    // If no solution data at all, show a minimal placeholder
    if (bestConfidence == null && weaponIds.length === 0) {
      return `
        <div class="solution-section">
          <div class="section-title">Firing Solution Breakdown</div>
          <div class="solution-quality-badge none">AWAITING DATA</div>
        </div>
      `;
    }

    const qualityLabel = this._solutionQualityLabel(bestConfidence);
    const qualityClass = this._solutionQualityClass(bestConfidence);
    const pulseClass = bestConfidence != null && bestConfidence > 0.8 ? "valid-pulse" : "";

    // Confidence bar
    const confPct = bestConfidence != null ? Math.round(bestConfidence * 100) : 0;
    const confColorClass = confPct > 80 ? "high" : confPct > 40 ? "mid" : "low";

    let html = `
      <div class="solution-section">
        <div class="section-title">Firing Solution Breakdown</div>
        <div class="solution-quality-badge ${qualityClass} ${pulseClass}">${qualityLabel}</div>

        <div class="confidence-bar-container">
          <div class="detail-label">SOLUTION CONFIDENCE</div>
          <div class="confidence-bar">
            <div class="confidence-fill ${confColorClass}" style="width: ${confPct}%"></div>
            <span class="confidence-label">${confPct}%</span>
          </div>
        </div>
    `;

    // Render per-weapon cards
    if (weaponIds.length > 0) {
      html += `<div class="weapon-solutions">`;
      for (const wid of weaponIds) {
        html += this._renderWeaponCard(wid, weapons[wid]);
      }
      html += `</div>`;
    }

    html += `</div>`;
    return html;
  }

  _renderWeaponCard(weaponId, sol) {
    const ready = sol.ready || false;
    const readyClass = ready ? "ready" : "";
    const readyTag = ready
      ? `<span class="weapon-ready-tag ready">READY</span>`
      : `<span class="weapon-ready-tag not-ready">${sol.reason || "NOT READY"}</span>`;

    const confidence = sol.confidence != null ? Math.round(sol.confidence * 100) : null;
    const hitProb = sol.hit_probability != null ? Math.round(sol.hit_probability * 100) : null;
    const leadAngle = sol.lead_angle != null ? sol.lead_angle.toFixed(2) : null;
    const tof = sol.time_of_flight != null ? sol.time_of_flight.toFixed(1) : null;

    const confClass = confidence != null ? (confidence > 80 ? "high" : confidence > 40 ? "mid" : "low") : "";
    const hitClass = hitProb != null ? (hitProb > 60 ? "high" : hitProb > 30 ? "mid" : "low") : "";

    // Format the weapon ID for display (e.g. "railgun_1" -> "RAILGUN 1")
    const displayName = weaponId.replace(/_/g, " ");

    return `
      <div class="weapon-card ${readyClass}">
        <div class="weapon-card-header">
          <span class="weapon-name">${displayName}</span>
          ${readyTag}
        </div>
        <div class="weapon-stats">
          <div class="weapon-stat">
            <span class="weapon-stat-label">Confidence</span>
            <span class="weapon-stat-value ${confClass}">${confidence != null ? confidence + '%' : '--'}</span>
          </div>
          <div class="weapon-stat">
            <span class="weapon-stat-label">Hit Prob</span>
            <span class="weapon-stat-value ${hitClass}">${hitProb != null ? hitProb + '%' : '--'}</span>
          </div>
          <div class="weapon-stat">
            <span class="weapon-stat-label">Lead Angle</span>
            <span class="weapon-stat-value">${leadAngle != null ? leadAngle + '\u00B0' : '--'}</span>
          </div>
          <div class="weapon-stat">
            <span class="weapon-stat-label">Time to Impact</span>
            <span class="weapon-stat-value">${tof != null ? tof + 's' : '--'}</span>
          </div>
        </div>
      </div>
    `;
  }

  _renderSubsystemSection(targeting) {
    const merged = this._getMergedSolution(targeting);
    const subsystem = merged.target_subsystem;

    if (!subsystem) {
      return "";
    }

    // Try to get target subsystem health from state if available
    const targetSystems = targeting.target_systems || targeting.target_subsystems || {};
    const health = targetSystems[subsystem];
    let healthDisplay = "";
    if (health != null) {
      const healthPct = typeof health === "number" ? Math.round(health * 100) : health;
      const healthClass = healthPct > 50 ? "high" : healthPct > 0 ? "mid" : "low";
      healthDisplay = `<span class="subsystem-health weapon-stat-value ${healthClass}">${healthPct}%</span>`;
    }

    return `
      <div class="subsystem-section">
        <div class="section-title">Targeted Subsystem</div>
        <div class="subsystem-target">
          <span class="subsystem-name">${subsystem}</span>
          ${healthDisplay}
        </div>
      </div>
    `;
  }

  _solutionQualityLabel(confidence) {
    if (confidence == null) return "NO SOLUTION";
    if (confidence > 0.8) return "FIRING SOLUTION VALID";
    if (confidence > 0.4) return "MARGINAL SOLUTION";
    return "NO SOLUTION";
  }

  _solutionQualityClass(confidence) {
    if (confidence == null) return "none";
    if (confidence > 0.8) return "good";
    if (confidence > 0.4) return "marginal";
    return "none";
  }

  _formatBearing(bearing) {
    if (typeof bearing !== "number") return "---";
    return bearing.toFixed(1);
  }

  _formatRange(meters) {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(2)} km`;
    }
    return `${meters.toFixed(0)} m`;
  }
}

customElements.define("targeting-display", TargetingDisplay);
export { TargetingDisplay };
