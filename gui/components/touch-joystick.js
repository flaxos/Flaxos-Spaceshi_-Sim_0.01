/**
 * Touch Joystick Component
 * Phase 6: Mobile Optimization
 * 
 * Virtual joystick for pitch/yaw control.
 * X-axis controls yaw, Y-axis controls pitch.
 * Returns to center on release.
 */

class TouchJoystick extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    
    this._x = 0; // -1 to 1 (yaw)
    this._y = 0; // -1 to 1 (pitch)
    this._isDragging = false;
    this._centerX = 0;
    this._centerY = 0;
    this._maxDistance = 50;
    this._sendInterval = null;
  }

  connectedCallback() {
    this.render();
    this._setupListeners();
  }

  disconnectedCallback() {
    if (this._sendInterval) {
      clearInterval(this._sendInterval);
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          width: 140px;
          height: 140px;
          touch-action: none;
          user-select: none;
        }

        .joystick-container {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
        }

        .joystick-label {
          font-size: 10px;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .joystick-base {
          width: 120px;
          height: 120px;
          background: var(--bg-input, #1a1a24);
          border: 2px solid var(--border-default, #2a2a3a);
          border-radius: 50%;
          position: relative;
          overflow: visible;
        }

        .joystick-crosshair {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          width: 80%;
          height: 80%;
          pointer-events: none;
        }

        .crosshair-line {
          position: absolute;
          background: var(--border-default, #2a2a3a);
        }

        .crosshair-h {
          width: 100%;
          height: 1px;
          top: 50%;
          left: 0;
        }

        .crosshair-v {
          width: 1px;
          height: 100%;
          left: 50%;
          top: 0;
        }

        .joystick-thumb {
          position: absolute;
          width: 40px;
          height: 40px;
          background: radial-gradient(circle at 30% 30%, var(--text-primary, #e0e0e0), var(--text-secondary, #888899));
          border-radius: 50%;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          cursor: grab;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
          transition: transform 0.15s ease, box-shadow 0.15s ease;
        }

        .joystick-thumb:active,
        :host(.dragging) .joystick-thumb {
          cursor: grabbing;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
        }

        :host(.dragging) .joystick-base {
          border-color: var(--status-info, #00aaff);
        }

        .joystick-values {
          display: flex;
          gap: 12px;
          font-family: var(--font-mono, monospace);
          font-size: 11px;
          color: var(--text-secondary, #888899);
        }

        .value-label {
          color: var(--text-dim, #555566);
        }

        /* Direction indicators */
        .direction-indicator {
          position: absolute;
          font-size: 8px;
          color: var(--text-dim, #555566);
        }

        .dir-up { top: 4px; left: 50%; transform: translateX(-50%); }
        .dir-down { bottom: 4px; left: 50%; transform: translateX(-50%); }
        .dir-left { left: 4px; top: 50%; transform: translateY(-50%); }
        .dir-right { right: 4px; top: 50%; transform: translateY(-50%); }
      </style>
      
      <div class="joystick-container">
        <span class="joystick-label">Heading</span>
        <div class="joystick-base" id="base">
          <div class="joystick-crosshair">
            <div class="crosshair-line crosshair-h"></div>
            <div class="crosshair-line crosshair-v"></div>
          </div>
          <div class="direction-indicator dir-up">P+</div>
          <div class="direction-indicator dir-down">P-</div>
          <div class="direction-indicator dir-left">Y-</div>
          <div class="direction-indicator dir-right">Y+</div>
          <div class="joystick-thumb" id="thumb"></div>
        </div>
        <div class="joystick-values">
          <span><span class="value-label">P:</span> <span id="pitch-value">0°</span></span>
          <span><span class="value-label">Y:</span> <span id="yaw-value">0°</span></span>
        </div>
      </div>
    `;
  }

  _setupListeners() {
    const base = this.shadowRoot.getElementById("base");
    const thumb = this.shadowRoot.getElementById("thumb");

    // Touch events
    base.addEventListener("touchstart", (e) => this._handleTouchStart(e));
    base.addEventListener("touchmove", (e) => this._handleTouchMove(e));
    base.addEventListener("touchend", (e) => this._handleTouchEnd(e));
    base.addEventListener("touchcancel", (e) => this._handleTouchEnd(e));

    // Mouse events for desktop testing
    base.addEventListener("mousedown", (e) => this._handleMouseDown(e));
    document.addEventListener("mousemove", (e) => this._handleMouseMove(e));
    document.addEventListener("mouseup", (e) => this._handleMouseUp(e));
  }

  _handleTouchStart(e) {
    e.preventDefault();
    this._isDragging = true;
    this.classList.add("dragging");
    
    const base = this.shadowRoot.getElementById("base");
    const rect = base.getBoundingClientRect();
    this._centerX = rect.left + rect.width / 2;
    this._centerY = rect.top + rect.height / 2;
    this._maxDistance = rect.width / 2 - 20;

    this._updatePosition(e.touches[0].clientX, e.touches[0].clientY);
    this._startSending();
  }

  _handleTouchMove(e) {
    if (!this._isDragging) return;
    e.preventDefault();
    this._updatePosition(e.touches[0].clientX, e.touches[0].clientY);
  }

  _handleTouchEnd(e) {
    if (!this._isDragging) return;
    this._isDragging = false;
    this.classList.remove("dragging");
    this._returnToCenter();
    this._stopSending();
  }

  _handleMouseDown(e) {
    this._isDragging = true;
    this.classList.add("dragging");
    
    const base = this.shadowRoot.getElementById("base");
    const rect = base.getBoundingClientRect();
    this._centerX = rect.left + rect.width / 2;
    this._centerY = rect.top + rect.height / 2;
    this._maxDistance = rect.width / 2 - 20;

    this._updatePosition(e.clientX, e.clientY);
    this._startSending();
  }

  _handleMouseMove(e) {
    if (!this._isDragging) return;
    this._updatePosition(e.clientX, e.clientY);
  }

  _handleMouseUp(e) {
    if (!this._isDragging) return;
    this._isDragging = false;
    this.classList.remove("dragging");
    this._returnToCenter();
    this._stopSending();
  }

  _updatePosition(clientX, clientY) {
    let dx = clientX - this._centerX;
    let dy = clientY - this._centerY;

    // Clamp to circle
    const distance = Math.sqrt(dx * dx + dy * dy);
    if (distance > this._maxDistance) {
      dx = (dx / distance) * this._maxDistance;
      dy = (dy / distance) * this._maxDistance;
    }

    // Normalize to -1 to 1
    this._x = dx / this._maxDistance;
    this._y = -dy / this._maxDistance; // Invert Y for pitch

    this._updateUI();
    this.dispatchEvent(new CustomEvent("change", { 
      detail: { x: this._x, y: this._y, pitch: this._y, yaw: this._x } 
    }));
  }

  _returnToCenter() {
    this._x = 0;
    this._y = 0;
    
    const thumb = this.shadowRoot.getElementById("thumb");
    thumb.style.transform = `translate(-50%, -50%)`;
    
    this._updateValues();
    this.dispatchEvent(new CustomEvent("release"));
  }

  _updateUI() {
    const thumb = this.shadowRoot.getElementById("thumb");
    const offsetX = this._x * this._maxDistance;
    const offsetY = -this._y * this._maxDistance;
    
    thumb.style.transform = `translate(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px))`;
    this._updateValues();
  }

  _updateValues() {
    const pitchEl = this.shadowRoot.getElementById("pitch-value");
    const yawEl = this.shadowRoot.getElementById("yaw-value");
    
    // Convert to degrees (scale factor for rate of change)
    const pitchRate = Math.round(this._y * 30);
    const yawRate = Math.round(this._x * 30);
    
    if (pitchEl) pitchEl.textContent = `${pitchRate > 0 ? "+" : ""}${pitchRate}°`;
    if (yawEl) yawEl.textContent = `${yawRate > 0 ? "+" : ""}${yawRate}°`;
  }

  _startSending() {
    // Send commands at a regular interval while dragging
    this._sendInterval = setInterval(() => {
      if (this._isDragging && (Math.abs(this._x) > 0.05 || Math.abs(this._y) > 0.05)) {
        this._sendCommand();
      }
    }, 100);
  }

  _stopSending() {
    if (this._sendInterval) {
      clearInterval(this._sendInterval);
      this._sendInterval = null;
    }
    // Send zero rate on release
    this._sendZeroRate();
  }

  _sendCommand() {
    const wsClient = window.flaxosApp?.wsClient;
    if (!wsClient) return;

    // Convert joystick position to angular velocity (deg/s)
    const pitchRate = this._y * 30; // -30 to +30 deg/s
    const yawRate = this._x * 30;

    wsClient.send("set_angular_velocity", { 
      pitch: pitchRate, 
      yaw: yawRate, 
      roll: 0 
    });
  }

  _sendZeroRate() {
    const wsClient = window.flaxosApp?.wsClient;
    if (!wsClient) return;

    wsClient.send("set_angular_velocity", { 
      pitch: 0, 
      yaw: 0, 
      roll: 0 
    });
  }

  // Public API
  get x() { return this._x; }
  get y() { return this._y; }
  get pitch() { return this._y; }
  get yaw() { return this._x; }
}

customElements.define("touch-joystick", TouchJoystick);
export { TouchJoystick };
