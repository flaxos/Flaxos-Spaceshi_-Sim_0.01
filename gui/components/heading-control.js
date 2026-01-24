/**
 * Heading Control
 * Pitch and yaw sliders with visual compass
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
    this._isDragging = false;
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
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
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
      </style>

      <div class="compass-container">
        <div class="compass">
          <span class="compass-label north">000</span>
          <span class="compass-label east">090</span>
          <span class="compass-label south">180</span>
          <span class="compass-label west">270</span>
          <div class="compass-needle" id="needle"></div>
          <div class="compass-center"></div>
          <div class="yaw-display" id="yaw-display">000.0°</div>
        </div>
      </div>

      <div class="sliders">
        <div class="slider-group">
          <div class="slider-header">
            <span class="slider-label">Pitch</span>
            <span class="slider-value" id="pitch-value">+0.0°</span>
          </div>
          <div class="slider-track" id="pitch-track">
            <div class="slider-handle" id="pitch-handle"></div>
          </div>
        </div>

        <div class="slider-group">
          <div class="slider-header">
            <span class="slider-label">Yaw</span>
            <span class="slider-value" id="yaw-value">000.0°</span>
          </div>
          <div class="slider-track" id="yaw-track">
            <div class="slider-handle" id="yaw-handle"></div>
          </div>
        </div>
      </div>

      <div class="buttons">
        <button class="btn primary" id="apply-btn">Apply</button>
        <button class="btn" id="reset-btn">Reset</button>
      </div>
    `;
  }

  _setupInteraction() {
    // Pitch slider
    this._setupSlider("pitch", -90, 90);

    // Yaw slider
    this._setupSlider("yaw", 0, 360);

    // Buttons
    this.shadowRoot.getElementById("apply-btn").addEventListener("click", () => {
      this._applyHeading();
    });

    this.shadowRoot.getElementById("reset-btn").addEventListener("click", () => {
      this._resetToCurrentHeading();
    });
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
    // Update pitch
    const pitchHandle = this.shadowRoot.getElementById("pitch-handle");
    const pitchValue = this.shadowRoot.getElementById("pitch-value");
    const pitchPercent = (this._pitch + 90) / 180;
    pitchHandle.style.left = `${pitchPercent * 100}%`;
    const pitchSign = this._pitch >= 0 ? "+" : "";
    pitchValue.textContent = `${pitchSign}${this._pitch.toFixed(1)}°`;

    // Update yaw
    const yawHandle = this.shadowRoot.getElementById("yaw-handle");
    const yawValue = this.shadowRoot.getElementById("yaw-value");
    const yawDisplay = this.shadowRoot.getElementById("yaw-display");
    const needle = this.shadowRoot.getElementById("needle");
    const yawPercent = this._yaw / 360;
    yawHandle.style.left = `${yawPercent * 100}%`;
    yawValue.textContent = `${this._yaw.toFixed(1).padStart(5, "0")}°`;
    yawDisplay.textContent = `${this._yaw.toFixed(1).padStart(5, "0")}°`;

    // Rotate compass needle
    needle.style.transform = `translate(-50%, -100%) rotate(${this._yaw}deg)`;
  }

  _updateFromState() {
    const nav = stateManager.getNavigation();
    const heading = nav.heading || { pitch: 0, yaw: 0 };
    this._pitch = heading.pitch || 0;
    this._yaw = heading.yaw || 0;
    this._updateVisual();
  }

  async _applyHeading() {
    try {
      console.log("Applying heading:", { pitch: this._pitch, yaw: this._yaw, roll: 0 });
      const response = await wsClient.sendShipCommand("set_orientation", {
        pitch: this._pitch,
        yaw: this._yaw,
        roll: 0
      });
      console.log("Heading response:", response);
      
      if (response?.error) {
        this._showMessage(`Heading error: ${response.error}`, "error");
      }
    } catch (error) {
      console.error("Heading command failed:", error);
      this._showMessage(`Heading failed: ${error.message}`, "error");
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
