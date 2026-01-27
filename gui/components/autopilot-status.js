/**
 * Autopilot Status Display - Sprint B
 * Shows current autopilot state, phase, and navigation information.
 *
 * Features:
 * - Current autopilot program display
 * - Phase progress indicator (ACCELERATE → COAST → BRAKE → HOLD)
 * - Distance, closing speed, ETA
 * - Quick autopilot controls
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

// Autopilot phases for GoToPosition
const PHASES = ["ACCELERATE", "COAST", "BRAKE", "HOLD"];

class AutopilotStatus extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._program = null;
    this._phase = null;
    this._status = null;
    this._mode = "manual";
    this._courseInfo = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
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
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .autopilot-panel {
          background: var(--bg-secondary, #12121a);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          padding: 12px;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .title {
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
        }

        .mode-badge {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 600;
          padding: 3px 8px;
          border-radius: 4px;
        }

        .mode-badge.manual {
          background: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .mode-badge.autopilot {
          background: var(--status-nominal, #00ff88);
          color: var(--bg-primary, #0a0a0f);
        }

        .mode-badge.override {
          background: var(--status-warning, #ffaa00);
          color: var(--bg-primary, #0a0a0f);
        }

        /* Program Display */
        .program-display {
          text-align: center;
          margin-bottom: 12px;
        }

        .program-name {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.1rem;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 4px;
        }

        .program-status {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
        }

        .no-autopilot {
          text-align: center;
          color: var(--text-dim, #555566);
          font-size: 0.8rem;
          padding: 16px 0;
        }

        /* Phase Progress */
        .phase-progress {
          margin-bottom: 12px;
        }

        .phase-bar {
          display: flex;
          gap: 4px;
          margin-bottom: 4px;
        }

        .phase-segment {
          flex: 1;
          height: 6px;
          background: var(--bg-primary, #0a0a0f);
          border-radius: 3px;
          transition: background 0.3s ease;
        }

        .phase-segment.active {
          background: var(--status-info, #00aaff);
        }

        .phase-segment.completed {
          background: var(--status-nominal, #00ff88);
        }

        .phase-segment.accelerate.active { background: var(--status-warning, #ffaa00); }
        .phase-segment.coast.active { background: var(--status-info, #00aaff); }
        .phase-segment.brake.active { background: var(--status-critical, #ff4444); }
        .phase-segment.hold.active { background: var(--status-nominal, #00ff88); }

        .phase-labels {
          display: flex;
          justify-content: space-between;
        }

        .phase-label {
          font-size: 0.55rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .phase-label.active {
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        /* Info Grid */
        .info-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
          margin-bottom: 12px;
        }

        .info-item {
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          padding: 8px;
          text-align: center;
        }

        .info-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-bottom: 2px;
        }

        .info-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
        }

        /* Quick Controls */
        .quick-controls {
          display: flex;
          gap: 8px;
        }

        .quick-btn {
          flex: 1;
          padding: 8px;
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

        .quick-btn.disengage {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .quick-btn.disengage:hover {
          background: var(--status-critical, #ff4444);
          color: var(--bg-primary, #0a0a0f);
        }
      </style>

      <div class="autopilot-panel">
        <div class="header">
          <span class="title">Autopilot</span>
          <span class="mode-badge manual" id="mode-badge">MANUAL</span>
        </div>

        <div id="autopilot-content">
          <div class="no-autopilot" id="no-autopilot">
            No autopilot program active<br>
            <small>Use Set Course or select a target</small>
          </div>

          <div id="autopilot-active" style="display: none;">
            <div class="program-display">
              <div class="program-name" id="program-name">--</div>
              <div class="program-status" id="program-status">--</div>
            </div>

            <div class="phase-progress" id="phase-progress">
              <div class="phase-bar">
                <div class="phase-segment accelerate" data-phase="ACCELERATE"></div>
                <div class="phase-segment coast" data-phase="COAST"></div>
                <div class="phase-segment brake" data-phase="BRAKE"></div>
                <div class="phase-segment hold" data-phase="HOLD"></div>
              </div>
              <div class="phase-labels">
                <span class="phase-label" data-phase="ACCELERATE">Accel</span>
                <span class="phase-label" data-phase="COAST">Coast</span>
                <span class="phase-label" data-phase="BRAKE">Brake</span>
                <span class="phase-label" data-phase="HOLD">Hold</span>
              </div>
            </div>

            <div class="info-grid">
              <div class="info-item">
                <div class="info-label">Distance</div>
                <div class="info-value" id="info-distance">--</div>
              </div>
              <div class="info-item">
                <div class="info-label">Closing</div>
                <div class="info-value" id="info-closing">--</div>
              </div>
              <div class="info-item">
                <div class="info-label">Braking Dist</div>
                <div class="info-value" id="info-braking">--</div>
              </div>
              <div class="info-item">
                <div class="info-label">Target</div>
                <div class="info-value" id="info-target">--</div>
              </div>
            </div>

            <div class="quick-controls">
              <button class="quick-btn" id="hold-btn">HOLD POSITION</button>
              <button class="quick-btn disengage" id="disengage-btn">DISENGAGE</button>
            </div>
          </div>
        </div>
      </div>
    `;

    this._setupControls();
  }

  _setupControls() {
    const holdBtn = this.shadowRoot.getElementById("hold-btn");
    const disengageBtn = this.shadowRoot.getElementById("disengage-btn");

    holdBtn?.addEventListener("click", () => this._engageHold());
    disengageBtn?.addEventListener("click", () => this._disengage());
  }

  _updateFromState() {
    const ship = stateManager.getShipState();
    const navigation = ship?.systems?.navigation || {};
    const helm = ship?.systems?.helm || {};

    this._mode = navigation.mode || helm.mode || "manual";
    this._program = navigation.current_program || helm.autopilot_program || null;
    this._status = navigation.autopilot_state?.status || null;

    // Get course info
    this._courseInfo = navigation.course || navigation.autopilot_state || null;
    if (this._courseInfo) {
      this._phase = this._courseInfo.phase || null;
    }

    this._updateDisplay();
  }

  _updateDisplay() {
    const modeBadge = this.shadowRoot.getElementById("mode-badge");
    const noAutopilot = this.shadowRoot.getElementById("no-autopilot");
    const autopilotActive = this.shadowRoot.getElementById("autopilot-active");
    const programName = this.shadowRoot.getElementById("program-name");
    const programStatus = this.shadowRoot.getElementById("program-status");

    // Update mode badge
    if (modeBadge) {
      modeBadge.classList.remove("manual", "autopilot", "override");
      if (this._mode === "autopilot" || this._program) {
        modeBadge.textContent = "AUTOPILOT";
        modeBadge.classList.add("autopilot");
      } else if (this._mode === "manual_override") {
        modeBadge.textContent = "OVERRIDE";
        modeBadge.classList.add("override");
      } else {
        modeBadge.textContent = "MANUAL";
        modeBadge.classList.add("manual");
      }
    }

    // Show/hide autopilot content
    if (this._program) {
      noAutopilot.style.display = "none";
      autopilotActive.style.display = "block";

      // Update program name
      if (programName) {
        programName.textContent = this._formatProgramName(this._program);
      }

      // Update status
      if (programStatus) {
        programStatus.textContent = this._status || "Active";
      }

      // Update phase progress
      this._updatePhaseProgress();

      // Update info grid
      this._updateInfoGrid();
    } else {
      noAutopilot.style.display = "block";
      autopilotActive.style.display = "none";
    }
  }

  _formatProgramName(program) {
    if (!program) return "--";
    return program.toUpperCase().replace(/_/g, " ");
  }

  _updatePhaseProgress() {
    const segments = this.shadowRoot.querySelectorAll(".phase-segment");
    const labels = this.shadowRoot.querySelectorAll(".phase-label");
    const currentPhase = this._phase?.toUpperCase() || null;
    const currentIndex = PHASES.indexOf(currentPhase);

    segments.forEach((segment, index) => {
      segment.classList.remove("active", "completed");
      if (index < currentIndex) {
        segment.classList.add("completed");
      } else if (index === currentIndex) {
        segment.classList.add("active");
      }
    });

    labels.forEach((label, index) => {
      label.classList.remove("active");
      if (index === currentIndex) {
        label.classList.add("active");
      }
    });
  }

  _updateInfoGrid() {
    const distanceEl = this.shadowRoot.getElementById("info-distance");
    const closingEl = this.shadowRoot.getElementById("info-closing");
    const brakingEl = this.shadowRoot.getElementById("info-braking");
    const targetEl = this.shadowRoot.getElementById("info-target");

    if (this._courseInfo) {
      // Distance
      if (distanceEl) {
        const dist = this._courseInfo.distance;
        if (dist !== null && dist !== undefined) {
          if (dist > 1000) {
            distanceEl.textContent = `${(dist / 1000).toFixed(2)} km`;
          } else {
            distanceEl.textContent = `${dist.toFixed(1)} m`;
          }
        } else {
          distanceEl.textContent = "--";
        }
      }

      // Closing speed
      if (closingEl) {
        const closing = this._courseInfo.closing_speed;
        if (closing !== null && closing !== undefined) {
          closingEl.textContent = `${closing.toFixed(1)} m/s`;
        } else {
          closingEl.textContent = "--";
        }
      }

      // Braking distance
      if (brakingEl) {
        const braking = this._courseInfo.braking_distance;
        if (braking !== null && braking !== undefined) {
          if (braking > 1000) {
            brakingEl.textContent = `${(braking / 1000).toFixed(2)} km`;
          } else {
            brakingEl.textContent = `${braking.toFixed(1)} m`;
          }
        } else {
          brakingEl.textContent = "--";
        }
      }

      // Target/destination
      if (targetEl) {
        const dest = this._courseInfo.destination;
        if (dest) {
          const x = dest.x?.toFixed(0) || 0;
          const y = dest.y?.toFixed(0) || 0;
          const z = dest.z?.toFixed(0) || 0;
          targetEl.textContent = `(${x}, ${y}, ${z})`;
        } else {
          targetEl.textContent = "--";
        }
      }
    }
  }

  async _engageHold() {
    try {
      const response = await wsClient.sendShipCommand("autopilot", {
        program: "hold"
      });
      if (response?.ok) {
        this._showMessage("Hold position engaged", "success");
      } else {
        this._showMessage(response?.error || "Failed to engage hold", "error");
      }
    } catch (error) {
      this._showMessage(`Hold failed: ${error.message}`, "error");
    }
  }

  async _disengage() {
    try {
      const response = await wsClient.sendShipCommand("autopilot", {
        program: "off"
      });
      if (response?.ok) {
        this._showMessage("Autopilot disengaged", "success");
      } else {
        this._showMessage(response?.error || "Failed to disengage", "error");
      }
    } catch (error) {
      this._showMessage(`Disengage failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("autopilot-status", AutopilotStatus);
export { AutopilotStatus };
