/**
 * Touch Throttle Component
 * Phase 6: Mobile Optimization
 * 
 * Vertical swipe/drag control for throttle with snap to 10% increments.
 * Includes emergency stop on double-tap.
 */

class TouchThrottle extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    
    this._value = 0;
    this._isDragging = false;
    this._startY = 0;
    this._startValue = 0;
    this._lastTap = 0;
  }

  connectedCallback() {
    this.render();
    this._setupListeners();
    this._subscribeToState();
  }

  disconnectedCallback() {
    this._unsubscribe?.();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          width: 80px;
          height: 200px;
          touch-action: none;
          user-select: none;
        }

        .throttle-container {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
        }

        .throttle-track {
          width: 50px;
          height: 160px;
          background: var(--bg-input, #1a1a24);
          border: 2px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          position: relative;
          overflow: hidden;
        }

        .throttle-fill {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          background: linear-gradient(to top, var(--status-nominal, #00ff88), var(--status-warning, #ffaa00));
          transition: height 0.1s ease;
        }

        .throttle-handle {
          position: absolute;
          left: -4px;
          right: -4px;
          height: 16px;
          background: var(--text-primary, #e0e0e0);
          border-radius: 4px;
          cursor: grab;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
          transition: transform 0.1s ease;
        }

        .throttle-handle:active {
          cursor: grabbing;
          transform: scaleX(1.1);
        }

        .throttle-markers {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          pointer-events: none;
        }

        .marker {
          position: absolute;
          left: 0;
          right: 0;
          height: 1px;
          background: var(--border-default, #2a2a3a);
        }

        .marker.major {
          background: var(--text-dim, #555566);
        }

        .throttle-value {
          font-family: var(--font-mono, monospace);
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          text-align: center;
        }

        .throttle-label {
          font-size: 10px;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .emergency-stop {
          width: 100%;
          padding: 8px;
          background: var(--status-critical, #ff4444);
          border: none;
          border-radius: 4px;
          color: white;
          font-size: 10px;
          font-weight: 600;
          cursor: pointer;
          opacity: 0.8;
        }

        .emergency-stop:active {
          opacity: 1;
          transform: scale(0.95);
        }

        /* Active dragging state */
        :host(.dragging) .throttle-track {
          border-color: var(--status-info, #00aaff);
        }
      </style>
      
      <div class="throttle-container">
        <span class="throttle-label">Throttle</span>
        <div class="throttle-track" id="track">
          <div class="throttle-fill" id="fill"></div>
          <div class="throttle-markers">
            ${this._renderMarkers()}
          </div>
          <div class="throttle-handle" id="handle"></div>
        </div>
        <span class="throttle-value" id="value">0%</span>
        <button class="emergency-stop" id="stop">STOP</button>
      </div>
    `;
  }

  _renderMarkers() {
    let markers = "";
    for (let i = 0; i <= 10; i++) {
      const pos = 100 - (i * 10);
      const major = i % 5 === 0;
      markers += `<div class="marker ${major ? "major" : ""}" style="top: ${pos}%"></div>`;
    }
    return markers;
  }

  _setupListeners() {
    const track = this.shadowRoot.getElementById("track");
    const handle = this.shadowRoot.getElementById("handle");
    const stopBtn = this.shadowRoot.getElementById("stop");

    // Touch events on track
    track.addEventListener("touchstart", (e) => this._handleTouchStart(e));
    track.addEventListener("touchmove", (e) => this._handleTouchMove(e));
    track.addEventListener("touchend", (e) => this._handleTouchEnd(e));

    // Mouse events for desktop testing
    track.addEventListener("mousedown", (e) => this._handleMouseDown(e));

    // Emergency stop
    stopBtn.addEventListener("click", () => this._emergencyStop());

    // Double-tap detection on track
    track.addEventListener("touchend", (e) => {
      const now = Date.now();
      if (now - this._lastTap < 300) {
        this._emergencyStop();
      }
      this._lastTap = now;
    });
  }

  _handleTouchStart(e) {
    e.preventDefault();
    this._isDragging = true;
    this._startY = e.touches[0].clientY;
    this._startValue = this._value;
    this.classList.add("dragging");
  }

  _handleTouchMove(e) {
    if (!this._isDragging) return;
    e.preventDefault();

    const track = this.shadowRoot.getElementById("track");
    const rect = track.getBoundingClientRect();
    const deltaY = this._startY - e.touches[0].clientY;
    const deltaPercent = (deltaY / rect.height) * 100;
    
    let newValue = Math.round((this._startValue + deltaPercent) / 10) * 10;
    newValue = Math.max(0, Math.min(100, newValue));
    
    this._setValue(newValue);
  }

  _handleTouchEnd(e) {
    if (!this._isDragging) return;
    this._isDragging = false;
    this.classList.remove("dragging");
    this._sendCommand();
  }

  _handleMouseDown(e) {
    const track = this.shadowRoot.getElementById("track");
    const rect = track.getBoundingClientRect();
    const y = e.clientY - rect.top;
    const percent = Math.round((1 - y / rect.height) * 100 / 10) * 10;
    this._setValue(Math.max(0, Math.min(100, percent)));
    this._sendCommand();
  }

  _setValue(value) {
    this._value = value;
    this._updateUI();
    this.dispatchEvent(new CustomEvent("change", { detail: { value } }));
  }

  _updateUI() {
    const fill = this.shadowRoot.getElementById("fill");
    const handle = this.shadowRoot.getElementById("handle");
    const valueEl = this.shadowRoot.getElementById("value");

    if (fill) fill.style.height = `${this._value}%`;
    if (handle) handle.style.bottom = `calc(${this._value}% - 8px)`;
    if (valueEl) valueEl.textContent = `${this._value}%`;
  }

  _sendCommand() {
    const wsClient = window.flaxosApp?.wsClient;
    if (wsClient) {
      wsClient.send("set_thrust", { thrust: this._value / 100 });
    }
  }

  _emergencyStop() {
    this._setValue(0);
    this._sendCommand();
    
    // Visual feedback
    const stopBtn = this.shadowRoot.getElementById("stop");
    stopBtn.style.background = "#ff0000";
    setTimeout(() => {
      stopBtn.style.background = "";
    }, 200);

    // Dispatch event
    this.dispatchEvent(new CustomEvent("emergency_stop"));
  }

  _subscribeToState() {
    const stateManager = window.flaxosApp?.stateManager;
    if (!stateManager) return;

    this._unsubscribe = stateManager.subscribe("*", (state) => {
      if (this._isDragging) return; // Don't update while user is dragging

      const nav = stateManager.getNavigation();
      if (nav && typeof nav.thrust === "number") {
        const serverValue = Math.round(nav.thrust * 100);
        if (serverValue !== this._value) {
          this._value = serverValue;
          this._updateUI();
        }
      }
    });
  }

  // Public API
  get value() {
    return this._value;
  }

  set value(val) {
    this._setValue(Math.max(0, Math.min(100, val)));
  }
}

customElements.define("touch-throttle", TouchThrottle);
export { TouchThrottle };
