/**
 * Throttle Control
 * Vertical slider with discrete steps and emergency stop
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class ThrottleControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._isDragging = false;
    this._currentValue = 0;
    this._targetValue = 0;
    // Store document-level event handlers for cleanup
    this._documentHandlers = [];
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    // Clean up document-level event listeners
    for (const { event, handler, options } of this._documentHandlers) {
      document.removeEventListener(event, handler, options);
    }
    this._documentHandlers = [];
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      if (!this._isDragging) {
        this._updateFromState();
      }
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .throttle-container {
          display: flex;
          gap: 16px;
          align-items: stretch;
        }

        .scale {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          padding: 4px 0;
        }

        .scale-mark {
          text-align: right;
          width: 35px;
        }

        .slider-track {
          width: 40px;
          height: 200px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          position: relative;
          cursor: pointer;
          touch-action: none;
        }

        .slider-fill {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          background: linear-gradient(to top, var(--status-info, #00aaff), var(--status-nominal, #00ff88));
          border-radius: 0 0 8px 8px;
          transition: height 0.1s ease;
        }

        .slider-handle {
          position: absolute;
          left: -4px;
          right: -4px;
          height: 12px;
          background: var(--text-primary, #e0e0e0);
          border-radius: 6px;
          cursor: grab;
          transform: translateY(50%);
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
          transition: background 0.1s ease;
        }

        .slider-handle:hover {
          background: var(--text-bright, #ffffff);
        }

        .slider-handle.dragging {
          cursor: grabbing;
          background: var(--status-info, #00aaff);
        }

        .current-value {
          text-align: center;
          margin-top: 16px;
        }

        .value-display {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.5rem;
          color: var(--text-primary, #e0e0e0);
        }

        .value-label {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .quick-buttons {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .quick-btn {
          width: 36px;
          height: 28px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          cursor: pointer;
          font-size: 0.7rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          min-height: auto;
          padding: 0;
        }

        .quick-btn:hover {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }

        .quick-btn.active {
          background: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
          border-color: var(--status-info, #00aaff);
        }

        .stop-btn {
          margin-top: 16px;
          padding: 12px 24px;
          background: var(--status-critical, #ff4444);
          border: none;
          border-radius: 8px;
          color: var(--text-bright, #ffffff);
          font-weight: 600;
          font-size: 0.85rem;
          cursor: pointer;
          min-height: 44px;
        }

        .stop-btn:hover {
          filter: brightness(1.1);
        }

        .stop-btn:active {
          transform: scale(0.98);
        }
      </style>

      <div class="throttle-container">
        <div class="scale">
          <span class="scale-mark">100%</span>
          <span class="scale-mark">80%</span>
          <span class="scale-mark">60%</span>
          <span class="scale-mark">40%</span>
          <span class="scale-mark">20%</span>
          <span class="scale-mark">0%</span>
        </div>

        <div class="slider-track" id="track">
          <div class="slider-fill" id="fill"></div>
          <div class="slider-handle" id="handle"></div>
        </div>

        <div class="quick-buttons">
          <button class="quick-btn" data-value="100">100</button>
          <button class="quick-btn" data-value="75">75</button>
          <button class="quick-btn" data-value="50">50</button>
          <button class="quick-btn" data-value="25">25</button>
          <button class="quick-btn" data-value="0">0</button>
        </div>
      </div>

      <div class="current-value">
        <div class="value-display" id="value-display">0%</div>
        <div class="value-label">Current Thrust</div>
      </div>

      <button class="stop-btn" id="stop-btn">🛑 EMERGENCY STOP</button>
    `;
  }

  _setupInteraction() {
    const track = this.shadowRoot.getElementById("track");
    const handle = this.shadowRoot.getElementById("handle");
    const stopBtn = this.shadowRoot.getElementById("stop-btn");

    // Quick buttons
    this.shadowRoot.querySelectorAll(".quick-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const value = parseInt(btn.dataset.value, 10);
        this._setThrottle(value / 100);
      });
    });

    // Emergency stop
    stopBtn.addEventListener("click", () => {
      this._emergencyStop();
    });

    // Mouse/touch drag on track
    const startDrag = (e) => {
      e.preventDefault();
      this._isDragging = true;
      handle.classList.add("dragging");
      this._updateFromEvent(e);
    };

    const moveDrag = (e) => {
      if (this._isDragging) {
        e.preventDefault();
        this._updateFromEvent(e);
      }
    };

    const endDrag = () => {
      if (this._isDragging) {
        this._isDragging = false;
        handle.classList.remove("dragging");
        // Snap to nearest 10%
        const snapped = Math.round(this._targetValue * 10) / 10;
        this._setThrottle(snapped);
      }
    };

    // Mouse events
    track.addEventListener("mousedown", startDrag);
    
    // Add document-level listeners and track them for cleanup
    document.addEventListener("mousemove", moveDrag);
    this._documentHandlers.push({ event: "mousemove", handler: moveDrag });
    
    document.addEventListener("mouseup", endDrag);
    this._documentHandlers.push({ event: "mouseup", handler: endDrag });

    // Touch events
    track.addEventListener("touchstart", startDrag, { passive: false });
    
    document.addEventListener("touchmove", moveDrag, { passive: false });
    this._documentHandlers.push({ event: "touchmove", handler: moveDrag, options: { passive: false } });
    
    document.addEventListener("touchend", endDrag);
    this._documentHandlers.push({ event: "touchend", handler: endDrag });

    // Click on track
    track.addEventListener("click", (e) => {
      if (!this._isDragging) {
        this._updateFromEvent(e);
        const snapped = Math.round(this._targetValue * 10) / 10;
        this._setThrottle(snapped);
      }
    });
  }

  _updateFromEvent(e) {
    const track = this.shadowRoot.getElementById("track");
    const rect = track.getBoundingClientRect();

    let clientY;
    if (e.touches) {
      clientY = e.touches[0].clientY;
    } else {
      clientY = e.clientY;
    }

    const relativeY = clientY - rect.top;
    const percent = 1 - (relativeY / rect.height);
    this._targetValue = Math.max(0, Math.min(1, percent));
    this._updateVisual(this._targetValue);
  }

  _updateVisual(value) {
    const fill = this.shadowRoot.getElementById("fill");
    const handle = this.shadowRoot.getElementById("handle");
    const display = this.shadowRoot.getElementById("value-display");

    const percent = value * 100;
    fill.style.height = `${percent}%`;
    handle.style.bottom = `calc(${percent}% - 6px)`;
    display.textContent = `${Math.round(percent)}%`;

    // Update quick button states
    this.shadowRoot.querySelectorAll(".quick-btn").forEach(btn => {
      const btnValue = parseInt(btn.dataset.value, 10);
      btn.classList.toggle("active", Math.abs(btnValue - percent) < 5);
    });
  }

  _updateFromState() {
    const nav = stateManager.getNavigation();
    const thrust = nav.thrust ?? 0;
    this._currentValue = thrust;
    this._updateVisual(thrust);
  }

  async _setThrottle(value) {
    this._targetValue = value;
    this._updateVisual(value);

    try {
      // Send scalar throttle (0-1) for main drive
      // Expanse-style: main drive thrust is along ship's forward axis
      // Server handles ship-frame to world-frame rotation via quaternion
      console.log("Setting throttle:", value);
      const response = await wsClient.sendShipCommand("set_thrust", { 
        thrust: value  // Scalar 0-1
      });
      console.log("Throttle response:", JSON.stringify(response, null, 2));
      
      // Check for errors in response
      if (response?.ok === false || response?.error) {
        const errorMsg = response.error || response.message || "Unknown error";
        console.error("Throttle command error:", errorMsg);
        this._showMessage(`Throttle error: ${errorMsg}`, "error");
        // Revert visual on error
        this._updateFromState();
      } else if (response?.ok === true) {
        // Response structure: {ok: true, response: {status: "...", throttle: ...}}
        const result = response.response || response;
        if (result?.throttle !== undefined) {
          // Update from server response if available
          this._currentValue = result.throttle;
          this._updateVisual(this._currentValue);
          console.log("Throttle updated from response:", result.throttle);
        } else {
          // Command succeeded but no throttle in response - that's OK, state will update via polling
          console.log("Throttle command succeeded, waiting for state update");
        }
      } else {
        console.warn("Unexpected throttle response format:", response);
      }
    } catch (error) {
      console.error("Throttle command failed:", error);
      this._showMessage(`Throttle failed: ${error.message}`, "error");
      // Revert visual on error
      this._updateFromState();
    }
  }

  async _emergencyStop() {
    this._targetValue = 0;
    this._updateVisual(0);

    try {
      // Emergency stop sets throttle to zero
      const response = await wsClient.sendShipCommand("set_thrust", { thrust: 0 });
      console.log("Emergency stop response:", response);
    } catch (error) {
      console.error("Emergency stop failed:", error);
      this._showMessage(`Emergency stop failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("throttle-control", ThrottleControl);
export { ThrottleControl };
