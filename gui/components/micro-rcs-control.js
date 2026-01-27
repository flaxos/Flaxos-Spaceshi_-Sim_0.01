/**
 * Micro RCS Control
 * Fine attitude adjustment controls for precision maneuvering
 *
 * Sprint C: Combat Controls - Placeholder Implementation
 * This component will provide fine-grained RCS control for:
 * - Precision docking maneuvers
 * - Weapons platform stabilization
 * - Fine attitude trimming
 */

import { stateManager } from "../js/state-manager.js";

class MicroRcsControl extends HTMLElement {
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
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .placeholder-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 120px;
          padding: 24px;
          background: rgba(0, 0, 0, 0.2);
          border: 1px dashed var(--border-default, #2a2a3a);
          border-radius: 8px;
          text-align: center;
        }

        .placeholder-icon {
          font-size: 2rem;
          margin-bottom: 12px;
          opacity: 0.5;
        }

        .placeholder-title {
          font-size: 0.85rem;
          font-weight: 600;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .placeholder-description {
          font-size: 0.75rem;
          color: var(--text-dim, #555566);
          line-height: 1.4;
          max-width: 250px;
        }

        .sprint-badge {
          display: inline-block;
          margin-top: 12px;
          padding: 4px 8px;
          background: rgba(255, 170, 0, 0.15);
          border: 1px solid var(--status-warning, #ffaa00);
          border-radius: 4px;
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--status-warning, #ffaa00);
        }

        .current-attitude {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
          text-align: center;
          margin-bottom: 16px;
        }

        .attitude-item {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .attitude-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-bottom: 2px;
        }

        .attitude-value {
          font-size: 0.85rem;
          color: var(--text-secondary, #888899);
        }
      </style>

      <!-- Current Attitude (read-only for now) -->
      <div class="current-attitude">
        <div class="attitude-item">
          <div class="attitude-label">Pitch</div>
          <div class="attitude-value" id="current-pitch">+0.0°</div>
        </div>
        <div class="attitude-item">
          <div class="attitude-label">Yaw</div>
          <div class="attitude-value" id="current-yaw">000.0°</div>
        </div>
        <div class="attitude-item">
          <div class="attitude-label">Roll</div>
          <div class="attitude-value" id="current-roll">+0.0°</div>
        </div>
      </div>

      <!-- Placeholder for future implementation -->
      <div class="placeholder-container">
        <div class="placeholder-icon">+</div>
        <div class="placeholder-title">Micro RCS Controls</div>
        <div class="placeholder-description">
          Fine attitude adjustment controls for precision maneuvering,
          docking operations, and weapons platform stabilization.
        </div>
        <div class="sprint-badge">Sprint C: Combat Controls</div>
      </div>
    `;
  }

  _updateDisplay() {
    const nav = stateManager.getNavigation();
    const heading = nav.heading || { pitch: 0, yaw: 0, roll: 0 };

    // Update current attitude display
    const pitchEl = this.shadowRoot.getElementById("current-pitch");
    const yawEl = this.shadowRoot.getElementById("current-yaw");
    const rollEl = this.shadowRoot.getElementById("current-roll");

    if (pitchEl) {
      const pitchSign = heading.pitch >= 0 ? "+" : "";
      pitchEl.textContent = `${pitchSign}${(heading.pitch || 0).toFixed(1)}°`;
    }

    if (yawEl) {
      const yawNorm = ((heading.yaw || 0) + 360) % 360;
      yawEl.textContent = `${yawNorm.toFixed(1).padStart(5, "0")}°`;
    }

    if (rollEl) {
      const rollSign = (heading.roll || 0) >= 0 ? "+" : "";
      rollEl.textContent = `${rollSign}${(heading.roll || 0).toFixed(1)}°`;
    }
  }
}

customElements.define("micro-rcs-control", MicroRcsControl);
export { MicroRcsControl };
