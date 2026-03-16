/**
 * Targeting Computer Display
 *
 * Shows the full targeting pipeline stages:
 *   contact -> track -> lock -> firing solution -> fire
 *
 * Each stage is visible so the player understands WHY solutions are
 * good or bad (design spec: "player sees each stage").
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
    this._hadTarget = false;
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
          padding: 0;
        }

        .no-lock {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px;
          color: var(--text-dim, #555566);
        }

        .no-lock-icon { font-size: 2rem; margin-bottom: 8px; opacity: 0.5; }
        .no-lock-text { font-size: 0.9rem; margin-bottom: 8px; }
        .no-lock-hint { font-size: 0.7rem; font-style: italic; }

        /* --- Pipeline stage indicator --- */
        .pipeline {
          display: flex;
          align-items: center;
          gap: 4px;
          margin-bottom: 16px;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 8px;
        }

        .pipeline-stage {
          flex: 1;
          text-align: center;
          padding: 6px 4px;
          font-size: 0.6rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-dim, #555566);
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          border: 1px solid transparent;
          transition: all 0.3s ease;
        }

        .pipeline-stage.completed {
          color: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.08);
        }

        .pipeline-stage.active {
          color: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          background: rgba(0, 170, 255, 0.12);
          animation: stage-pulse 1.5s ease-in-out infinite;
        }

        .pipeline-stage.lost {
          color: var(--status-critical, #ff4444);
          border-color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.1);
        }

        .pipeline-arrow {
          color: var(--text-dim, #555566);
          font-size: 0.6rem;
          flex-shrink: 0;
        }

        .pipeline-arrow.completed {
          color: var(--status-nominal, #00ff88);
        }

        @keyframes stage-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        /* --- Target header --- */
        .target-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          border-radius: 8px;
          margin-bottom: 16px;
        }

        .target-header.tracking {
          background: rgba(255, 170, 0, 0.08);
          border: 1px solid var(--status-warning, #ffaa00);
        }

        .target-header.acquiring {
          background: rgba(0, 170, 255, 0.08);
          border: 1px solid var(--status-info, #00aaff);
        }

        .target-header.locked {
          background: rgba(0, 255, 136, 0.08);
          border: 1px solid var(--status-nominal, #00ff88);
        }

        .target-header.lost {
          background: rgba(255, 68, 68, 0.08);
          border: 1px solid var(--status-critical, #ff4444);
        }

        .lock-indicator {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .lock-indicator.tracking {
          background: var(--status-warning, #ffaa00);
          animation: pulse 1s ease-in-out infinite;
        }

        .lock-indicator.acquiring {
          background: var(--status-info, #00aaff);
          animation: pulse 0.7s ease-in-out infinite;
        }

        .lock-indicator.locked {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 12px var(--status-nominal, #00ff88);
          animation: pulse 2s ease-in-out infinite;
        }

        .lock-indicator.lost {
          background: var(--status-critical, #ff4444);
          animation: pulse 0.4s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }

        .lock-text {
          font-weight: 600;
          font-size: 0.75rem;
          text-transform: uppercase;
        }

        .lock-text.tracking { color: var(--status-warning, #ffaa00); }
        .lock-text.acquiring { color: var(--status-info, #00aaff); }
        .lock-text.locked { color: var(--status-nominal, #00ff88); }
        .lock-text.lost { color: var(--status-critical, #ff4444); }

        .target-id {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
        }

        /* --- Details rows --- */
        .target-details {
          display: grid;
          gap: 4px;
          margin-bottom: 16px;
        }

        .detail-row {
          display: flex;
          justify-content: space-between;
          padding: 4px 0;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .detail-row:last-child { border-bottom: none; }

        .detail-label {
          color: var(--text-secondary, #888899);
          font-size: 0.75rem;
        }

        .detail-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
        }

        .closure-value.closing { color: var(--status-critical, #ff4444); }
        .closure-value.opening { color: var(--status-nominal, #00ff88); }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        /* --- Track quality / lock progress bars --- */
        .bar-section { margin-bottom: 12px; }

        .bar-container {
          height: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 6px;
          overflow: hidden;
          margin-top: 6px;
          position: relative;
        }

        .bar-fill {
          height: 100%;
          transition: width 0.3s ease;
          border-radius: 6px;
        }

        .bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .bar-fill.info { background: var(--status-info, #00aaff); }
        .bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .bar-fill.critical { background: var(--status-critical, #ff4444); }

        .bar-label {
          position: absolute;
          right: 6px;
          top: 50%;
          transform: translateY(-50%);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.6rem;
          color: var(--text-primary, #e0e0e0);
          text-shadow: 0 0 4px rgba(0, 0, 0, 0.8);
        }

        .bar-inline-label {
          display: flex;
          justify-content: space-between;
          font-size: 0.7rem;
          margin-top: 4px;
        }

        .bar-inline-label .detail-label {
          font-size: 0.65rem;
        }

        /* --- Solution grid --- */
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

        /* --- Solution badges --- */
        .solution-section { margin-top: 16px; }

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

        .confidence-bar-container { margin-bottom: 12px; }

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

        /* --- Weapon cards --- */
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

        .weapon-stat { display: flex; flex-direction: column; }

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

        /* --- Subsystem targeting --- */
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

        /* --- Degradation reasons --- */
        .degradation-info {
          margin-top: 8px;
          padding: 8px 10px;
          background: rgba(255, 170, 0, 0.06);
          border: 1px solid rgba(255, 170, 0, 0.2);
          border-radius: 6px;
          font-size: 0.7rem;
          color: var(--status-warning, #ffaa00);
        }

        .degradation-info .info-title {
          font-weight: 600;
          text-transform: uppercase;
          font-size: 0.6rem;
          letter-spacing: 0.5px;
          margin-bottom: 4px;
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

        .warning-icon { font-size: 1rem; }

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

        .request-solution-btn:hover { background: rgba(0, 170, 255, 0.2); }
        .request-solution-btn:active { background: rgba(0, 170, 255, 0.3); }
      </style>

      <div id="content">
        <div class="no-lock">
          <div class="no-lock-icon">&#9675;</div>
          <div class="no-lock-text">NO TARGET LOCK</div>
          <div class="no-lock-hint">Select a contact from Sensors panel</div>
        </div>
      </div>
    `;
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    // Determine pipeline state from the targeting telemetry.
    // The targeting system exposes: locked_target, lock_state, track_quality,
    // lock_progress, lock_quality, solutions, target_subsystem.
    const lockState = targeting?.lock_state || "none";
    const lockedTarget = targeting?.locked_target || null;
    const hasTarget = lockedTarget != null && lockState !== "none";

    if (!hasTarget) {
      if (this._hadTarget) {
        this._stopSolutionPolling();
        this._solutionData = null;
        this._hadTarget = false;
      }
      content.innerHTML = `
        <div class="no-lock">
          <div class="no-lock-icon">&#9675;</div>
          <div class="no-lock-text">NO TARGET DESIGNATED</div>
          <div class="no-lock-hint">Select a contact from Sensors panel</div>
        </div>
      `;
      return;
    }

    // Start polling when we first get a target
    if (!this._hadTarget) {
      this._hadTarget = true;
      this._startSolutionPolling();
    }

    // Extract pipeline metrics
    const trackQuality = targeting.track_quality ?? 0;
    const lockProgress = targeting.lock_progress ?? 0;
    const lockQuality = targeting.lock_quality ?? 0;
    const targetSubsystem = targeting.target_subsystem || null;

    // Get solution data (merge polled + state)
    const solutions = this._getMergedSolutions(targeting);
    const basicSolution = solutions._basic || {};

    const range = basicSolution.range ?? 0;
    const rangeRate = basicSolution.range_rate ?? 0;
    const bearing = basicSolution.bearing;
    const tca = basicSolution.time_to_cpa ?? null;
    const cpa = basicSolution.cpa_distance ?? null;
    const closing = basicSolution.closing ?? false;

    // Build the display
    let html = "";

    // 1. Pipeline stage indicator
    html += this._renderPipeline(lockState);

    // 2. Target header with state-appropriate styling
    html += this._renderTargetHeader(lockState, lockedTarget);

    // 3. Track quality bar (always shown when tracking)
    if (lockState !== "none") {
      html += this._renderBarSection(
        "Track Quality",
        trackQuality,
        this._trackQualityExplanation(trackQuality)
      );
    }

    // 4. Lock progress (shown during acquiring)
    if (lockState === "acquiring") {
      html += this._renderBarSection("Lock Progress", lockProgress, null, "info");
    }

    // 5. Lock quality (shown when locked)
    if (lockState === "locked") {
      const lqColor = lockQuality > 0.8 ? "nominal" : lockQuality > 0.5 ? "warning" : "critical";
      html += this._renderBarSection("Lock Quality", lockQuality, null, lqColor);
    }

    // 6. Target details (range, bearing, closure)
    if (range > 0 || bearing) {
      const closureClass = closing ? "closing" : "opening";
      const closureText = closing ? "CLOSING" : "OPENING";
      html += `
        <div class="target-details">
          <div class="detail-row">
            <span class="detail-label">RANGE</span>
            <span class="detail-value">${this._formatRange(range)}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">BEARING</span>
            <span class="detail-value">${this._formatBearing(bearing)}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">CLOSURE</span>
            <span class="detail-value closure-value ${closureClass}">
              ${Math.abs(rangeRate).toFixed(0)} m/s (${closureText})
            </span>
          </div>
        </div>
      `;
    }

    // 7. TCA/CPA
    if (lockState === "locked" && (tca != null || cpa != null)) {
      html += `
        <div class="solution-grid">
          <div class="solution-item">
            <div class="solution-value">${tca != null ? tca.toFixed(0) + 's' : '--'}</div>
            <div class="solution-label">TCA</div>
          </div>
          <div class="solution-item">
            <div class="solution-value">${cpa != null ? this._formatRange(cpa) : '--'}</div>
            <div class="solution-label">CPA</div>
          </div>
        </div>
      `;
    }

    // 8. Firing solutions (only when locked)
    if (lockState === "locked") {
      html += this._renderFiringSolutionSection(targeting, solutions);
    }

    // 9. Targeted subsystem
    if (targetSubsystem) {
      html += this._renderSubsystemSection(targeting);
    }

    // 10. Lock lost warning
    if (lockState === "lost") {
      html += `
        <div class="warning-box">
          <span class="warning-icon">!</span>
          <span>LOCK LOST - REACQUIRING</span>
        </div>
      `;
    }

    // 11. Refresh button
    if (lockState === "locked") {
      html += `<button class="request-solution-btn" id="request-solution-btn">
        REQUEST SOLUTION UPDATE
      </button>`;
    }

    content.innerHTML = html;

    const reqBtn = this.shadowRoot.getElementById("request-solution-btn");
    if (reqBtn) {
      reqBtn.addEventListener("click", () => this._requestSolution());
    }
  }

  // --- Pipeline stage indicator ---

  _renderPipeline(lockState) {
    const stages = [
      { id: "contact", label: "Contact" },
      { id: "tracking", label: "Track" },
      { id: "acquiring", label: "Lock" },
      { id: "locked", label: "Solution" },
    ];

    // Determine the index of the current stage
    const stageOrder = ["contact", "tracking", "acquiring", "locked"];
    const currentIdx = stageOrder.indexOf(lockState);
    const isLost = lockState === "lost";

    let html = `<div class="pipeline" data-testid="pipeline-stages">`;
    stages.forEach((stage, i) => {
      let stageClass = "";
      if (isLost) {
        stageClass = i <= 1 ? "completed" : "lost";
      } else if (i < currentIdx) {
        stageClass = "completed";
      } else if (i === currentIdx) {
        stageClass = "active";
      }

      if (i > 0) {
        const arrowClass = (i <= currentIdx && !isLost) ? "completed" : "";
        html += `<span class="pipeline-arrow ${arrowClass}">&rarr;</span>`;
      }
      html += `<div class="pipeline-stage ${stageClass}" data-stage="${stage.id}">${stage.label}</div>`;
    });
    html += `</div>`;
    return html;
  }

  // --- Target header ---

  _renderTargetHeader(lockState, targetId) {
    const stateLabels = {
      tracking: "TRACKING:",
      acquiring: "ACQUIRING LOCK:",
      locked: "TARGET LOCKED:",
      lost: "LOCK LOST:",
    };
    const label = stateLabels[lockState] || "DESIGNATING:";

    return `
      <div class="target-header ${lockState}" data-testid="target-header">
        <div class="lock-indicator ${lockState}"></div>
        <span class="lock-text ${lockState}">${label}</span>
        <span class="target-id">${targetId}</span>
      </div>
    `;
  }

  // --- Bar section (track quality, lock progress, lock quality) ---

  _renderBarSection(title, value, explanation, colorOverride) {
    const pct = Math.round(value * 100);
    let colorClass;
    if (colorOverride) {
      colorClass = colorOverride;
    } else {
      colorClass = pct > 80 ? "nominal" : pct > 50 ? "info" : pct > 30 ? "warning" : "critical";
    }

    let html = `
      <div class="bar-section">
        <div class="bar-inline-label">
          <span class="detail-label">${title}</span>
          <span class="detail-value" style="font-size: 0.7rem">${pct}%</span>
        </div>
        <div class="bar-container">
          <div class="bar-fill ${colorClass}" style="width: ${pct}%"></div>
        </div>
    `;

    if (explanation) {
      html += `
        <div class="degradation-info">
          <div class="info-title">Factors</div>
          ${explanation}
        </div>
      `;
    }

    html += `</div>`;
    return html;
  }

  _trackQualityExplanation(quality) {
    if (quality >= 0.9) return "Excellent track - clear return";
    if (quality >= 0.7) return "Good track - minor degradation";
    if (quality >= 0.5) return "Fair track - range or maneuver effects";
    if (quality >= 0.3) return "Poor track - high range or target maneuvering";
    return "Minimal track - extreme range or sensor damage";
  }

  // --- Firing solution polling ---

  _startSolutionPolling() {
    this._stopSolutionPolling();
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
      console.debug("Firing solution request failed:", err.message);
    }
  }

  // --- Merged solutions ---

  _getMergedSolutions(targeting) {
    // Combine state-pushed solutions with polled solution data.
    // Polled data (from get_target_solution) takes priority.
    const polled = this._solutionData || {};
    const stateSolutions = targeting?.solutions || {};

    // Build weapon solutions: prefer polled weapon data, fall back to state
    const weapons = {};
    const allIds = new Set([
      ...Object.keys(polled.weapons || {}),
      ...Object.keys(stateSolutions),
    ]);

    for (const wid of allIds) {
      weapons[wid] = polled.weapons?.[wid] || stateSolutions[wid] || {};
    }

    // Basic solution data (range, bearing, etc.)
    const _basic = {
      range: polled.range ?? 0,
      bearing: polled.bearing ?? null,
      range_rate: polled.range_rate ?? 0,
      closing: polled.closing ?? false,
      time_to_cpa: polled.time_to_cpa ?? null,
      cpa_distance: polled.cpa_distance ?? null,
    };

    return { ...weapons, _basic };
  }

  // --- Firing solution section ---

  _renderFiringSolutionSection(targeting, solutions) {
    const weaponIds = Object.keys(solutions).filter(k => k !== "_basic");

    let bestConfidence = null;
    for (const wid of weaponIds) {
      const wc = solutions[wid].confidence;
      if (wc != null && (bestConfidence == null || wc > bestConfidence)) {
        bestConfidence = wc;
      }
    }

    if (bestConfidence == null && weaponIds.length === 0) {
      return `
        <div class="solution-section">
          <div class="section-title">Firing Solutions</div>
          <div class="solution-quality-badge none">COMPUTING</div>
        </div>
      `;
    }

    const qualityLabel = this._solutionQualityLabel(bestConfidence);
    const qualityClass = this._solutionQualityClass(bestConfidence);
    const pulseClass = bestConfidence != null && bestConfidence > 0.8 ? "valid-pulse" : "";

    const confPct = bestConfidence != null ? Math.round(bestConfidence * 100) : 0;
    const confColorClass = confPct > 80 ? "high" : confPct > 40 ? "mid" : "low";

    let html = `
      <div class="solution-section">
        <div class="section-title">Firing Solutions</div>
        <div class="solution-quality-badge ${qualityClass} ${pulseClass}">${qualityLabel}</div>

        <div class="confidence-bar-container">
          <div class="detail-label">BEST SOLUTION CONFIDENCE</div>
          <div class="confidence-bar">
            <div class="confidence-fill ${confColorClass}" style="width: ${confPct}%"></div>
            <span class="confidence-label">${confPct}%</span>
          </div>
        </div>
    `;

    if (weaponIds.length > 0) {
      html += `<div class="weapon-solutions">`;
      for (const wid of weaponIds) {
        html += this._renderWeaponCard(wid, solutions[wid]);
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
    const leadAngle = sol.lead_angle != null
      ? (typeof sol.lead_angle === "object"
        ? Math.sqrt((sol.lead_angle.pitch || 0) ** 2 + (sol.lead_angle.yaw || 0) ** 2).toFixed(2)
        : sol.lead_angle.toFixed(2))
      : null;
    const tof = sol.time_of_flight != null ? sol.time_of_flight.toFixed(1) : null;

    const confClass = confidence != null ? (confidence > 80 ? "high" : confidence > 40 ? "mid" : "low") : "";
    const hitClass = hitProb != null ? (hitProb > 60 ? "high" : hitProb > 30 ? "mid" : "low") : "";

    const displayName = weaponId.replace(/_/g, " ");

    // Cone radius for visual feedback
    const coneRadius = sol.cone_radius_m;
    const coneStr = coneRadius != null
      ? (coneRadius >= 1000 ? `${(coneRadius / 1000).toFixed(1)} km` : `${coneRadius.toFixed(0)} m`)
      : null;

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
            <span class="weapon-stat-label">Time of Flight</span>
            <span class="weapon-stat-value">${tof != null ? tof + 's' : '--'}</span>
          </div>
          ${coneStr ? `
          <div class="weapon-stat">
            <span class="weapon-stat-label">Cone Radius</span>
            <span class="weapon-stat-value">${coneStr}</span>
          </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  _renderSubsystemSection(targeting) {
    const subsystem = targeting?.target_subsystem;
    if (!subsystem) return "";

    return `
      <div class="subsystem-section">
        <div class="section-title">Targeted Subsystem</div>
        <div class="subsystem-target">
          <span class="subsystem-name">${subsystem}</span>
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
    if (bearing == null) return "---";
    if (typeof bearing === "number") return bearing.toFixed(1) + "\u00B0";
    if (typeof bearing === "object") {
      const az = bearing.azimuth ?? bearing.yaw ?? bearing.horizontal;
      if (az != null) return az.toFixed(1) + "\u00B0";
    }
    return "---";
  }

  _formatRange(meters) {
    if (meters == null || meters === 0) return "---";
    if (meters >= 1000000) return `${(meters / 1000).toFixed(0)} km`;
    if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
    return `${meters.toFixed(0)} m`;
  }
}

customElements.define("targeting-display", TargetingDisplay);
export { TargetingDisplay };
