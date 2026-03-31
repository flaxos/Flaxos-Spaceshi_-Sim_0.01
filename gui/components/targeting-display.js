/**
 * Targeting Computer Display
 *
 * Two-step lock pipeline visualization:
 *   SENSOR ACQUISITION (confidence bar) -> WEAPONS LOCK (track/lock bar)
 *   -> SOLUTION status -> FIRE status
 *
 * The first two stages are prominent progress bars showing the player
 * exactly where they are in the lock pipeline. The last two are compact
 * status indicators.
 *
 * Data sources:
 *   - stateManager.getTargeting() for lock_state, track_quality, lock_progress, etc.
 *   - Polled firing solution data via get_target_solution command
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

    this._contactSelectedHandler = (e) => {
      this._onContactSelected(e.detail.contactId);
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
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

        /* --- No target state --- */
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

        /* --- Target header --- */
        .target-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 12px;
          border-radius: 8px;
          margin-bottom: 12px;
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

        /* --- Range HUD --- */
        .range-hud {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 8px 10px;
          margin-bottom: 12px;
          background: rgba(0, 0, 0, 0.35);
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          letter-spacing: 0.3px;
        }
        .range-hud-item {
          display: flex;
          align-items: center;
          gap: 4px;
          white-space: nowrap;
        }
        .range-hud-label {
          font-size: 0.6rem;
          font-weight: 700;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .range-hud-value {
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }
        .range-hud-value.closing { color: var(--status-critical, #ff4444); }
        .range-hud-value.opening { color: var(--status-nominal, #00ff88); }
        .range-hud-value.eta { color: var(--status-info, #00aaff); }
        .range-hud-sep {
          color: var(--text-dim, #555566);
          font-size: 0.55rem;
          user-select: none;
        }

        /* === TWO-STEP LOCK PIPELINE === */
        .pipeline-section {
          margin-bottom: 12px;
        }

        /* Big progress bars for sensor + weapons steps */
        .step-bar {
          margin-bottom: 14px;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 8px;
          border: 1px solid var(--border-default, #2a2a3a);
        }
        .step-bar.active {
          border-color: var(--status-info, #00aaff);
        }
        .step-bar.complete {
          border-color: var(--status-nominal, #00ff88);
        }

        .step-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 6px;
        }
        .step-label {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: var(--text-secondary, #888899);
        }
        .step-label.active { color: var(--status-info, #00aaff); }
        .step-label.complete { color: var(--status-nominal, #00ff88); }
        .step-label.lost { color: var(--status-critical, #ff4444); }

        .step-pct {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1rem;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          color: var(--text-primary, #e0e0e0);
        }
        .step-pct.active { color: var(--status-info, #00aaff); }
        .step-pct.complete { color: var(--status-nominal, #00ff88); }

        .step-sub {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 4px;
        }

        .bar-track {
          height: 16px;
          background: rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          overflow: hidden;
          position: relative;
        }

        .bar-fill {
          height: 100%;
          border-radius: 8px;
          transition: width 0.3s ease, background 0.3s ease;
        }
        .bar-fill.amber { background: var(--status-warning, #ffaa00); }
        .bar-fill.green { background: var(--status-nominal, #00ff88); }
        .bar-fill.blue { background: var(--status-info, #00aaff); }
        .bar-fill.red { background: var(--status-critical, #ff4444); }

        .bar-pct-overlay {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.6rem;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          text-shadow: 0 0 4px rgba(0, 0, 0, 0.8);
        }

        /* Compact status indicators for solution + fire */
        .status-row {
          display: flex;
          gap: 8px;
          margin-bottom: 12px;
        }

        .status-chip {
          flex: 1;
          padding: 10px 12px;
          border-radius: 6px;
          text-align: center;
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-dim, #555566);
        }
        .status-chip.ready {
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.08);
        }
        .status-chip.computing {
          border-color: var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
          background: rgba(0, 170, 255, 0.08);
          animation: chip-pulse 1.5s ease-in-out infinite;
        }
        .status-chip.unavailable {
          border-color: var(--border-default, #2a2a3a);
          color: var(--text-dim, #555566);
        }

        @keyframes chip-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        .chip-title {
          font-size: 0.55rem;
          color: var(--text-secondary, #888899);
          letter-spacing: 0.5px;
          margin-bottom: 4px;
        }
        .chip-title.ready { color: var(--status-nominal, #00ff88); }

        /* --- Subsystem target --- */
        .subsystem-section {
          margin-top: 8px;
          padding: 8px 10px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
        }
        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 4px;
        }
        .subsystem-name {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--status-info, #00aaff);
          text-transform: uppercase;
        }

        /* --- Lock lost warning --- */
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
          margin-top: 8px;
        }
        .warning-icon { font-size: 1rem; }

        /* --- Request solution button --- */
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

        @media (prefers-reduced-motion: reduce) {
          .bar-fill { transition: none !important; }
          .lock-indicator,
          .status-chip.computing { animation: none !important; }
        }
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

    if (!this._hadTarget) {
      this._hadTarget = true;
      this._startSolutionPolling();
    }

    const trackQuality = targeting.track_quality ?? 0;
    const lockProgress = targeting.lock_progress ?? 0;
    const lockQuality = targeting.lock_quality ?? 0;
    const targetSubsystem = targeting.target_subsystem || null;

    const solutions = this._getMergedSolutions(targeting);
    const basicSolution = solutions._basic || {};

    const range = basicSolution.range ?? 0;
    const rangeRate = basicSolution.range_rate ?? 0;
    const closing = basicSolution.closing ?? false;
    const tca = basicSolution.time_to_cpa ?? null;

    let html = "";

    // 1. Target header
    html += this._renderTargetHeader(lockState, lockedTarget);

    // 2. Range HUD
    if (range > 0) {
      html += this._renderRangeHud(range, rangeRate, closing, tca);
    }

    // 3. Two-step pipeline: SENSOR + WEAPONS bars
    html += this._renderPipelineBars(lockState, trackQuality, lockProgress, lockQuality);

    // 4. Solution + Fire status chips
    html += this._renderStatusChips(lockState, solutions);

    // 5. Subsystem target
    if (targetSubsystem) {
      html += `
        <div class="subsystem-section">
          <div class="section-title">Targeted Subsystem</div>
          <div class="subsystem-name">${targetSubsystem}</div>
        </div>
      `;
    }

    // 6. Lock lost warning
    if (lockState === "lost") {
      html += `
        <div class="warning-box">
          <span class="warning-icon">!</span>
          <span>LOCK LOST - REACQUIRING</span>
        </div>
      `;
    }

    // 7. Refresh button
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

  // --- Two-step pipeline bars ---

  /**
   * Renders the two prominent progress bars:
   * Step 1 (SENSOR): shows sensor confidence / track quality building.
   * Step 2 (WEAPONS): shows lock acquisition progress, then lock quality.
   */
  _renderPipelineBars(lockState, trackQuality, lockProgress, lockQuality) {
    const isLost = lockState === "lost";

    // SENSOR step: driven by track quality (0-1)
    // Green when track is good enough for lock (>= 0.3 threshold implied by server)
    const sensorPct = Math.round(trackQuality * 100);
    const sensorComplete = trackQuality >= 0.3 && !isLost;
    const sensorActive = !sensorComplete && !isLost;
    const sensorBarColor = isLost ? "red" : sensorComplete ? "green" : "amber";
    const sensorLabelClass = isLost ? "lost" : sensorComplete ? "complete" : "active";

    // WEAPONS step: shows different sub-states
    //   TRACKING: track quality bar (same data, but weapons context)
    //   ACQUIRING: lock progress bar
    //   LOCKED: lock quality bar (solid green)
    let weaponsPct = 0;
    let weaponsBarColor = "amber";
    let weaponsSub = "WAITING";
    let weaponsLabelClass = "";
    let weaponsComplete = false;

    if (isLost) {
      weaponsPct = 0;
      weaponsBarColor = "red";
      weaponsSub = "LOCK LOST";
      weaponsLabelClass = "lost";
    } else if (lockState === "tracking") {
      weaponsPct = Math.round(trackQuality * 100);
      weaponsBarColor = "amber";
      weaponsSub = "TRACKING";
      weaponsLabelClass = "active";
    } else if (lockState === "acquiring") {
      weaponsPct = Math.round(lockProgress * 100);
      weaponsBarColor = "blue";
      weaponsSub = "ACQUIRING LOCK";
      weaponsLabelClass = "active";
    } else if (lockState === "locked") {
      weaponsPct = Math.round(lockQuality * 100);
      weaponsBarColor = "green";
      weaponsSub = "LOCKED";
      weaponsLabelClass = "complete";
      weaponsComplete = true;
    }

    return `
      <div class="pipeline-section">
        <div class="step-bar ${isLost ? '' : sensorComplete ? 'complete' : 'active'}">
          <div class="step-header">
            <span class="step-label ${sensorLabelClass}">SENSOR</span>
            <span class="step-pct ${sensorComplete ? 'complete' : 'active'}">${sensorPct}%</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill ${sensorBarColor}" style="width: ${sensorPct}%"></div>
            <span class="bar-pct-overlay">${this._trackQualityBrief(trackQuality)}</span>
          </div>
        </div>

        <div class="step-bar ${weaponsComplete ? 'complete' : isLost ? '' : 'active'}">
          <div class="step-header">
            <span class="step-label ${weaponsLabelClass}">WEAPONS</span>
            <span class="step-pct ${weaponsComplete ? 'complete' : 'active'}">${weaponsPct}%</span>
          </div>
          <div class="step-sub">${weaponsSub}</div>
          <div class="bar-track">
            <div class="bar-fill ${weaponsBarColor}" style="width: ${weaponsPct}%"></div>
          </div>
        </div>
      </div>
    `;
  }

  // --- Status chips for Solution + Fire ---

  _renderStatusChips(lockState, solutions) {
    const weaponIds = Object.keys(solutions).filter(k => k !== "_basic");
    let bestConfidence = null;
    let anyReady = false;

    for (const wid of weaponIds) {
      const wc = solutions[wid].confidence;
      if (wc != null && (bestConfidence == null || wc > bestConfidence)) {
        bestConfidence = wc;
      }
      if (solutions[wid].ready) anyReady = true;
    }

    const hasSolution = bestConfidence != null && bestConfidence > 0.5;
    const solutionClass = hasSolution ? "ready" : (lockState === "locked" ? "computing" : "unavailable");
    const solutionText = hasSolution
      ? `READY ${Math.round(bestConfidence * 100)}%`
      : (lockState === "locked" ? "COMPUTING..." : "---");
    const solutionTitleClass = hasSolution ? "ready" : "";

    const fireClass = anyReady && hasSolution ? "ready" : "unavailable";
    const fireText = anyReady && hasSolution ? "READY" : "---";
    const fireTitleClass = anyReady && hasSolution ? "ready" : "";

    return `
      <div class="status-row">
        <div class="status-chip ${solutionClass}">
          <div class="chip-title ${solutionTitleClass}">SOLUTION</div>
          ${solutionText}
        </div>
        <div class="status-chip ${fireClass}">
          <div class="chip-title ${fireTitleClass}">FIRE</div>
          ${fireText}
        </div>
      </div>
    `;
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

  // --- Range HUD ---

  _renderRangeHud(range, rangeRate, closing, tca) {
    const rangeStr = this._formatRange(range);
    const closureAbs = Math.abs(rangeRate);
    const closureClass = closing ? "closing" : "opening";
    const closureLabel = closing ? "CLS" : "OPN";
    const closureStr = closureAbs >= 1000
      ? `${(closureAbs / 1000).toFixed(1)} km/s`
      : `${closureAbs.toFixed(0)} m/s`;

    let etaStr = null;
    if (closing && closureAbs > 0) {
      if (tca != null && tca > 0) {
        etaStr = this._formatEta(tca);
      } else {
        const etaSec = range / closureAbs;
        if (etaSec < 86400) etaStr = this._formatEta(etaSec);
      }
    }

    let html = `
      <div class="range-hud" data-testid="range-hud">
        <span class="range-hud-item">
          <span class="range-hud-label">RNG</span>
          <span class="range-hud-value">${rangeStr}</span>
        </span>
        <span class="range-hud-sep">|</span>
        <span class="range-hud-item">
          <span class="range-hud-label">${closureLabel}</span>
          <span class="range-hud-value ${closureClass}">${closureStr}</span>
        </span>
    `;

    if (etaStr) {
      html += `
        <span class="range-hud-sep">|</span>
        <span class="range-hud-item">
          <span class="range-hud-label">ETA</span>
          <span class="range-hud-value eta">${etaStr}</span>
        </span>
      `;
    }

    html += `</div>`;
    return html;
  }

  // --- Helpers ---

  _trackQualityBrief(quality) {
    if (quality >= 0.9) return "EXCELLENT";
    if (quality >= 0.7) return "GOOD";
    if (quality >= 0.5) return "FAIR";
    if (quality >= 0.3) return "POOR";
    return "MINIMAL";
  }

  _formatEta(seconds) {
    if (seconds < 0) return "--";
    if (seconds < 120) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return `${h}h${m > 0 ? m + "m" : ""}`;
  }

  _formatRange(meters) {
    if (meters == null || meters === 0) return "---";
    if (meters >= 1000000) return `${(meters / 1000).toFixed(0)} km`;
    if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
    return `${meters.toFixed(0)} m`;
  }

  // --- Solution data ---

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

  _getMergedSolutions(targeting) {
    const polled = this._solutionData || {};
    const stateSolutions = targeting?.solutions || {};

    const weapons = {};
    const allIds = new Set([
      ...Object.keys(polled.weapons || {}),
      ...Object.keys(stateSolutions),
    ]);

    for (const wid of allIds) {
      weapons[wid] = polled.weapons?.[wid] || stateSolutions[wid] || {};
    }

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
}

customElements.define("targeting-display", TargetingDisplay);
export { TargetingDisplay };
