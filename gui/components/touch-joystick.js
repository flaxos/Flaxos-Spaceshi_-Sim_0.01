/**
 * Touch Joystick Component
 * Virtual joystick for heading control (yaw/pitch) on mobile devices.
 * Touch events only — designed for touchscreens.
 * Sends set_orientation commands via wsClient.sendShipCommand().
 *
 * The knob position maps to yaw (X) and pitch (Y) in degrees.
 * A dead zone in the center (5% of radius) prevents jitter.
 * Knob springs back to center on touch release.
 */

import { wsClient } from "../js/ws-client.js";

class TouchJoystick extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._isDragging = false;
    this._baseRect = null;
    this._centerX = 0;
    this._centerY = 0;
    this._radius = 0;
    this._knobX = 0;  // -1 to 1
    this._knobY = 0;  // -1 to 1

    // Max degrees per full deflection
    this._maxYaw = 180;
    this._maxPitch = 90;

    // Dead zone as fraction of radius
    this._deadZone = 0.05;

    // Command throttle: don't spam faster than 10 Hz
    this._lastSendTime = 0;
    this._sendInterval = 100;
    this._pendingSend = null;

    this._onTouchStart = this._handleTouchStart.bind(this);
    this._onTouchMove = this._handleTouchMove.bind(this);
    this._onTouchEnd = this._handleTouchEnd.bind(this);
  }

  connectedCallback() {
    this._render();
    this._bindEvents();
  }

  disconnectedCallback() {
    if (this._pendingSend) {
      clearTimeout(this._pendingSend);
      this._pendingSend = null;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 120px;
          height: 130px;
          user-select: none;
          -webkit-user-select: none;
          touch-action: none;
        }

        .joystick-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
        }

        .joystick-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 11px;
          font-weight: 600;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .joystick-base {
          position: relative;
          width: 100px;
          height: 100px;
          border-radius: 50%;
          background: var(--bg-input, #1a1a24);
          border: 2px solid var(--border-default, #2a2a3a);
          box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.3);
        }

        .crosshair-h, .crosshair-v { position: absolute; background: var(--border-default, #2a2a3a); pointer-events: none; }
        .crosshair-h { top: 50%; left: 15%; right: 15%; height: 1px; transform: translateY(-0.5px); }
        .crosshair-v { left: 50%; top: 15%; bottom: 15%; width: 1px; transform: translateX(-0.5px); }
        .dead-zone { position: absolute; top: 50%; left: 50%; width: 10%; height: 10%; border-radius: 50%;
          border: 1px solid var(--text-dim, #555566); transform: translate(-50%, -50%); pointer-events: none; opacity: 0.5; }

        .joystick-knob {
          position: absolute;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: var(--text-secondary, #888899);
          border: 2px solid var(--text-primary, #e0e0e0);
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          pointer-events: none;
          transition: background 0.1s ease;
          box-shadow: 0 0 8px rgba(0, 170, 255, 0.2);
        }

        .joystick-knob.dragging {
          background: var(--status-info, #00aaff);
          border-color: var(--text-bright, #ffffff);
          box-shadow: 0 0 12px rgba(0, 170, 255, 0.5);
        }

        .cardinal { position: absolute; font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 8px; color: var(--text-dim, #555566); pointer-events: none; }
        .cardinal.n { top: 3px; left: 50%; transform: translateX(-50%); }
        .cardinal.s { bottom: 3px; left: 50%; transform: translateX(-50%); }
        .cardinal.e { right: 5px; top: 50%; transform: translateY(-50%); }
        .cardinal.w { left: 5px; top: 50%; transform: translateY(-50%); }
        .joystick-readout { font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 10px; color: var(--text-secondary, #888899); text-align: center; min-height: 14px; }
      </style>

      <div class="joystick-wrapper">
        <span class="joystick-label">HDG</span>
        <div class="joystick-base">
          <div class="crosshair-h"></div>
          <div class="crosshair-v"></div>
          <div class="dead-zone"></div>
          <span class="cardinal n">P+</span>
          <span class="cardinal s">P-</span>
          <span class="cardinal e">Y+</span>
          <span class="cardinal w">Y-</span>
          <div class="joystick-knob"></div>
        </div>
        <span class="joystick-readout"></span>
      </div>
    `;
  }

  _bindEvents() {
    const base = this.shadowRoot.querySelector(".joystick-base");
    base.addEventListener("touchstart", this._onTouchStart, { passive: false });
    base.addEventListener("touchmove", this._onTouchMove, { passive: false });
    base.addEventListener("touchend", this._onTouchEnd, { passive: true });
    base.addEventListener("touchcancel", this._onTouchEnd, { passive: true });
  }

  _handleTouchStart(e) {
    e.preventDefault();
    this._isDragging = true;
    const base = this.shadowRoot.querySelector(".joystick-base");
    this._baseRect = base.getBoundingClientRect();
    this._centerX = this._baseRect.left + this._baseRect.width / 2;
    this._centerY = this._baseRect.top + this._baseRect.height / 2;
    this._radius = this._baseRect.width / 2;

    const knob = this.shadowRoot.querySelector(".joystick-knob");
    knob.classList.add("dragging");

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

    const knob = this.shadowRoot.querySelector(".joystick-knob");
    knob.classList.remove("dragging");

    // Spring back to center
    this._knobX = 0;
    this._knobY = 0;
    this._updateKnobVisual();
    this._updateReadout();

    this._baseRect = null;
  }

  /**
   * Map touch position to normalized knob coordinates (-1 to 1),
   * clamped to the circular base boundary.
   * @param {Touch} touch
   */
  _updateFromTouch(touch) {
    if (!this._baseRect) return;

    let dx = (touch.clientX - this._centerX) / this._radius;
    let dy = -(touch.clientY - this._centerY) / this._radius; // Invert Y: up = positive pitch

    // Clamp to unit circle
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist > 1) {
      dx /= dist;
      dy /= dist;
    }

    // Apply dead zone
    if (dist < this._deadZone) {
      dx = 0;
      dy = 0;
    }

    this._knobX = dx;
    this._knobY = dy;

    this._updateKnobVisual();
    this._updateReadout();
    this._throttledSend();
  }

  /**
   * Update the knob DOM position.
   */
  _updateKnobVisual() {
    const knob = this.shadowRoot.querySelector(".joystick-knob");
    if (!knob) return;

    // Map -1..1 to pixel offset from center (max = radius - knob radius)
    const maxOffset = 36; // ~half of base (50px) minus half of knob (14px)
    const px = this._knobX * maxOffset;
    const py = -this._knobY * maxOffset; // CSS Y is inverted
    knob.style.transform = `translate(calc(-50% + ${px}px), calc(-50% + ${py}px))`;
  }

  /**
   * Update the readout text below the joystick.
   */
  _updateReadout() {
    const readout = this.shadowRoot.querySelector(".joystick-readout");
    if (!readout) return;

    if (this._knobX === 0 && this._knobY === 0) {
      readout.textContent = "";
    } else {
      const yaw = (this._knobX * this._maxYaw).toFixed(0);
      const pitch = (this._knobY * this._maxPitch).toFixed(0);
      readout.textContent = `Y:${yaw} P:${pitch}`;
    }
  }

  /**
   * Rate-limited send of heading command.
   */
  _throttledSend() {
    const now = Date.now();
    if (now - this._lastSendTime >= this._sendInterval) {
      this._lastSendTime = now;
      this._sendHeading();
    } else if (!this._pendingSend) {
      const delay = this._sendInterval - (now - this._lastSendTime);
      this._pendingSend = setTimeout(() => {
        this._pendingSend = null;
        this._lastSendTime = Date.now();
        this._sendHeading();
      }, delay);
    }
  }

  /**
   * Send heading command to server.
   */
  _sendHeading() {
    // Only send if deflected past dead zone
    if (this._knobX === 0 && this._knobY === 0) return;

    const yaw = this._knobX * this._maxYaw;
    const pitch = this._knobY * this._maxPitch;

    wsClient.sendShipCommand("set_orientation", {
      yaw: Math.round(yaw),
      pitch: Math.round(pitch),
    }).catch((err) => {
      console.warn("Touch joystick command failed:", err.message);
    });
  }
}

customElements.define("touch-joystick", TouchJoystick);
export { TouchJoystick };
