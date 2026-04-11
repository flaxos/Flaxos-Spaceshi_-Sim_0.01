/**
 * ECM Frequency Game (ARCADE tier)
 *
 * Electronic warfare as a frequency-matching challenge. The enemy broadcasts
 * jamming on shifting frequencies; the player drags a filter band to match
 * and neutralize the signal. Cat-and-mouse signal tracking mini-game.
 *
 * State reads:
 *   ship.systems.sensors.eccm  — own ECCM status
 *   ship.targeting.ecm_detected — whether hostile ECM is active
 *
 * On successful match (>1s): sends eccm_frequency_hop command.
 * Actual ECCM effectiveness is server-authoritative.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

// Match state thresholds (filter width = 15% of spectrum)
const FILTER_WIDTH = 0.15;
const CLOSE_MULTIPLIER = 2; // "close" if signal within 2x filter half-width
const MATCH_HOLD_MS = 1000; // hold match for 1s to trigger command
const HOP_MIN_MS = 2000;
const HOP_MAX_MS = 5000;

class EcmFrequencyGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._signalPosition = 0.5; // 0-1 on spectrum
    this._filterPosition = 0.5;
    this._hopTimer = 0;
    this._hopInterval = 3000;
    this._nextHopTime = 0;
    this._matchState = "missed"; // "matched" | "close" | "missed"
    this._matchStart = 0; // timestamp when match began
    this._matchSent = false; // whether we sent the command for this match
    this._animFrame = null;
    this._lastFrameTime = 0;
    this._ecmActive = false;
    this._ecmPower = 0;
    this._dragging = false;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";
  }

  connectedCallback() {
    this._render();
    this._subscribe();
    this._setupInteraction();
    this._startLoop();

    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
    };
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._readState();
    });
  }

  /** Read ECM/ECCM state from server telemetry */
  _readState() {
    if (!this.offsetParent) return;
    const ship = stateManager.getShipState();
    if (!ship) return;

    const eccm = ship?.systems?.sensors?.eccm || ship?.eccm || {};
    const ecmDetected = ship?.targeting?.ecm_detected || false;
    const ownEcm = ship?.systems?.sensors?.ecm_active || false;
    const ownEccm = eccm?.mode && eccm.mode !== "off";

    this._ecmActive = ecmDetected || ownEcm || ownEccm;
    this._ecmPower = eccm?.jamming_strength || ship?.targeting?.ecm_strength || 0.5;

    // Adjust hop speed based on ECM sophistication
    const sophistication = Math.max(0.1, Math.min(1.0, this._ecmPower));
    this._hopInterval = HOP_MAX_MS - (HOP_MAX_MS - HOP_MIN_MS) * sophistication;

    this._updateIdleState();
  }

  /** Show/hide idle state when no EW activity */
  _updateIdleState() {
    const idle = this.shadowRoot.querySelector(".idle-state");
    const active = this.shadowRoot.querySelector(".game-container");
    if (!idle || !active) return;

    if (this._ecmActive) {
      idle.style.display = "none";
      active.style.display = "flex";
    } else {
      idle.style.display = "flex";
      active.style.display = "none";
    }
  }

  /** Seeded pseudo-random hop target based on time */
  _hopSignal(now) {
    if (now < this._nextHopTime) return;

    // New random position, biased away from current position for variety
    const oldPos = this._signalPosition;
    let newPos;
    do {
      newPos = Math.random();
    } while (Math.abs(newPos - oldPos) < 0.2);

    this._signalPosition = newPos;
    this._nextHopTime = now + this._hopInterval;
    this._matchSent = false; // reset command flag on hop
  }

  /** Evaluate match state between filter and signal */
  _evaluateMatch() {
    const halfFilter = FILTER_WIDTH / 2;
    const dist = Math.abs(this._filterPosition - this._signalPosition);

    let newState;
    if (dist <= halfFilter) {
      newState = "matched";
    } else if (dist <= halfFilter * CLOSE_MULTIPLIER) {
      newState = "close";
    } else {
      newState = "missed";
    }

    const now = performance.now();

    if (newState === "matched") {
      if (this._matchState !== "matched") {
        this._matchStart = now;
      }
      // Send command after sustained match
      if (!this._matchSent && (now - this._matchStart) >= MATCH_HOLD_MS) {
        wsClient.sendShipCommand("eccm_frequency_hop", {});
        this._matchSent = true;
      }
    } else {
      this._matchStart = 0;
    }

    this._matchState = newState;
  }

  /** Main animation loop */
  _startLoop() {
    const loop = (timestamp) => {
      this._animFrame = requestAnimationFrame(loop);

      if (this._ecmActive) {
        this._hopSignal(timestamp);
        this._evaluateMatch();
      }

      this._updateVisuals(timestamp);
    };
    this._animFrame = requestAnimationFrame(loop);
  }

  /** Update all visual elements each frame */
  _updateVisuals(timestamp) {
    const signal = this.shadowRoot.querySelector(".signal-spike");
    const filter = this.shadowRoot.querySelector(".filter-band");
    const statusText = this.shadowRoot.querySelector(".match-status-text");
    const statusDot = this.shadowRoot.querySelector(".match-status-dot");
    const container = this.shadowRoot.querySelector(".spectrum-bar");
    const strengthFill = this.shadowRoot.querySelector(".strength-fill");
    const matchProgress = this.shadowRoot.querySelector(".match-progress");

    if (!signal || !filter || !container) return;

    // Position signal spike with wobble
    const wobble = Math.sin(timestamp * 0.008) * 0.005;
    const signalPx = (this._signalPosition + wobble) * 100;
    signal.style.left = `${signalPx}%`;

    // Position filter band
    const filterPx = this._filterPosition * 100;
    filter.style.left = `${filterPx - (FILTER_WIDTH * 100) / 2}%`;

    // Match status indicator
    if (statusText && statusDot) {
      if (this._matchState === "matched") {
        const holdTime = performance.now() - this._matchStart;
        if (this._matchSent || holdTime >= MATCH_HOLD_MS) {
          statusText.textContent = "JAMMING NEUTRALIZED";
          statusDot.className = "match-status-dot matched-locked";
        } else {
          statusText.textContent = "JAMMING...";
          statusDot.className = "match-status-dot matched";
        }
      } else if (this._matchState === "close") {
        statusText.textContent = "PARTIAL";
        statusDot.className = "match-status-dot close";
      } else {
        statusText.textContent = "EVADED";
        statusDot.className = "match-status-dot missed";
      }
    }

    // Match progress bar (fill over MATCH_HOLD_MS)
    if (matchProgress) {
      if (this._matchState === "matched" && !this._matchSent) {
        const holdTime = performance.now() - this._matchStart;
        const pct = Math.min(1, holdTime / MATCH_HOLD_MS) * 100;
        matchProgress.style.width = `${pct}%`;
        matchProgress.style.opacity = "1";
      } else if (this._matchSent) {
        matchProgress.style.width = "100%";
        matchProgress.style.opacity = "1";
      } else {
        matchProgress.style.width = "0%";
        matchProgress.style.opacity = "0.3";
      }
    }

    // Signal strength meter
    if (strengthFill) {
      strengthFill.style.height = `${this._ecmPower * 100}%`;
    }

    // Container border glow
    if (container) {
      container.classList.remove("glow-green", "glow-yellow", "glow-red");
      if (this._ecmActive) {
        if (this._matchState === "matched") {
          container.classList.add("glow-green");
        } else if (this._matchState === "close") {
          container.classList.add("glow-yellow");
        } else {
          container.classList.add("glow-red");
        }
      }
    }
  }

  /** Set up mouse/touch interaction for filter dragging */
  _setupInteraction() {
    const bar = this.shadowRoot.querySelector(".spectrum-bar");
    if (!bar) return;

    const updateFilter = (clientX) => {
      const rect = bar.getBoundingClientRect();
      const x = (clientX - rect.left) / rect.width;
      this._filterPosition = Math.max(0, Math.min(1, x));
    };

    // Mouse — filter follows cursor position (no click needed, just hover)
    bar.addEventListener("mousemove", (e) => {
      updateFilter(e.clientX);
    });

    const stopDrag = () => { this._dragging = false; };
    bar.addEventListener("mouseup", stopDrag);
    bar.addEventListener("mouseleave", stopDrag);

    // Touch
    bar.addEventListener("touchstart", (e) => {
      e.preventDefault();
      this._dragging = true;
      updateFilter(e.touches[0].clientX);
    });
    bar.addEventListener("touchmove", (e) => {
      e.preventDefault();
      if (this._dragging) {
        updateFilter(e.touches[0].clientX);
      }
    });
    bar.addEventListener("touchend", stopDrag);
    bar.addEventListener("touchcancel", stopDrag);
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 0;
        }

        .ecm-game-root {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 12px;
        }

        /* --- Idle state --- */
        .idle-state {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 80px;
          color: #445;
          font-size: 0.75rem;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          border: 1px dashed #1a1a2e;
          border-radius: 3px;
        }

        .idle-state .idle-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #334;
          margin-right: 8px;
        }

        /* --- Active game container --- */
        .game-container {
          display: flex;
          gap: 10px;
          align-items: stretch;
        }

        .spectrum-column {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        /* --- Match status row --- */
        .match-status {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 0;
        }

        .match-status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #334;
          transition: background 0.2s, box-shadow 0.2s;
        }
        .match-status-dot.matched {
          background: #0f0;
          box-shadow: 0 0 6px rgba(0, 255, 0, 0.5);
        }
        .match-status-dot.matched-locked {
          background: #0f0;
          box-shadow: 0 0 12px rgba(0, 255, 0, 0.8);
          animation: pulse-green 0.6s ease-in-out infinite alternate;
        }
        .match-status-dot.close {
          background: #fc0;
          box-shadow: 0 0 6px rgba(255, 200, 0, 0.5);
        }
        .match-status-dot.missed {
          background: #f33;
          box-shadow: 0 0 6px rgba(255, 50, 50, 0.5);
        }

        @keyframes pulse-green {
          from { box-shadow: 0 0 8px rgba(0, 255, 0, 0.6); }
          to   { box-shadow: 0 0 20px rgba(0, 255, 0, 1.0); }
        }

        .match-status-text {
          font-size: 0.7rem;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: #99a;
          font-weight: 600;
        }

        /* --- Match progress bar --- */
        .match-progress-track {
          height: 3px;
          background: #0a0a14;
          border-radius: 2px;
          overflow: hidden;
        }

        .match-progress {
          height: 100%;
          width: 0%;
          background: linear-gradient(90deg, #0a4, #0f0);
          border-radius: 2px;
          transition: width 0.1s linear, opacity 0.3s;
          opacity: 0.3;
        }

        /* --- Spectrum bar (main interaction area) --- */
        .spectrum-bar {
          position: relative;
          height: 64px;
          background: #060610;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          overflow: hidden;
          cursor: crosshair;
          user-select: none;
          touch-action: none;
          transition: border-color 0.3s, box-shadow 0.3s;
        }

        .spectrum-bar.glow-green {
          border-color: rgba(0, 255, 0, 0.3);
          box-shadow: inset 0 0 20px rgba(0, 255, 0, 0.05), 0 0 8px rgba(0, 255, 0, 0.1);
        }
        .spectrum-bar.glow-yellow {
          border-color: rgba(255, 200, 0, 0.3);
          box-shadow: inset 0 0 20px rgba(255, 200, 0, 0.05), 0 0 8px rgba(255, 200, 0, 0.08);
        }
        .spectrum-bar.glow-red {
          border-color: rgba(255, 50, 50, 0.3);
          box-shadow: inset 0 0 20px rgba(255, 50, 50, 0.05), 0 0 8px rgba(255, 50, 50, 0.08);
        }

        /* Noise floor grain */
        .noise-floor {
          position: absolute;
          inset: 0;
          background: repeating-linear-gradient(
            90deg,
            transparent 0px,
            rgba(40, 40, 60, 0.08) 1px,
            transparent 2px,
            transparent 6px
          );
          pointer-events: none;
          z-index: 0;
          animation: noise-shift 4s linear infinite;
        }

        @keyframes noise-shift {
          from { background-position: 0 0; }
          to   { background-position: 24px 0; }
        }

        /* Grid lines */
        .grid-lines {
          position: absolute;
          inset: 0;
          pointer-events: none;
          z-index: 0;
        }
        .grid-line {
          position: absolute;
          top: 0;
          bottom: 0;
          width: 1px;
          background: rgba(60, 60, 80, 0.2);
        }

        /* Frequency labels */
        .freq-labels {
          display: flex;
          justify-content: space-between;
          padding: 0 2px;
        }
        .freq-label {
          font-size: 0.55rem;
          letter-spacing: 0.1em;
          color: #445;
          text-transform: uppercase;
        }

        /* --- Enemy signal spike --- */
        .signal-spike {
          position: absolute;
          top: 4px;
          bottom: 4px;
          width: 4px;
          margin-left: -2px;
          z-index: 3;
          pointer-events: none;
          transition: left 0.15s ease-out;
        }

        .signal-spike-line {
          position: absolute;
          inset: 0;
          background: #f33;
          border-radius: 2px;
          box-shadow: 0 0 8px rgba(255, 50, 50, 0.6), 0 0 16px rgba(255, 50, 50, 0.3);
        }

        .signal-spike-glow {
          position: absolute;
          top: -2px;
          bottom: -2px;
          left: -6px;
          right: -6px;
          background: radial-gradient(ellipse at center, rgba(255, 50, 50, 0.25), transparent 70%);
          animation: spike-wobble 0.8s ease-in-out infinite alternate;
        }

        @keyframes spike-wobble {
          from { opacity: 0.6; transform: scaleX(0.8); }
          to   { opacity: 1.0; transform: scaleX(1.2); }
        }

        /* --- Player filter band --- */
        .filter-band {
          position: absolute;
          top: 0;
          bottom: 0;
          width: ${FILTER_WIDTH * 100}%;
          z-index: 2;
          pointer-events: none;
          transition: left 0.05s linear;
          background: rgba(50, 120, 255, 0.12);
          border-left: 1px solid rgba(50, 120, 255, 0.4);
          border-right: 1px solid rgba(50, 120, 255, 0.4);
        }

        .filter-band-label {
          position: absolute;
          top: 3px;
          left: 50%;
          transform: translateX(-50%);
          font-size: 0.5rem;
          color: rgba(80, 150, 255, 0.6);
          letter-spacing: 0.1em;
          text-transform: uppercase;
          white-space: nowrap;
        }

        .filter-center {
          position: absolute;
          top: 0;
          bottom: 0;
          left: 50%;
          width: 1px;
          background: rgba(50, 120, 255, 0.5);
        }

        /* --- Signal strength meter (vertical bar) --- */
        .strength-meter {
          width: 20px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          flex-shrink: 0;
        }

        .strength-label {
          font-size: 0.5rem;
          letter-spacing: 0.08em;
          color: #556;
          text-transform: uppercase;
          writing-mode: vertical-lr;
          text-orientation: mixed;
          transform: rotate(180deg);
        }

        .strength-track {
          flex: 1;
          width: 8px;
          background: #0a0a14;
          border: 1px solid #1a1a2e;
          border-radius: 2px;
          position: relative;
          overflow: hidden;
          min-height: 50px;
        }

        .strength-fill {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 50%;
          background: linear-gradient(0deg, #f33, #f80);
          border-radius: 0 0 1px 1px;
          transition: height 0.5s ease;
        }
      </style>

      <div class="ecm-game-root">
        <!-- Idle state: no electronic warfare happening -->
        <div class="idle-state">
          <span class="idle-dot"></span>
          EW CLEAR
        </div>

        <!-- Active game -->
        <div class="game-container" style="display: none;">
          <div class="spectrum-column">
            <!-- Match status -->
            <div class="match-status">
              <span class="match-status-dot missed"></span>
              <span class="match-status-text">EVADED</span>
            </div>

            <!-- Match progress bar -->
            <div class="match-progress-track">
              <div class="match-progress"></div>
            </div>

            <!-- Spectrum bar -->
            <div class="spectrum-bar">
              <div class="noise-floor"></div>

              <!-- Grid lines at 25%, 50%, 75% -->
              <div class="grid-lines">
                <div class="grid-line" style="left: 25%;"></div>
                <div class="grid-line" style="left: 50%;"></div>
                <div class="grid-line" style="left: 75%;"></div>
              </div>

              <!-- Enemy signal -->
              <div class="signal-spike">
                <div class="signal-spike-glow"></div>
                <div class="signal-spike-line"></div>
              </div>

              <!-- Player filter band -->
              <div class="filter-band">
                <div class="filter-band-label">ECCM</div>
                <div class="filter-center"></div>
              </div>
            </div>

            <!-- Frequency labels -->
            <div class="freq-labels">
              <span class="freq-label">LOW</span>
              <span class="freq-label">MID</span>
              <span class="freq-label">HIGH</span>
            </div>
          </div>

          <!-- Signal strength meter -->
          <div class="strength-meter">
            <div class="strength-track">
              <div class="strength-fill"></div>
            </div>
            <span class="strength-label">SIG</span>
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define("ecm-frequency-game", EcmFrequencyGame);
