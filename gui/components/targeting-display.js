/**
 * Targeting Computer Display
 * Shows target lock status, firing solution, TCA/CPA
 */

import { stateManager } from "../js/state-manager.js";

class TargetingDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._contactSelectedHandler = null;
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
      content.innerHTML = `
        <div class="no-lock">
          <div class="no-lock-icon">○</div>
          <div class="no-lock-text">NO TARGET LOCK</div>
          <div class="no-lock-hint">Select a contact from Sensors panel</div>
        </div>
      `;
      return;
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
    `;
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
