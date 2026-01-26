/**
 * Throttle Control - Enhanced
 * Vertical slider with direct percentage input, G-force display, and emergency stop
 * Supports precise manual % input at any value (not just increments)
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

// G-force zones for display
const G_ZONES = {
  CRUISE: { max: 0.3, label: "CRUISE", color: "var(--status-nominal, #00ff88)" },
  STANDARD: { max: 1.0, label: "STANDARD", color: "var(--status-info, #00aaff)" },
  HIGH: { max: 3.0, label: "HIGH-G", color: "var(--status-warning, #ffaa00)" },
  COMBAT: { max: 6.0, label: "COMBAT", color: "var(--status-critical, #ff4444)" },
  EXTREME: { max: Infinity, label: "EXTREME", color: "#ff0000" }
};

class ThrottleControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._isDragging = false;
    this._currentValue = 0;
    this._targetValue = 0;
    this._inputMode = "slider"; // "slider", "percent", or "g"
    this._currentG = 0;
    this._maxG = 0;
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

        .mode-toggle {
          display: flex;
          gap: 4px;
          margin-bottom: 12px;
          width: 100%;
        }

        .mode-btn {
          flex: 1;
          padding: 6px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          font-size: 0.65rem;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .mode-btn.active {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
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

        /* Manual Input Section */
        .manual-input-section {
          width: 100%;
          margin-top: 16px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .input-row {
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .input-row input {
          flex: 1;
          padding: 8px;
          background: var(--bg-primary, #0a0a0f);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.9rem;
          text-align: center;
        }

        .input-row input:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .input-row .unit {
          font-size: 0.75rem;
          color: var(--text-dim, #555566);
          min-width: 20px;
        }

        .apply-btn {
          padding: 8px 16px;
          background: var(--status-info, #00aaff);
          border: none;
          border-radius: 4px;
          color: var(--bg-primary, #0a0a0f);
          font-weight: 600;
          font-size: 0.8rem;
          cursor: pointer;
        }

        .apply-btn:hover {
          filter: brightness(1.1);
        }

        /* G-Force Display */
        .g-force-display {
          width: 100%;
          margin-top: 12px;
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
        }

        .g-force-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .g-force-label {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .g-force-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.2rem;
          font-weight: 600;
        }

        .g-force-bar {
          height: 8px;
          background: var(--bg-primary, #0a0a0f);
          border-radius: 4px;
          overflow: hidden;
          position: relative;
        }

        .g-force-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.2s ease, background 0.2s ease;
        }

        .g-zone-indicator {
          margin-top: 8px;
          display: flex;
          justify-content: space-between;
          font-size: 0.65rem;
        }

        .g-zone {
          padding: 2px 6px;
          border-radius: 3px;
          font-weight: 600;
        }

        .current-value {
          text-align: center;
          margin-top: 12px;
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
          width: 100%;
        }

        .stop-btn:hover {
          filter: brightness(1.1);
        }

        .stop-btn:active {
          transform: scale(0.98);
        }

        .hidden {
          display: none !important;
        }
      </style>

      <!-- Mode Toggle -->
      <div class="mode-toggle">
        <button class="mode-btn active" data-mode="slider">Slider</button>
        <button class="mode-btn" data-mode="percent">% Input</button>
        <button class="mode-btn" data-mode="g">G-Force</button>
      </div>

      <!-- Slider Mode -->
      <div class="throttle-container" id="slider-section">
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
          <button class="quick-btn" data-value="10">10</button>
          <button class="quick-btn" data-value="1">1</button>
          <button class="quick-btn" data-value="0">0</button>
        </div>
      </div>

      <!-- Manual Percent Input -->
      <div class="manual-input-section hidden" id="percent-section">
        <div class="input-row">
          <input type="number" id="percent-input" value="0" min="0" max="100" step="0.1" placeholder="0.0" />
          <span class="unit">%</span>
          <button class="apply-btn" id="apply-percent-btn">Set</button>
        </div>
        <div class="quick-buttons" style="flex-direction: row; flex-wrap: wrap; gap: 4px;">
          <button class="quick-btn" data-value="1" style="width: auto; padding: 4px 8px;">1%</button>
          <button class="quick-btn" data-value="5" style="width: auto; padding: 4px 8px;">5%</button>
          <button class="quick-btn" data-value="10" style="width: auto; padding: 4px 8px;">10%</button>
          <button class="quick-btn" data-value="25" style="width: auto; padding: 4px 8px;">25%</button>
          <button class="quick-btn" data-value="50" style="width: auto; padding: 4px 8px;">50%</button>
          <button class="quick-btn" data-value="75" style="width: auto; padding: 4px 8px;">75%</button>
          <button class="quick-btn" data-value="100" style="width: auto; padding: 4px 8px;">100%</button>
        </div>
      </div>

      <!-- G-Force Input -->
      <div class="manual-input-section hidden" id="g-section">
        <div class="input-row">
          <input type="number" id="g-input" value="0" min="0" step="0.1" placeholder="0.0" />
          <span class="unit">G</span>
          <button class="apply-btn" id="apply-g-btn">Set</button>
        </div>
        <div class="quick-buttons" style="flex-direction: row; flex-wrap: wrap; gap: 4px;">
          <button class="quick-btn g-preset" data-g="0.25" style="width: auto; padding: 4px 8px;">0.25G</button>
          <button class="quick-btn g-preset" data-g="0.5" style="width: auto; padding: 4px 8px;">0.5G</button>
          <button class="quick-btn g-preset" data-g="1.0" style="width: auto; padding: 4px 8px;">1.0G</button>
          <button class="quick-btn g-preset" data-g="2.0" style="width: auto; padding: 4px 8px;">2.0G</button>
          <button class="quick-btn g-preset" data-g="3.0" style="width: auto; padding: 4px 8px;">3.0G</button>
        </div>
      </div>

      <!-- G-Force Display -->
      <div class="g-force-display">
        <div class="g-force-header">
          <span class="g-force-label">Current G-Force</span>
          <span class="g-force-value" id="g-value">0.00 G</span>
        </div>
        <div class="g-force-bar">
          <div class="g-force-fill" id="g-fill"></div>
        </div>
        <div class="g-zone-indicator">
          <span class="g-zone" id="g-zone" style="background: var(--status-nominal);">CRUISE</span>
          <span id="max-g-display" style="color: var(--text-dim);">Max: 0.0 G</span>
        </div>
      </div>

      <div class="current-value">
        <div class="value-display" id="value-display">0%</div>
        <div class="value-label">Current Thrust</div>
      </div>

      <button class="stop-btn" id="stop-btn">EMERGENCY STOP</button>
    `;
  }

  _setupInteraction() {
    // Mode toggle
    this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._setMode(btn.dataset.mode);
      });
    });

    const track = this.shadowRoot.getElementById("track");
    const handle = this.shadowRoot.getElementById("handle");
    const stopBtn = this.shadowRoot.getElementById("stop-btn");

    // Quick buttons (slider section)
    this.shadowRoot.getElementById("slider-section").querySelectorAll(".quick-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const value = parseInt(btn.dataset.value, 10);
        this._setThrottle(value / 100);
      });
    });

    // Percent section quick buttons and input
    this.shadowRoot.getElementById("percent-section").querySelectorAll(".quick-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const value = parseInt(btn.dataset.value, 10);
        this.shadowRoot.getElementById("percent-input").value = value;
        this._setThrottle(value / 100);
      });
    });

    this.shadowRoot.getElementById("apply-percent-btn").addEventListener("click", () => {
      const value = parseFloat(this.shadowRoot.getElementById("percent-input").value) || 0;
      this._setThrottle(Math.max(0, Math.min(100, value)) / 100);
    });

    this.shadowRoot.getElementById("percent-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const value = parseFloat(e.target.value) || 0;
        this._setThrottle(Math.max(0, Math.min(100, value)) / 100);
      }
    });

    // G-Force section
    this.shadowRoot.querySelectorAll(".g-preset").forEach(btn => {
      btn.addEventListener("click", () => {
        const gValue = parseFloat(btn.dataset.g);
        this.shadowRoot.getElementById("g-input").value = gValue;
        this._setThrottleByG(gValue);
      });
    });

    this.shadowRoot.getElementById("apply-g-btn").addEventListener("click", () => {
      const gValue = parseFloat(this.shadowRoot.getElementById("g-input").value) || 0;
      this._setThrottleByG(gValue);
    });

    this.shadowRoot.getElementById("g-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const gValue = parseFloat(e.target.value) || 0;
        this._setThrottleByG(gValue);
      }
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
        // NO snapping - use exact value
        this._setThrottle(this._targetValue);
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

    // Click on track (no snap)
    track.addEventListener("click", (e) => {
      if (!this._isDragging) {
        this._updateFromEvent(e);
        this._setThrottle(this._targetValue);
      }
    });
  }

  _setMode(mode) {
    this._inputMode = mode;

    // Update button states
    this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });

    // Show/hide sections
    const sliderSection = this.shadowRoot.getElementById("slider-section");
    const percentSection = this.shadowRoot.getElementById("percent-section");
    const gSection = this.shadowRoot.getElementById("g-section");

    sliderSection.classList.toggle("hidden", mode !== "slider");
    percentSection.classList.toggle("hidden", mode !== "percent");
    gSection.classList.toggle("hidden", mode !== "g");

    // Update input values
    if (mode === "percent") {
      this.shadowRoot.getElementById("percent-input").value = (this._currentValue * 100).toFixed(1);
    } else if (mode === "g") {
      this.shadowRoot.getElementById("g-input").value = this._currentG.toFixed(2);
    }
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
    display.textContent = `${percent.toFixed(1)}%`;

    // Update quick button states
    this.shadowRoot.querySelectorAll(".quick-btn[data-value]").forEach(btn => {
      const btnValue = parseInt(btn.dataset.value, 10);
      btn.classList.toggle("active", Math.abs(btnValue - percent) < 1);
    });
  }

  _updateGForceDisplay() {
    const gValue = this.shadowRoot.getElementById("g-value");
    const gFill = this.shadowRoot.getElementById("g-fill");
    const gZone = this.shadowRoot.getElementById("g-zone");
    const maxGDisplay = this.shadowRoot.getElementById("max-g-display");

    // Update G value display
    gValue.textContent = `${this._currentG.toFixed(2)} G`;
    maxGDisplay.textContent = `Max: ${this._maxG.toFixed(1)} G`;

    // Calculate fill percentage (capped at max G or 6G for display)
    const maxDisplayG = Math.max(this._maxG, 6);
    const fillPercent = Math.min((this._currentG / maxDisplayG) * 100, 100);
    gFill.style.width = `${fillPercent}%`;

    // Determine zone and color
    let zone = G_ZONES.CRUISE;
    if (this._currentG > G_ZONES.COMBAT.max) {
      zone = G_ZONES.EXTREME;
    } else if (this._currentG > G_ZONES.HIGH.max) {
      zone = G_ZONES.COMBAT;
    } else if (this._currentG > G_ZONES.STANDARD.max) {
      zone = G_ZONES.HIGH;
    } else if (this._currentG > G_ZONES.CRUISE.max) {
      zone = G_ZONES.STANDARD;
    }

    gValue.style.color = zone.color;
    gFill.style.background = zone.color;
    gZone.textContent = zone.label;
    gZone.style.background = zone.color;
    gZone.style.color = zone === G_ZONES.CRUISE || zone === G_ZONES.STANDARD ? "#000" : "#fff";
  }

  _updateFromState() {
    const nav = stateManager.getNavigation();
    const ship = stateManager.getShipState();
    const thrust = nav.thrust ?? 0;
    this._currentValue = thrust;
    this._updateVisual(thrust);

    // Get G-force from propulsion system
    const propulsion = ship?.systems?.propulsion || {};
    this._currentG = propulsion.thrust_g || 0;
    this._maxG = propulsion.max_thrust_g || 0;
    this._updateGForceDisplay();
  }

  async _setThrottle(value) {
    this._targetValue = value;
    this._updateVisual(value);

    try {
      // Send scalar throttle (0-1) for main drive
      console.log("Setting throttle:", value, `(${(value * 100).toFixed(1)}%)`);
      const response = await wsClient.sendShipCommand("set_thrust", {
        thrust: value
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
        const result = response.response || response;
        if (result?.throttle !== undefined) {
          this._currentValue = result.throttle;
          this._updateVisual(this._currentValue);
          console.log("Throttle updated from response:", result.throttle);
        }
      }
    } catch (error) {
      console.error("Throttle command failed:", error);
      this._showMessage(`Throttle failed: ${error.message}`, "error");
      this._updateFromState();
    }
  }

  async _setThrottleByG(gValue) {
    try {
      console.log("Setting throttle by G-force:", gValue);
      const response = await wsClient.sendShipCommand("set_thrust", {
        g: gValue
      });
      console.log("G-force throttle response:", JSON.stringify(response, null, 2));

      if (response?.ok === false || response?.error) {
        const errorMsg = response.error || response.message || "Unknown error";
        this._showMessage(`G-force error: ${errorMsg}`, "error");
      } else {
        this._showMessage(`Thrust set to ${gValue} G`, "success");
      }
    } catch (error) {
      console.error("G-force command failed:", error);
      this._showMessage(`G-force failed: ${error.message}`, "error");
    }
  }

  async _emergencyStop() {
    this._targetValue = 0;
    this._updateVisual(0);

    try {
      const response = await wsClient.sendShipCommand("set_thrust", { thrust: 0 });
      console.log("Emergency stop response:", response);
      this._showMessage("EMERGENCY STOP - Thrust zeroed", "warning");
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
