/**
 * Target Damage Assessment Panel
 *
 * Dedicated panel for viewing enemy subsystem damage estimates.
 * Sends `assess_damage` command and displays hull integrity + subsystem
 * health with confidence-weighted accuracy based on track quality.
 *
 * Auto-refreshes every 5 seconds while a target is locked.
 * Color coding: green (>75%), yellow (25-75%), red (<25%), struck-through (destroyed).
 *
 * Data source: assess_damage command returns:
 *   { ok, target_id, assessment_quality, subsystems: { name: { health, status, confidence } } }
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const ASSESS_INTERVAL_MS = 5000;

// Subsystem display names and order (propulsion first — mission kill priority)
const SUBSYSTEM_ORDER = [
  { key: "propulsion", label: "Drive" },
  { key: "rcs", label: "RCS" },
  { key: "sensors", label: "Sensors" },
  { key: "weapons", label: "Weapons" },
  { key: "reactor", label: "Reactor" },
];

class TargetAssessment extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._assessInterval = null;
    this._assessmentData = null;
    this._lastAssessTime = null;
    this._assessing = false;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    this._stopAutoAssess();
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  _startAutoAssess() {
    if (this._assessInterval) return;
    this._assessInterval = setInterval(() => {
      this._assessDamage();
    }, ASSESS_INTERVAL_MS);
  }

  _stopAutoAssess() {
    if (this._assessInterval) {
      clearInterval(this._assessInterval);
      this._assessInterval = null;
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        /* --- Empty state: no lock --- */
        .no-target {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px 16px;
          color: var(--text-dim, #555566);
          text-align: center;
        }

        .no-target-icon {
          font-size: 1.8rem;
          margin-bottom: 8px;
          opacity: 0.4;
        }

        .no-target-text {
          font-size: 0.85rem;
          margin-bottom: 4px;
        }

        .no-target-hint {
          font-size: 0.7rem;
          font-style: italic;
        }

        /* --- Target header --- */
        .target-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 12px;
          padding: 8px 10px;
          background: rgba(0, 170, 255, 0.06);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 6px;
        }

        .target-name {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.9rem;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          flex: 1;
        }

        .lock-badge {
          font-size: 0.6rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          padding: 2px 8px;
          border-radius: 3px;
        }

        .lock-badge.locked {
          background: rgba(0, 255, 136, 0.15);
          color: var(--status-nominal, #00ff88);
          border: 1px solid var(--status-nominal, #00ff88);
        }

        .lock-badge.tracking {
          background: rgba(255, 170, 0, 0.15);
          color: var(--status-warning, #ffaa00);
          border: 1px solid var(--status-warning, #ffaa00);
        }

        .lock-badge.acquiring {
          background: rgba(0, 170, 255, 0.15);
          color: var(--status-info, #00aaff);
          border: 1px solid var(--status-info, #00aaff);
        }

        /* --- Hull integrity bar --- */
        .hull-section {
          margin-bottom: 14px;
        }

        .section-label {
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 6px;
        }

        .hull-bar-container {
          position: relative;
          height: 20px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .hull-bar-fill {
          height: 100%;
          transition: width 0.4s ease, background 0.4s ease;
          border-radius: 3px;
        }

        .hull-bar-fill.green {
          background: linear-gradient(90deg, #00cc66, #00ff88);
        }

        .hull-bar-fill.yellow {
          background: linear-gradient(90deg, #cc8800, #ffaa00);
        }

        .hull-bar-fill.red {
          background: linear-gradient(90deg, #cc2222, #ff4444);
        }

        .hull-bar-fill.destroyed {
          background: #333;
        }

        .hull-bar-label {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 700;
          color: #fff;
          text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
        }

        /* --- Subsystem rows --- */
        .subsystems-section {
          margin-bottom: 14px;
        }

        .subsystem-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 0;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .subsystem-row:last-child {
          border-bottom: none;
        }

        .subsys-name {
          width: 70px;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          color: var(--text-secondary, #888899);
          flex-shrink: 0;
        }

        .subsys-bar-container {
          flex: 1;
          height: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          overflow: hidden;
          position: relative;
        }

        .subsys-bar-fill {
          height: 100%;
          transition: width 0.3s ease, background 0.3s ease;
          border-radius: 3px;
        }

        .subsys-bar-fill.green { background: var(--status-nominal, #00ff88); }
        .subsys-bar-fill.yellow { background: var(--status-warning, #ffaa00); }
        .subsys-bar-fill.red { background: var(--status-critical, #ff4444); }
        .subsys-bar-fill.destroyed { background: #333; width: 0 !important; }

        .subsys-value {
          width: 44px;
          text-align: right;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          flex-shrink: 0;
        }

        .subsys-value.green { color: var(--status-nominal, #00ff88); }
        .subsys-value.yellow { color: var(--status-warning, #ffaa00); }
        .subsys-value.red { color: var(--status-critical, #ff4444); }
        .subsys-value.destroyed {
          color: var(--text-dim, #555566);
          text-decoration: line-through;
        }
        .subsys-value.unknown { color: var(--text-dim, #555566); }

        .subsys-confidence {
          width: 18px;
          font-size: 0.55rem;
          text-align: center;
          flex-shrink: 0;
          opacity: 0.7;
        }

        .subsys-confidence.high { color: var(--status-nominal, #00ff88); }
        .subsys-confidence.moderate { color: var(--status-warning, #ffaa00); }
        .subsys-confidence.low { color: var(--status-critical, #ff4444); }
        .subsys-confidence.none { color: var(--text-dim, #555566); }

        /* --- Footer: timestamp + assess button --- */
        .footer {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 4px;
        }

        .assess-btn {
          flex: 1;
          padding: 10px 12px;
          background: rgba(0, 170, 255, 0.08);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 6px;
          color: var(--status-info, #00aaff);
          font-family: inherit;
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          min-height: 38px;
          transition: background 0.15s ease;
        }

        .assess-btn:hover:not(:disabled) {
          background: rgba(0, 170, 255, 0.18);
        }

        .assess-btn:disabled {
          opacity: 0.35;
          cursor: not-allowed;
        }

        .assess-btn.assessing {
          animation: assess-pulse 1s ease-in-out infinite;
        }

        @keyframes assess-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        .assess-timestamp {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          white-space: nowrap;
        }

        /* --- Overall confidence footer --- */
        .confidence-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid var(--border-default, #2a2a3a);
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
        }

        .confidence-footer .quality-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-weight: 600;
        }

        .confidence-footer .quality-value.high { color: var(--status-nominal, #00ff88); }
        .confidence-footer .quality-value.moderate { color: var(--status-warning, #ffaa00); }
        .confidence-footer .quality-value.low { color: var(--status-critical, #ff4444); }

        /* --- Stale data warning --- */
        .stale-warning {
          margin-top: 6px;
          padding: 6px 10px;
          background: rgba(255, 170, 0, 0.08);
          border: 1px solid rgba(255, 170, 0, 0.3);
          border-radius: 4px;
          font-size: 0.65rem;
          color: var(--status-warning, #ffaa00);
          text-align: center;
        }

        /* --- No data state (locked but no assessment yet) --- */
        .no-data {
          text-align: center;
          padding: 16px;
          color: var(--text-dim, #555566);
          font-size: 0.8rem;
        }

        .no-data-hint {
          font-size: 0.7rem;
          font-style: italic;
          margin-top: 6px;
        }
      </style>

      <div id="content">
        <div class="no-target">
          <div class="no-target-icon">&#9678;</div>
          <div class="no-target-text">NO TARGET</div>
          <div class="no-target-hint">Lock a contact to assess damage</div>
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
      // No target — stop polling, clear data, show empty state
      this._stopAutoAssess();
      if (this._assessmentData) {
        this._assessmentData = null;
        this._lastAssessTime = null;
      }
      content.innerHTML = `
        <div class="no-target">
          <div class="no-target-icon">&#9678;</div>
          <div class="no-target-text">NO TARGET</div>
          <div class="no-target-hint">Lock a contact to assess damage</div>
        </div>
      `;
      return;
    }

    // Target is locked — start auto-assess if not already running
    this._startAutoAssess();

    // If we have no assessment data yet, show a prompt to assess
    if (!this._assessmentData) {
      content.innerHTML = `
        <div class="target-header">
          <span class="target-name">${this._escapeHtml(lockedTarget)}</span>
          <span class="lock-badge ${lockState}">${lockState.toUpperCase()}</span>
        </div>
        <div class="no-data">
          No damage assessment data
          <div class="no-data-hint">Press ASSESS to scan target</div>
        </div>
        <div class="footer">
          <button class="assess-btn" id="assess-btn">ASSESS TARGET</button>
        </div>
      `;
      this._bindAssessButton();
      return;
    }

    // Render full assessment display
    const data = this._assessmentData;
    const subsystems = data.subsystems || {};
    const quality = data.assessment_quality ?? 0;
    const qualityClass = quality > 0.7 ? "high" : quality > 0.4 ? "moderate" : "low";

    // Compute hull estimate: average of all subsystem health values that are known
    const hullEstimate = this._computeHullEstimate(subsystems);

    // Check for stale data (older than 15 seconds)
    const isStale = this._lastAssessTime && (Date.now() - this._lastAssessTime > 15000);

    let html = `
      <div class="target-header">
        <span class="target-name">${this._escapeHtml(data.target_id || lockedTarget)}</span>
        <span class="lock-badge ${lockState}">${lockState.toUpperCase()}</span>
      </div>
    `;

    // Hull integrity bar
    html += this._renderHullBar(hullEstimate);

    // Subsystem rows
    html += `<div class="subsystems-section">
      <div class="section-label">Subsystem Health</div>`;

    for (const { key, label } of SUBSYSTEM_ORDER) {
      const info = subsystems[key];
      if (info) {
        html += this._renderSubsystemRow(label, info);
      }
    }

    // Also render any subsystems not in our known list (future-proofing)
    for (const [key, info] of Object.entries(subsystems)) {
      if (!SUBSYSTEM_ORDER.find((s) => s.key === key)) {
        const label = key.charAt(0).toUpperCase() + key.slice(1);
        html += this._renderSubsystemRow(label, info);
      }
    }

    html += `</div>`;

    // Confidence footer
    html += `
      <div class="confidence-footer">
        <span>Sensor Confidence</span>
        <span class="quality-value ${qualityClass}">${Math.round(quality * 100)}%</span>
      </div>
    `;

    // Stale data warning
    if (isStale) {
      html += `<div class="stale-warning">Assessment data may be stale -- reassessing</div>`;
    }

    // Assess button + timestamp
    const timeStr = this._lastAssessTime
      ? this._formatTimestamp(this._lastAssessTime)
      : "";

    html += `
      <div class="footer">
        <button class="assess-btn ${this._assessing ? "assessing" : ""}" id="assess-btn"
                ${this._assessing ? "disabled" : ""}>
          ${this._assessing ? "SCANNING..." : "ASSESS TARGET"}
        </button>
        ${timeStr ? `<span class="assess-timestamp">@ ${timeStr}</span>` : ""}
      </div>
    `;

    content.innerHTML = html;
    this._bindAssessButton();
  }

  /** Compute an aggregate hull estimate from subsystem health values */
  _computeHullEstimate(subsystems) {
    let total = 0;
    let count = 0;
    for (const info of Object.values(subsystems)) {
      if (info.health != null) {
        total += info.health;
        count++;
      }
    }
    return count > 0 ? total / count : null;
  }

  _renderHullBar(hullEstimate) {
    if (hullEstimate == null) {
      return `
        <div class="hull-section">
          <div class="section-label">Hull Integrity</div>
          <div class="hull-bar-container">
            <div class="hull-bar-fill destroyed" style="width: 100%"></div>
            <span class="hull-bar-label">???</span>
          </div>
        </div>
      `;
    }

    const pct = Math.round(hullEstimate * 100);
    const colorClass = pct > 75 ? "green" : pct > 25 ? "yellow" : pct > 0 ? "red" : "destroyed";

    return `
      <div class="hull-section">
        <div class="section-label">Hull Integrity</div>
        <div class="hull-bar-container">
          <div class="hull-bar-fill ${colorClass}" style="width: ${Math.max(pct, 2)}%"></div>
          <span class="hull-bar-label">${pct}%</span>
        </div>
      </div>
    `;
  }

  _renderSubsystemRow(label, info) {
    const health = info.health;
    const status = info.status || "unknown";
    const confidence = info.confidence || "none";

    let pct, colorClass, displayValue;

    if (health != null) {
      pct = Math.round(health * 100);
      colorClass = pct > 75 ? "green" : pct > 25 ? "yellow" : pct > 0 ? "red" : "destroyed";
      displayValue = status === "destroyed" ? "DEAD" : `${pct}%`;
    } else {
      pct = 0;
      colorClass = "destroyed";
      displayValue = "???";
    }

    // Confidence indicator: single character showing data quality
    const confChar = { high: "H", moderate: "M", low: "L", none: "?" }[confidence] || "?";

    return `
      <div class="subsystem-row">
        <span class="subsys-name">${this._escapeHtml(label)}</span>
        <div class="subsys-bar-container">
          <div class="subsys-bar-fill ${colorClass}" style="width: ${health != null ? Math.max(pct, 2) : 0}%"></div>
        </div>
        <span class="subsys-value ${status === "unknown" ? "unknown" : colorClass}">${displayValue}</span>
        <span class="subsys-confidence ${confidence}" title="Confidence: ${confidence}">${confChar}</span>
      </div>
    `;
  }

  _formatTimestamp(ms) {
    const d = new Date(ms);
    const h = String(d.getHours()).padStart(2, "0");
    const m = String(d.getMinutes()).padStart(2, "0");
    const s = String(d.getSeconds()).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  _bindAssessButton() {
    const btn = this.shadowRoot.getElementById("assess-btn");
    if (btn) {
      btn.addEventListener("click", () => this._assessDamage());
    }
  }

  async _assessDamage() {
    if (this._assessing) return;

    this._assessing = true;
    this._updateDisplay();

    try {
      const response = await wsClient.sendShipCommand("assess_damage", {});
      if (response && response.ok) {
        this._assessmentData = response;
        this._lastAssessTime = Date.now();
      }
    } catch (error) {
      console.error("[target-assessment] assess_damage failed:", error);
    } finally {
      this._assessing = false;
      this._updateDisplay();
    }
  }

  _escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
}

customElements.define("target-assessment", TargetAssessment);
export { TargetAssessment };
