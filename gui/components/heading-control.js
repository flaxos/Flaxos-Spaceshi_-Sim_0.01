/**
 * Heading Control - Enhanced
 * Pitch and yaw sliders with visual compass AND direct numeric input
 * Supports both slider and manual entry for precise heading control
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class HeadingControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._pitch = 0;
    this._yaw = 0;
    this._roll = 0;
    this._isDragging = false;
    this._inputMode = "slider"; // "slider" or "manual"
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
      if (!this._isDragging && this._inputMode !== "manual") {
        this._updateFromState();
      }
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

        .mode-toggle {
          display: flex;
          gap: 4px;
          margin-bottom: 12px;
        }

        .mode-btn {
          flex: 1;
          padding: 6px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          font-size: 0.7rem;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .mode-btn.active {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .compass-container {
          display: flex;
          justify-content: center;
          margin-bottom: 16px;
        }

        .compass {
          width: 120px;
          height: 120px;
          border-radius: 50%;
          background: var(--bg-input, #1a1a24);
          border: 2px solid var(--border-default, #2a2a3a);
          position: relative;
        }

        .compass-label {
          position: absolute;
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
        }

        .compass-label.north { top: 4px; left: 50%; transform: translateX(-50%); }
        .compass-label.south { bottom: 4px; left: 50%; transform: translateX(-50%); }
        .compass-label.east { right: 4px; top: 50%; transform: translateY(-50%); }
        .compass-label.west { left: 4px; top: 50%; transform: translateY(-50%); }

        .compass-needle {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 4px;
          height: 50px;
          background: linear-gradient(to top, var(--status-critical, #ff4444) 50%, var(--status-info, #00aaff) 50%);
          border-radius: 2px;
          transform-origin: center bottom;
          transform: translate(-50%, -100%) rotate(0deg);
          transition: transform 0.2s ease;
        }

        .compass-center {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 12px;
          height: 12px;
          background: var(--text-primary, #e0e0e0);
          border-radius: 50%;
          transform: translate(-50%, -50%);
        }

        .yaw-display {
          position: absolute;
          bottom: -24px;
          left: 50%;
          transform: translateX(-50%);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
        }

        /* Manual input section */
        .manual-inputs {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-bottom: 16px;
        }

        .input-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .input-group label {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          text-align: center;
        }

        .input-group input {
          padding: 8px;
          background: var(--bg-primary, #0a0a0f);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          text-align: center;
          width: 100%;
          box-sizing: border-box;
        }

        .input-group input:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .input-group input.invalid {
          border-color: var(--status-critical, #ff4444);
        }

        /* Slider controls */
        .sliders {
          display: grid;
          gap: 16px;
        }

        .slider-group {
          display: grid;
          gap: 8px;
        }

        .slider-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .slider-label {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
        }

        .slider-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
        }

        .slider-track {
          height: 24px;
          background: var(--bg-input, #1a1a24);
          border-radius: 12px;
          position: relative;
          cursor: pointer;
        }

        .slider-track::before {
          content: '';
          position: absolute;
          left: 50%;
          top: 4px;
          bottom: 4px;
          width: 2px;
          background: var(--border-active, #3a3a4a);
          transform: translateX(-50%);
        }

        .slider-handle {
          position: absolute;
          top: 2px;
          width: 20px;
          height: 20px;
          background: var(--status-info, #00aaff);
          border-radius: 50%;
          cursor: grab;
          transform: translateX(-50%);
          transition: background 0.1s ease;
        }

        .slider-handle:hover {
          background: var(--text-bright, #ffffff);
        }

        .slider-handle.dragging {
          cursor: grabbing;
          background: var(--status-nominal, #00ff88);
        }

        /* Current heading display */
        .current-heading {
          margin-bottom: 12px;
          padding: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-align: center;
        }

        .current-heading strong {
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .buttons {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }

        .btn {
          flex: 1;
          padding: 10px 16px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.8rem;
          cursor: pointer;
          min-height: 44px;
        }

        .btn:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--border-active, #3a3a4a);
        }

        .btn.primary {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
          font-weight: 600;
        }

        .btn.primary:hover {
          filter: brightness(1.1);
        }

        .hidden {
          display: none !important;
        }
      </style>

      <!-- Mode Toggle -->
      <div class="mode-toggle">
        <button class="mode-btn active" data-mode="slider">Slider</button>
        <button class="mode-btn" data-mode="manual">Manual Entry</button>
      </div>

      <!-- Current Heading Display -->
      <div class="current-heading" id="current-heading">
        Current: <strong id="current-display">P: 0.0 | Y: 0.0 | R: 0.0</strong>
      </div>

      <!-- Compass (shown in both modes) -->
      <div class="compass-container">
        <div class="compass">
          <span class="compass-label north">000</span>
          <span class="compass-label east">090</span>
          <span class="compass-label south">180</span>
          <span class="compass-label west">270</span>
          <div class="compass-needle" id="needle"></div>
          <div class="compass-center"></div>
          <div class="yaw-display" id="yaw-display">000.0</div>
        </div>
      </div>

      <!-- Manual Input Section -->
      <div class="manual-inputs hidden" id="manual-section">
        <div class="input-group">
          <label>Pitch</label>
          <input type="number" id="pitch-input" value="0" min="-90" max="90" step="0.1" />
        </div>
        <div class="input-group">
          <label>Yaw</label>
          <input type="number" id="yaw-input" value="0" min="-180" max="360" step="0.1" />
        </div>
        <div class="input-group">
          <label>Roll</label>
          <input type="number" id="roll-input" value="0" min="-180" max="180" step="0.1" />
        </div>
      </div>

      <!-- Slider Section -->
      <div class="sliders" id="slider-section">
        <div class="slider-group">
          <div class="slider-header">
            <span class="slider-label">Pitch</span>
            <span class="slider-value" id="pitch-value">+0.0</span>
          </div>
          <div class="slider-track" id="pitch-track">
            <div class="slider-handle" id="pitch-handle"></div>
          </div>
        </div>

        <div class="slider-group">
          <div class="slider-header">
            <span class="slider-label">Yaw</span>
            <span class="slider-value" id="yaw-value">000.0</span>
          </div>
          <div class="slider-track" id="yaw-track">
            <div class="slider-handle" id="yaw-handle"></div>
          </div>
        </div>
      </div>

      <div class="buttons">
        <button class="btn primary" id="apply-btn">Apply Heading</button>
        <button class="btn" id="reset-btn">Reset</button>
      </div>
    `;
  }

  _setupInteraction() {
    // Mode toggle
    this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._setMode(btn.dataset.mode);
      });
    });

    // Pitch slider
    this._setupSlider("pitch", -90, 90);

    // Yaw slider
    this._setupSlider("yaw", 0, 360);

    // Manual inputs
    this._setupManualInputs();

    // Buttons
    this.shadowRoot.getElementById("apply-btn").addEventListener("click", () => {
      this._applyHeading();
    });

    this.shadowRoot.getElementById("reset-btn").addEventListener("click", () => {
      this._resetToCurrentHeading();
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
    const manualSection = this.shadowRoot.getElementById("manual-section");

    if (mode === "slider") {
      sliderSection.classList.remove("hidden");
      manualSection.classList.add("hidden");
    } else {
      sliderSection.classList.add("hidden");
      manualSection.classList.remove("hidden");
      // Populate manual inputs with current values
      this._updateManualInputs();
    }
  }

  _setupManualInputs() {
    const pitchInput = this.shadowRoot.getElementById("pitch-input");
    const yawInput = this.shadowRoot.getElementById("yaw-input");
    const rollInput = this.shadowRoot.getElementById("roll-input");

    // Update internal values on input change
    pitchInput.addEventListener("input", () => {
      const value = parseFloat(pitchInput.value);
      if (!isNaN(value)) {
        this._pitch = Math.max(-90, Math.min(90, value));
        this._updateVisual();
      }
    });

    yawInput.addEventListener("input", () => {
      const value = parseFloat(yawInput.value);
      if (!isNaN(value)) {
        this._yaw = ((value % 360) + 360) % 360; // Normalize to 0-360
        this._updateVisual();
      }
    });

    rollInput.addEventListener("input", () => {
      const value = parseFloat(rollInput.value);
      if (!isNaN(value)) {
        this._roll = Math.max(-180, Math.min(180, value));
      }
    });

    // Enter key applies heading
    [pitchInput, yawInput, rollInput].forEach(input => {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          this._applyHeading();
        }
      });
    });
  }

  _updateManualInputs() {
    const pitchInput = this.shadowRoot.getElementById("pitch-input");
    const yawInput = this.shadowRoot.getElementById("yaw-input");
    const rollInput = this.shadowRoot.getElementById("roll-input");

    if (pitchInput) pitchInput.value = this._pitch.toFixed(1);
    if (yawInput) yawInput.value = this._yaw.toFixed(1);
    if (rollInput) rollInput.value = this._roll.toFixed(1);
  }

  _setupSlider(name, min, max) {
    const track = this.shadowRoot.getElementById(`${name}-track`);
    const handle = this.shadowRoot.getElementById(`${name}-handle`);

    const updateFromEvent = (e) => {
      const rect = track.getBoundingClientRect();
      let clientX;
      if (e.touches) {
        clientX = e.touches[0].clientX;
      } else {
        clientX = e.clientX;
      }
      const relativeX = clientX - rect.left;
      const percent = relativeX / rect.width;
      const value = min + (max - min) * Math.max(0, Math.min(1, percent));

      if (name === "pitch") {
        this._pitch = value;
      } else {
        this._yaw = value;
      }

      this._updateVisual();
    };

    const startDrag = (e) => {
      e.preventDefault();
      this._isDragging = true;
      handle.classList.add("dragging");
      updateFromEvent(e);
    };

    const moveDrag = (e) => {
      if (this._isDragging && handle.classList.contains("dragging")) {
        e.preventDefault();
        updateFromEvent(e);
      }
    };

    const endDrag = () => {
      this._isDragging = false;
      handle.classList.remove("dragging");
    };

    track.addEventListener("mousedown", startDrag);
    track.addEventListener("touchstart", startDrag, { passive: false });

    // Add document-level listeners and track them for cleanup
    document.addEventListener("mousemove", moveDrag);
    this._documentHandlers.push({ event: "mousemove", handler: moveDrag });

    document.addEventListener("touchmove", moveDrag, { passive: false });
    this._documentHandlers.push({ event: "touchmove", handler: moveDrag, options: { passive: false } });

    document.addEventListener("mouseup", endDrag);
    this._documentHandlers.push({ event: "mouseup", handler: endDrag });

    document.addEventListener("touchend", endDrag);
    this._documentHandlers.push({ event: "touchend", handler: endDrag });
  }

  _updateVisual() {
    // Update pitch slider
    const pitchHandle = this.shadowRoot.getElementById("pitch-handle");
    const pitchValue = this.shadowRoot.getElementById("pitch-value");
    if (pitchHandle && pitchValue) {
      const pitchPercent = (this._pitch + 90) / 180;
      pitchHandle.style.left = `${pitchPercent * 100}%`;
      const pitchSign = this._pitch >= 0 ? "+" : "";
      pitchValue.textContent = `${pitchSign}${this._pitch.toFixed(1)}`;
    }

    // Update yaw slider
    const yawHandle = this.shadowRoot.getElementById("yaw-handle");
    const yawValue = this.shadowRoot.getElementById("yaw-value");
    const yawDisplay = this.shadowRoot.getElementById("yaw-display");
    const needle = this.shadowRoot.getElementById("needle");
    if (yawHandle && yawValue) {
      const yawPercent = this._yaw / 360;
      yawHandle.style.left = `${yawPercent * 100}%`;
      yawValue.textContent = `${this._yaw.toFixed(1).padStart(5, "0")}`;
    }
    if (yawDisplay) {
      yawDisplay.textContent = `${this._yaw.toFixed(1).padStart(5, "0")}`;
    }

    // Rotate compass needle
    if (needle) {
      needle.style.transform = `translate(-50%, -100%) rotate(${this._yaw}deg)`;
    }

    // Update manual inputs if in manual mode
    if (this._inputMode === "manual") {
      this._updateManualInputs();
    }
  }

  _updateFromState() {
    const nav = stateManager.getNavigation();
    const heading = nav.heading || { pitch: 0, yaw: 0, roll: 0 };
    this._pitch = heading.pitch || 0;
    this._yaw = heading.yaw || 0;
    this._roll = heading.roll || 0;
    this._updateVisual();

    // Update current heading display
    const currentDisplay = this.shadowRoot.getElementById("current-display");
    if (currentDisplay) {
      const pSign = this._pitch >= 0 ? "+" : "";
      const rSign = this._roll >= 0 ? "+" : "";
      currentDisplay.textContent = `P: ${pSign}${this._pitch.toFixed(1)} | Y: ${this._yaw.toFixed(1)} | R: ${rSign}${this._roll.toFixed(1)}`;
    }
  }

  async _applyHeading() {
    // Get values from manual inputs if in manual mode
    if (this._inputMode === "manual") {
      const pitchInput = this.shadowRoot.getElementById("pitch-input");
      const yawInput = this.shadowRoot.getElementById("yaw-input");
      const rollInput = this.shadowRoot.getElementById("roll-input");

      this._pitch = parseFloat(pitchInput.value) || 0;
      this._yaw = parseFloat(yawInput.value) || 0;
      this._roll = parseFloat(rollInput.value) || 0;

      // Normalize values
      this._pitch = Math.max(-90, Math.min(90, this._pitch));
      this._yaw = ((this._yaw % 360) + 360) % 360;
      this._roll = Math.max(-180, Math.min(180, this._roll));
    }

    try {
      console.log("Applying heading:", { pitch: this._pitch, yaw: this._yaw, roll: this._roll });
      const response = await wsClient.sendShipCommand("set_orientation", {
        pitch: this._pitch,
        yaw: this._yaw,
        roll: this._roll
      });
      console.log("Heading response:", JSON.stringify(response, null, 2));

      // Check for errors in response
      if (response?.ok === false || response?.error) {
        const errorMsg = response.error || response.message || "Unknown error";
        console.error("Heading command error:", errorMsg);
        this._showMessage(`Heading error: ${errorMsg}`, "error");
        // Revert on error
        this._updateFromState();
      } else if (response?.ok === true) {
        // Response structure: {ok: true, response: {status: "...", target: {...}}}
        const result = response.response || response;
        if (result?.target) {
          // Update from server response if available
          const target = result.target;
          this._pitch = target.pitch ?? this._pitch;
          this._yaw = target.yaw ?? this._yaw;
          this._roll = target.roll ?? this._roll;
          this._updateVisual();
          console.log("Heading updated from response:", target);
        } else {
          // Command succeeded but no target in response - that's OK, state will update via polling
          console.log("Heading command succeeded, waiting for state update");
        }
        this._showMessage(`Heading set: P=${this._pitch.toFixed(1)} Y=${this._yaw.toFixed(1)} R=${this._roll.toFixed(1)}`, "success");
      } else {
        console.warn("Unexpected heading response format:", response);
      }
    } catch (error) {
      console.error("Heading command failed:", error);
      this._showMessage(`Heading failed: ${error.message}`, "error");
      // Revert on error
      this._updateFromState();
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }

  _resetToCurrentHeading() {
    this._updateFromState();
  }
}

customElements.define("heading-control", HeadingControl);
export { HeadingControl };
