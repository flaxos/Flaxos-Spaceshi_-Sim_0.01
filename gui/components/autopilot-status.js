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

// Phase lists for different autopilot programs.
// GoToPosition uses uppercase, Rendezvous uses lowercase, Intercept has its own set.
// We normalise to uppercase for display and map them into a common ordered list.
const GOTO_PHASES = ["ACCELERATE", "COAST", "FLIP", "BRAKE", "ZERO", "HOLD"];
const RENDEZVOUS_PHASES = ["BURN", "FLIP", "BRAKE", "APPROACH_DECEL", "APPROACH_ROTATE", "APPROACH_COAST", "STATIONKEEP"];
// InterceptAutopilot now subclasses RendezvousAutopilot — same phases
const INTERCEPT_PHASES = RENDEZVOUS_PHASES;
const ALL_STOP_PHASES = ["CUT", "FLIP", "BRAKE", "ZERO", "HOLD"];

// Map program names to their phase lists
const PROGRAM_PHASES = {
  goto_position: GOTO_PHASES,
  set_course: GOTO_PHASES,
  rendezvous: RENDEZVOUS_PHASES,
  intercept: INTERCEPT_PHASES,
  all_stop: ALL_STOP_PHASES,
  stop: ALL_STOP_PHASES,
};

// Default fallback
const DEFAULT_PHASES = GOTO_PHASES;

class AutopilotStatus extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._program = null;
    this._phase = null;
    this._status = null;
    this._mode = "manual";
    this._apState = null;
    this._range = null;
    this._closingSpeed = null;
    this._brakingDistance = null;
    this._eta = null;
    this._statusText = null;
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

        /* GoToPosition phases */
        .phase-segment.accelerate.active { background: var(--status-warning, #ffaa00); }
        .phase-segment.coast.active { background: var(--status-info, #00aaff); }
        .phase-segment.brake.active { background: var(--status-critical, #ff4444); }
        .phase-segment.hold.active { background: var(--status-nominal, #00ff88); }
        /* Rendezvous phases */
        .phase-segment.burn.active { background: var(--status-warning, #ffaa00); }
        .phase-segment.flip.active { background: #cc66ff; }
        .phase-segment.approach_decel.active { background: var(--status-critical, #ff4444); }
        .phase-segment.approach_rotate.active { background: #cc66ff; }
        .phase-segment.approach_coast.active { background: var(--status-info, #00aaff); }
        .phase-segment.stationkeep.active { background: var(--status-nominal, #00ff88); }
        /* Intercept phases */
        .phase-segment.intercept.active { background: var(--status-warning, #ffaa00); }
        .phase-segment.approach.active { background: var(--status-info, #00aaff); }
        .phase-segment.match.active { background: var(--status-nominal, #00ff88); }

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

        /* Status Text */
        .status-text {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
          text-align: center;
          padding: 6px 8px;
          margin-bottom: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          font-style: italic;
          min-height: 1.4em;
        }

        .status-text:empty {
          display: none;
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

        .quick-btn.all-stop {
          border-color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.15);
          color: var(--status-critical, #ff4444);
          font-weight: 600;
        }

        .quick-btn.all-stop:hover {
          background: var(--status-critical, #ff4444);
          color: var(--bg-primary, #0a0a0f);
        }

        /* All-stop phase segment colors */
        .phase-segment.cut.active { background: var(--status-critical, #ff4444); }
        .phase-segment.zero.active { background: var(--status-warning, #ffaa00); }
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
              <div class="phase-bar" id="phase-bar"></div>
              <div class="phase-labels" id="phase-labels"></div>
            </div>

            <div class="status-text" id="status-text"></div>

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
                <div class="info-label" id="info-braking-label">Braking Dist</div>
                <div class="info-value" id="info-braking">--</div>
              </div>
              <div class="info-item">
                <div class="info-label">ETA</div>
                <div class="info-value" id="info-eta">--</div>
              </div>
            </div>

            <div class="quick-controls">
              <button class="quick-btn" id="hold-btn">HOLD POSITION</button>
              <button class="quick-btn all-stop" id="all-stop-btn" title="Kill all velocity (X)">ALL STOP</button>
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
    const allStopBtn = this.shadowRoot.getElementById("all-stop-btn");
    const disengageBtn = this.shadowRoot.getElementById("disengage-btn");

    holdBtn?.addEventListener("click", () => this._engageHold());
    allStopBtn?.addEventListener("click", () => this._allStop());
    disengageBtn?.addEventListener("click", () => this._disengage());
  }

  _updateFromState() {
    const ship = stateManager.getShipState();
    const navigation = ship?.systems?.navigation || {};
    const helm = ship?.systems?.helm || {};
    // Station-filtered HELM view nests autopilot data under ship.autopilot
    const ap = ship?.autopilot || {};

    // Check all possible paths for mode and program name
    this._mode = ship?.nav_mode || ap.mode || navigation.mode || helm.mode || "manual";
    this._program = ship?.autopilot_program || ap.program || navigation.current_program || helm.autopilot_program || null;

    // Autopilot state dict -- the rich data from the autopilot's get_state().
    // Telemetry puts it at top-level as "autopilot_state", station filter
    // nests it under "autopilot.autopilot_state", and navigation system
    // exposes it via systems.navigation.autopilot_state.
    const apState = ship?.autopilot_state
      || ap.autopilot_state
      || navigation.autopilot_state
      || null;

    this._status = apState?.status || null;
    this._apState = apState;

    // Phase from autopilot state (normalise to uppercase for display)
    this._phase = apState?.phase?.toUpperCase() || null;

    // Extract numeric fields -- autopilots use "range" or "distance" depending on type
    this._range = apState?.range ?? apState?.distance ?? null;
    this._closingSpeed = apState?.closing_speed ?? null;
    this._brakingDistance = apState?.braking_distance ?? null;
    this._eta = apState?.time_to_arrival ?? null;
    this._statusText = apState?.status_text ?? null;
    this._flipInM = apState?.flip_in_m ?? null;
    this._flipInS = apState?.flip_in_s ?? null;

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
    const bar = this.shadowRoot.getElementById("phase-bar");
    const labelsContainer = this.shadowRoot.getElementById("phase-labels");
    if (!bar || !labelsContainer) return;

    // Pick the phase list for the current program
    const programKey = this._program?.toLowerCase() || "";
    const phases = PROGRAM_PHASES[programKey] || DEFAULT_PHASES;
    const currentPhase = this._phase || null;
    const currentIndex = phases.indexOf(currentPhase);

    // Rebuild segments and labels to match the active program's phases
    bar.innerHTML = phases.map(
      (p) => `<div class="phase-segment ${p.toLowerCase()}" data-phase="${p}"></div>`
    ).join("");
    labelsContainer.innerHTML = phases.map(
      (p) => `<span class="phase-label" data-phase="${p}">${this._shortPhaseLabel(p)}</span>`
    ).join("");

    // Apply active/completed classes
    bar.querySelectorAll(".phase-segment").forEach((seg, i) => {
      if (i < currentIndex) seg.classList.add("completed");
      else if (i === currentIndex) seg.classList.add("active");
    });
    labelsContainer.querySelectorAll(".phase-label").forEach((lbl, i) => {
      if (i === currentIndex) lbl.classList.add("active");
    });
  }

  /** Short display label for a phase name */
  _shortPhaseLabel(phase) {
    const labels = {
      ACCELERATE: "Accel",
      COAST: "Coast",
      BRAKE: "Brake",
      HOLD: "Hold",
      BURN: "Burn",
      FLIP: "Flip",
      APPROACH_DECEL: "Decel",
      APPROACH_ROTATE: "Rotate",
      APPROACH_COAST: "Coast",
      STATIONKEEP: "Dock",
      INTERCEPT: "Intrcpt",
      APPROACH: "Approach",
      MATCH: "Match",
      CUT: "Cut",
      ZERO: "Zero",
    };
    return labels[phase] || phase;
  }

  _updateInfoGrid() {
    const distanceEl = this.shadowRoot.getElementById("info-distance");
    const closingEl = this.shadowRoot.getElementById("info-closing");
    const brakingEl = this.shadowRoot.getElementById("info-braking");
    const etaEl = this.shadowRoot.getElementById("info-eta");
    const statusTextEl = this.shadowRoot.getElementById("status-text");

    // Distance (use normalised _range which covers both "range" and "distance" fields)
    if (distanceEl) {
      distanceEl.textContent = this._formatDistance(this._range);
    }

    // Closing speed
    if (closingEl) {
      closingEl.textContent = this._closingSpeed != null
        ? `${this._closingSpeed.toFixed(1)} m/s`
        : "--";
    }

    // In BURN phase show flip countdown; otherwise show braking distance
    const brakingLabelEl = this.shadowRoot.getElementById("info-braking-label");
    if (brakingEl) {
      if (this._phase === "BURN" && this._flipInM != null) {
        if (brakingLabelEl) brakingLabelEl.textContent = "Flip In";
        const dist = this._formatDistance(this._flipInM);
        const t = this._formatEta(this._flipInS);
        brakingEl.textContent = `${dist} / ~${t}`;
      } else {
        if (brakingLabelEl) brakingLabelEl.textContent = "Braking Dist";
        brakingEl.textContent = this._formatDistance(this._brakingDistance);
      }
    }

    // ETA
    if (etaEl) {
      etaEl.textContent = this._formatEta(this._eta);
    }

    // Human-readable status text from the autopilot
    if (statusTextEl) {
      statusTextEl.textContent = this._statusText || "";
    }
  }

  /** Format a distance in metres for display: "427.3 km" or "850 m" */
  _formatDistance(metres) {
    if (metres == null) return "--";
    if (metres >= 1000) {
      return `${(metres / 1000).toFixed(1)} km`;
    }
    return `${metres.toFixed(0)} m`;
  }

  /** Format seconds into "Xm Ys" or "Xs" */
  _formatEta(seconds) {
    if (seconds == null) return "--";
    if (seconds <= 0) return "0s";
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    if (m < 60) return `${m}m ${String(s).padStart(2, "0")}s`;
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return `${h}h ${String(rm).padStart(2, "0")}m`;
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

  async _allStop() {
    try {
      const response = await wsClient.sendShipCommand("autopilot", {
        program: "all_stop",
        g_level: 1.0
      });
      if (response?.ok) {
        this._showMessage("All stop engaged", "success");
      } else {
        this._showMessage(response?.error || "Failed to engage all stop", "error");
      }
    } catch (error) {
      this._showMessage(`All stop failed: ${error.message}`, "error");
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
