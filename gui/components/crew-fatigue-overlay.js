/**
 * Crew Fatigue Overlay Component
 *
 * Full-screen overlay that appears during crew blackout and shows
 * impairment warnings when performance degrades. This is a safety
 * display — it tells the player their crew is physically compromised.
 *
 * States:
 * - Hidden: performance >= 0.85, no blackout
 * - Amber warning: performance < 0.85 (vignette + status text)
 * - Blackout: is_blacked_out === true (dark overlay, pulsing text, recovery bar)
 */

import { stateManager } from "../js/state-manager.js";

const IMPAIRMENT_THRESHOLD = 0.85;

class CrewFatigueOverlay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._lastState = "hidden";
  }

  connectedCallback() {
    this._render();
    this._unsubscribe = stateManager.subscribe("*", () => this._update());
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          pointer-events: none;
          z-index: 9000;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .overlay {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          display: none;
          justify-content: center;
          align-items: center;
          flex-direction: column;
          transition: opacity 0.5s ease;
        }

        /* Amber impairment vignette */
        .overlay.warning {
          display: flex;
          background: radial-gradient(
            ellipse at center,
            transparent 40%,
            rgba(255, 170, 0, 0.08) 70%,
            rgba(255, 170, 0, 0.15) 100%
          );
          border: 2px solid transparent;
          box-shadow: inset 0 0 80px rgba(255, 170, 0, 0.06);
        }

        /* Blackout: dark overlay blocks visibility */
        .overlay.blackout {
          display: flex;
          background: radial-gradient(
            ellipse at center,
            rgba(0, 0, 0, 0.75) 20%,
            rgba(0, 0, 0, 0.92) 60%,
            rgba(0, 0, 0, 0.98) 100%
          );
          pointer-events: auto;
        }

        .blackout-content {
          text-align: center;
          color: #ff4444;
        }

        .blackout-title {
          font-size: 2.5rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 6px;
          animation: pulse-text 1.2s ease-in-out infinite;
          margin-bottom: 16px;
        }

        .blackout-subtitle {
          font-size: 0.9rem;
          color: #ff8888;
          letter-spacing: 2px;
          text-transform: uppercase;
          margin-bottom: 32px;
        }

        .g-readout {
          font-size: 3rem;
          font-weight: 700;
          color: #ff6666;
          margin-bottom: 8px;
        }

        .g-label {
          font-size: 0.7rem;
          color: #666;
          text-transform: uppercase;
          letter-spacing: 1px;
          margin-bottom: 32px;
        }

        .recovery-container {
          width: 300px;
        }

        .recovery-label {
          font-size: 0.7rem;
          color: #888;
          text-transform: uppercase;
          letter-spacing: 1px;
          margin-bottom: 8px;
          display: flex;
          justify-content: space-between;
        }

        .recovery-bar {
          height: 6px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 3px;
          overflow: hidden;
        }

        .recovery-fill {
          height: 100%;
          background: #ff4444;
          border-radius: 3px;
          transition: width 0.3s ease;
        }

        /* Warning banner (shown during impairment, not blackout) */
        .warning-banner {
          position: absolute;
          top: 48px;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(255, 170, 0, 0.12);
          border: 1px solid rgba(255, 170, 0, 0.4);
          border-radius: 6px;
          padding: 8px 24px;
          display: flex;
          align-items: center;
          gap: 12px;
          backdrop-filter: blur(4px);
        }

        .warning-icon {
          font-size: 1.1rem;
          color: #ffaa00;
        }

        .warning-text {
          font-size: 0.75rem;
          color: #ffaa00;
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .warning-perf {
          font-weight: 700;
          font-size: 0.85rem;
        }

        @keyframes pulse-text {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      </style>

      <div class="overlay" id="overlay">
        <!-- Blackout content (shown during blackout) -->
        <div class="blackout-content" id="blackout-content" style="display:none;">
          <div class="blackout-title">CREW BLACKOUT</div>
          <div class="blackout-subtitle">Manual operations suspended</div>
          <div class="g-readout" id="g-readout">0.0g</div>
          <div class="g-label">Current G-Load</div>
          <div class="recovery-container">
            <div class="recovery-label">
              <span>RECOVERY</span>
              <span id="recovery-time">0s</span>
            </div>
            <div class="recovery-bar">
              <div class="recovery-fill" id="recovery-fill" style="width:0%"></div>
            </div>
          </div>
        </div>

        <!-- Warning banner (shown during impairment) -->
        <div class="warning-banner" id="warning-banner" style="display:none;">
          <span class="warning-icon">!</span>
          <span class="warning-text">
            CREW IMPAIRED — G-LOAD/FATIGUE DEGRADING PERFORMANCE TO
            <span class="warning-perf" id="warning-perf">0%</span>
          </span>
        </div>
      </div>
    `;
  }

  _update() {
    const ship = stateManager.getShipState();
    if (!ship) return;

    const cf = ship.crew_fatigue || ship.systems?.crew_fatigue;
    const overlay = this.shadowRoot.getElementById("overlay");
    const blackoutContent = this.shadowRoot.getElementById("blackout-content");
    const warningBanner = this.shadowRoot.getElementById("warning-banner");

    if (!cf || !cf.enabled) {
      overlay.className = "overlay";
      blackoutContent.style.display = "none";
      warningBanner.style.display = "none";
      return;
    }

    const isBlackedOut = cf.is_blacked_out ?? false;
    const perf = cf.performance ?? 1;
    const gLoad = cf.g_load ?? 0;
    const recovery = cf.blackout_recovery ?? 0;
    const blackoutTimer = cf.blackout_timer ?? 0;

    if (isBlackedOut) {
      overlay.className = "overlay blackout";
      blackoutContent.style.display = "block";
      warningBanner.style.display = "none";

      this.shadowRoot.getElementById("g-readout").textContent =
        `${gLoad.toFixed(1)}g`;
      this.shadowRoot.getElementById("recovery-time").textContent =
        `${recovery.toFixed(0)}s`;

      // Recovery bar: 15s max recovery time
      const maxRecovery = 15;
      const pct = Math.max(0, Math.min(100, (1 - recovery / maxRecovery) * 100));
      this.shadowRoot.getElementById("recovery-fill").style.width = `${pct}%`;
    } else if (perf < IMPAIRMENT_THRESHOLD) {
      overlay.className = "overlay warning";
      blackoutContent.style.display = "none";
      warningBanner.style.display = "flex";

      this.shadowRoot.getElementById("warning-perf").textContent =
        `${(perf * 100).toFixed(0)}%`;
    } else {
      overlay.className = "overlay";
      blackoutContent.style.display = "none";
      warningBanner.style.display = "none";
    }
  }
}

customElements.define("crew-fatigue-overlay", CrewFatigueOverlay);
export { CrewFatigueOverlay };
