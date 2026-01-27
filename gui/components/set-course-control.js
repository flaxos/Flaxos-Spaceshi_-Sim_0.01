/**
 * Set Course Control - Sprint B
 * Navigation component for setting course destinations with GoToPosition autopilot.
 *
 * Features:
 * - Coordinate input (X, Y, Z)
 * - Stop at destination toggle
 * - Tolerance and speed settings
 * - Course status display with phase tracking
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class SetCourseControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._courseActive = false;
    this._coursePhase = null;
    this._destination = null;
    this._distance = null;
    this._closingSpeed = null;
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
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateFromState();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .section-title {
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          margin-bottom: 12px;
        }

        /* Course Status */
        .course-status {
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 16px;
        }

        .status-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .status-row:last-child {
          margin-bottom: 0;
        }

        .status-label {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
        }

        .status-value.phase {
          font-weight: 600;
          padding: 2px 8px;
          border-radius: 4px;
          background: var(--bg-primary, #0a0a0f);
        }

        .phase-accelerate { color: var(--status-warning, #ffaa00); }
        .phase-coast { color: var(--status-info, #00aaff); }
        .phase-brake { color: var(--status-critical, #ff4444); }
        .phase-hold { color: var(--status-nominal, #00ff88); }

        .no-course {
          text-align: center;
          color: var(--text-dim, #555566);
          font-size: 0.8rem;
          padding: 8px;
        }

        /* Coordinate Inputs */
        .coord-inputs {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr;
          gap: 8px;
          margin-bottom: 12px;
        }

        .coord-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .coord-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .coord-input {
          padding: 8px;
          background: var(--bg-primary, #0a0a0f);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          text-align: center;
        }

        .coord-input:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        /* Options */
        .options-row {
          display: flex;
          gap: 16px;
          margin-bottom: 12px;
          align-items: center;
        }

        .option-group {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .option-label {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
        }

        .option-checkbox {
          width: 18px;
          height: 18px;
          accent-color: var(--status-info, #00aaff);
        }

        .option-input {
          width: 60px;
          padding: 4px 8px;
          background: var(--bg-primary, #0a0a0f);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          text-align: center;
        }

        /* Buttons */
        .button-row {
          display: flex;
          gap: 8px;
        }

        .set-course-btn {
          flex: 1;
          padding: 12px 16px;
          background: var(--status-info, #00aaff);
          border: none;
          border-radius: 6px;
          color: var(--bg-primary, #0a0a0f);
          font-weight: 600;
          font-size: 0.85rem;
          cursor: pointer;
        }

        .set-course-btn:hover {
          filter: brightness(1.1);
        }

        .set-course-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .cancel-btn {
          padding: 12px 16px;
          background: var(--status-critical, #ff4444);
          border: none;
          border-radius: 6px;
          color: var(--text-bright, #ffffff);
          font-weight: 600;
          font-size: 0.85rem;
          cursor: pointer;
        }

        .cancel-btn:hover {
          filter: brightness(1.1);
        }

        .cancel-btn.hidden {
          display: none;
        }

        /* Quick Destinations */
        .quick-section {
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .quick-destinations {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .quick-btn {
          padding: 6px 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-secondary, #888899);
          font-size: 0.7rem;
          cursor: pointer;
        }

        .quick-btn:hover {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }
      </style>

      <div class="section-title">Set Course</div>

      <!-- Course Status -->
      <div class="course-status" id="course-status">
        <div class="no-course" id="no-course">No active course</div>
        <div id="active-course" style="display: none;">
          <div class="status-row">
            <span class="status-label">Phase</span>
            <span class="status-value phase" id="course-phase">--</span>
          </div>
          <div class="status-row">
            <span class="status-label">Distance</span>
            <span class="status-value" id="course-distance">-- m</span>
          </div>
          <div class="status-row">
            <span class="status-label">Closing</span>
            <span class="status-value" id="course-closing">-- m/s</span>
          </div>
          <div class="status-row">
            <span class="status-label">Destination</span>
            <span class="status-value" id="course-dest">--</span>
          </div>
        </div>
      </div>

      <!-- Coordinate Inputs -->
      <div class="coord-inputs">
        <div class="coord-group">
          <label class="coord-label">X</label>
          <input type="number" class="coord-input" id="coord-x" value="0" step="100" />
        </div>
        <div class="coord-group">
          <label class="coord-label">Y</label>
          <input type="number" class="coord-input" id="coord-y" value="0" step="100" />
        </div>
        <div class="coord-group">
          <label class="coord-label">Z</label>
          <input type="number" class="coord-input" id="coord-z" value="0" step="100" />
        </div>
      </div>

      <!-- Options -->
      <div class="options-row">
        <div class="option-group">
          <input type="checkbox" class="option-checkbox" id="stop-at-target" checked />
          <label class="option-label" for="stop-at-target">Stop at target</label>
        </div>
        <div class="option-group">
          <label class="option-label">Tolerance</label>
          <input type="number" class="option-input" id="tolerance" value="50" min="1" step="10" />
          <span class="option-label">m</span>
        </div>
      </div>

      <!-- Buttons -->
      <div class="button-row">
        <button class="set-course-btn" id="set-course-btn">SET COURSE</button>
        <button class="cancel-btn hidden" id="cancel-btn">CANCEL</button>
      </div>

      <!-- Quick Destinations -->
      <div class="quick-section">
        <div class="section-title">Quick Destinations</div>
        <div class="quick-destinations">
          <button class="quick-btn" data-x="1000" data-y="0" data-z="0">+1km X</button>
          <button class="quick-btn" data-x="0" data-y="1000" data-z="0">+1km Y</button>
          <button class="quick-btn" data-x="0" data-y="0" data-z="1000">+1km Z</button>
          <button class="quick-btn" data-x="10000" data-y="0" data-z="0">+10km X</button>
          <button class="quick-btn" data-x="0" data-y="0" data-z="0">Origin</button>
        </div>
      </div>
    `;
  }

  _setupInteraction() {
    const setCourseBtn = this.shadowRoot.getElementById("set-course-btn");
    const cancelBtn = this.shadowRoot.getElementById("cancel-btn");
    const quickBtns = this.shadowRoot.querySelectorAll(".quick-btn");

    setCourseBtn.addEventListener("click", () => this._setCourse());
    cancelBtn.addEventListener("click", () => this._cancelCourse());

    // Quick destination buttons
    quickBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const x = parseFloat(btn.dataset.x) || 0;
        const y = parseFloat(btn.dataset.y) || 0;
        const z = parseFloat(btn.dataset.z) || 0;
        this.shadowRoot.getElementById("coord-x").value = x;
        this.shadowRoot.getElementById("coord-y").value = y;
        this.shadowRoot.getElementById("coord-z").value = z;
      });
    });

    // Enter key to set course
    const coordInputs = this.shadowRoot.querySelectorAll(".coord-input");
    coordInputs.forEach(input => {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          this._setCourse();
        }
      });
    });
  }

  _updateFromState() {
    const ship = stateManager.getShipState();
    const navigation = ship?.systems?.navigation || {};
    const course = navigation.course || {};

    this._courseActive = course.active || false;
    this._coursePhase = course.phase || null;
    this._destination = course.destination || null;
    this._distance = course.distance || null;
    this._closingSpeed = course.closing_speed || null;

    this._updateCourseDisplay();
  }

  _updateCourseDisplay() {
    const noCourse = this.shadowRoot.getElementById("no-course");
    const activeCourse = this.shadowRoot.getElementById("active-course");
    const cancelBtn = this.shadowRoot.getElementById("cancel-btn");
    const phaseEl = this.shadowRoot.getElementById("course-phase");
    const distanceEl = this.shadowRoot.getElementById("course-distance");
    const closingEl = this.shadowRoot.getElementById("course-closing");
    const destEl = this.shadowRoot.getElementById("course-dest");

    if (this._courseActive) {
      noCourse.style.display = "none";
      activeCourse.style.display = "block";
      cancelBtn.classList.remove("hidden");

      // Update phase with color coding
      if (phaseEl && this._coursePhase) {
        phaseEl.textContent = this._coursePhase;
        phaseEl.className = "status-value phase";
        const phaseLower = this._coursePhase.toLowerCase();
        if (phaseLower.includes("accelerate")) {
          phaseEl.classList.add("phase-accelerate");
        } else if (phaseLower.includes("coast")) {
          phaseEl.classList.add("phase-coast");
        } else if (phaseLower.includes("brake")) {
          phaseEl.classList.add("phase-brake");
        } else if (phaseLower.includes("hold")) {
          phaseEl.classList.add("phase-hold");
        }
      }

      // Update distance
      if (distanceEl && this._distance !== null) {
        if (this._distance > 1000) {
          distanceEl.textContent = `${(this._distance / 1000).toFixed(2)} km`;
        } else {
          distanceEl.textContent = `${this._distance.toFixed(1)} m`;
        }
      }

      // Update closing speed
      if (closingEl && this._closingSpeed !== null) {
        closingEl.textContent = `${this._closingSpeed.toFixed(1)} m/s`;
      }

      // Update destination
      if (destEl && this._destination) {
        const x = this._destination.x?.toFixed(0) || 0;
        const y = this._destination.y?.toFixed(0) || 0;
        const z = this._destination.z?.toFixed(0) || 0;
        destEl.textContent = `(${x}, ${y}, ${z})`;
      }
    } else {
      noCourse.style.display = "block";
      activeCourse.style.display = "none";
      cancelBtn.classList.add("hidden");
    }
  }

  async _setCourse() {
    const x = parseFloat(this.shadowRoot.getElementById("coord-x").value) || 0;
    const y = parseFloat(this.shadowRoot.getElementById("coord-y").value) || 0;
    const z = parseFloat(this.shadowRoot.getElementById("coord-z").value) || 0;
    const stop = this.shadowRoot.getElementById("stop-at-target").checked;
    const tolerance = parseFloat(this.shadowRoot.getElementById("tolerance").value) || 50;

    try {
      console.log(`Setting course to (${x}, ${y}, ${z}), stop=${stop}, tolerance=${tolerance}`);
      const response = await wsClient.sendShipCommand("set_course", {
        x, y, z, stop, tolerance
      });
      console.log("Set course response:", response);

      if (response?.ok) {
        this._showMessage(`Course set to (${x}, ${y}, ${z})`, "success");
      } else {
        this._showMessage(response?.error || "Failed to set course", "error");
      }
    } catch (error) {
      console.error("Set course failed:", error);
      this._showMessage(`Set course failed: ${error.message}`, "error");
    }
  }

  async _cancelCourse() {
    try {
      console.log("Canceling course (disengaging autopilot)...");
      const response = await wsClient.sendShipCommand("autopilot", {
        program: "off"
      });
      console.log("Cancel course response:", response);

      if (response?.ok) {
        this._showMessage("Course canceled", "success");
      } else {
        this._showMessage(response?.error || "Failed to cancel course", "error");
      }
    } catch (error) {
      console.error("Cancel course failed:", error);
      this._showMessage(`Cancel failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("set-course-control", SetCourseControl);
export { SetCourseControl };
