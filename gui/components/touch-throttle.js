/**
 * Touch Throttle Component
 * Vertical slider for thrust control (0-100%) on mobile devices.
 * Touch events only — designed for touchscreens.
 * Sends set_thrust commands via wsClient.sendShipCommand().
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

class TouchThrottle extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._throttle = 0;       // 0.0 - 1.0
    this._isDragging = false;
    this._trackRect = null;
    this._unsub = null;

    // Bound handlers for cleanup
    this._onTouchStart = this._handleTouchStart.bind(this);
    this._onTouchMove = this._handleTouchMove.bind(this);
    this._onTouchEnd = this._handleTouchEnd.bind(this);
  }

  connectedCallback() {
    this._render();
    this._bindEvents();
    // Subscribe to state updates for current throttle
    this._unsub = stateManager.subscribe("*", () => {
      if (!this._isDragging) this._syncFromState();
    });
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: flex-end;
          width: 70px;
          height: 160px;
          user-select: none;
          -webkit-user-select: none;
          touch-action: none;
        }

        .throttle-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
          width: 100%;
          height: 100%;
        }

        .throttle-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 11px;
          font-weight: 600;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .throttle-track {
          position: relative;
          width: 40px;
          height: 120px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          overflow: hidden;
        }

        .throttle-fill {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          background: var(--status-info, #00aaff);
          border-radius: 0 0 5px 5px;
          transition: height 0.05s linear;
          pointer-events: none;
        }

        /* Tick marks along the track */
        .throttle-ticks {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          pointer-events: none;
        }

        .tick {
          position: absolute;
          right: 0;
          width: 8px;
          height: 1px;
          background: var(--border-default, #2a2a3a);
        }

        .tick.major {
          width: 12px;
          background: var(--text-dim, #555566);
        }

        .throttle-thumb {
          position: absolute;
          left: 2px;
          right: 2px;
          height: 8px;
          background: var(--text-bright, #ffffff);
          border-radius: 3px;
          transform: translateY(50%);
          pointer-events: none;
          box-shadow: 0 0 6px rgba(0, 170, 255, 0.4);
        }

        .throttle-thumb.dragging {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
        }

        .throttle-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 13px;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          min-width: 3em;
          text-align: center;
        }
      </style>

      <div class="throttle-wrapper">
        <span class="throttle-label">THR</span>
        <div class="throttle-track">
          <div class="throttle-ticks">
            ${this._renderTicks()}
          </div>
          <div class="throttle-fill"></div>
          <div class="throttle-thumb"></div>
        </div>
        <span class="throttle-value">0%</span>
      </div>
    `;
  }

  /**
   * Render tick marks at 0%, 25%, 50%, 75%, 100%.
   */
  _renderTicks() {
    const ticks = [];
    for (let i = 0; i <= 4; i++) {
      const pct = i * 25;
      // Bottom = 0%, Top = 100%. CSS bottom percentage.
      const isMajor = pct === 0 || pct === 50 || pct === 100;
      ticks.push(
        `<div class="tick${isMajor ? " major" : ""}" style="bottom: ${pct}%"></div>`
      );
    }
    return ticks.join("");
  }

  _bindEvents() {
    const track = this.shadowRoot.querySelector(".throttle-track");
    track.addEventListener("touchstart", this._onTouchStart, { passive: false });
    track.addEventListener("touchmove", this._onTouchMove, { passive: false });
    track.addEventListener("touchend", this._onTouchEnd, { passive: true });
    track.addEventListener("touchcancel", this._onTouchEnd, { passive: true });
  }

  _handleTouchStart(e) {
    e.preventDefault();
    this._isDragging = true;
    const track = this.shadowRoot.querySelector(".throttle-track");
    this._trackRect = track.getBoundingClientRect();
    const thumb = this.shadowRoot.querySelector(".throttle-thumb");
    thumb.classList.add("dragging");
    this._updateFromTouch(e.touches[0]);
  }

  _handleTouchMove(e) {
    if (!this._isDragging) return;
    e.preventDefault();
    this._updateFromTouch(e.touches[0]);
  }

  _handleTouchEnd() {
    if (!this._isDragging) return;
    this._isDragging = false;
    const thumb = this.shadowRoot.querySelector(".throttle-thumb");
    thumb.classList.remove("dragging");
    this._trackRect = null;
    // Send final throttle value
    this._sendThrottle();
  }

  /**
   * Map touch Y position to throttle value (bottom=0, top=1).
   * @param {Touch} touch
   */
  _updateFromTouch(touch) {
    if (!this._trackRect) return;
    const rect = this._trackRect;
    // Y relative to track, inverted (bottom = 0)
    const relY = rect.bottom - touch.clientY;
    const ratio = Math.max(0, Math.min(1, relY / rect.height));

    // Quantize to 1% steps to reduce command spam
    const quantized = Math.round(ratio * 100) / 100;
    if (quantized !== this._throttle) {
      this._throttle = quantized;
      this._updateVisuals();
      this._sendThrottle();
    }
  }

  _updateVisuals() {
    const fill = this.shadowRoot.querySelector(".throttle-fill");
    const thumb = this.shadowRoot.querySelector(".throttle-thumb");
    const valueEl = this.shadowRoot.querySelector(".throttle-value");
    if (!fill || !thumb || !valueEl) return;

    const pct = this._throttle * 100;
    fill.style.height = `${pct}%`;
    // Thumb positioned from bottom
    thumb.style.bottom = `${pct}%`;
    valueEl.textContent = `${Math.round(pct)}%`;

    // Color coding: low=blue, mid=green, high=orange/red
    if (pct > 90) {
      fill.style.background = "var(--status-critical, #ff4444)";
    } else if (pct > 70) {
      fill.style.background = "var(--status-warning, #ffaa00)";
    } else if (pct > 30) {
      fill.style.background = "var(--status-nominal, #00ff88)";
    } else {
      fill.style.background = "var(--status-info, #00aaff)";
    }
  }

  /**
   * Send throttle command to server.
   */
  _sendThrottle() {
    wsClient.sendShipCommand("set_thrust", { thrust: this._throttle }).catch((err) => {
      console.warn("Touch throttle command failed:", err.message);
    });
  }

  /**
   * Sync throttle display from server state (when not dragging).
   */
  _syncFromState() {
    const ship = stateManager.getShipState();
    const thrust = ship?.thrust ?? ship?.throttle ?? null;
    if (thrust !== null && typeof thrust === "number") {
      this._throttle = Math.max(0, Math.min(1, thrust));
      this._updateVisuals();
    }
  }
}

customElements.define("touch-throttle", TouchThrottle);
export { TouchThrottle };
