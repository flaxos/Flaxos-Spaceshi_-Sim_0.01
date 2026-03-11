/**
 * Flight Computer Panel
 * Displays server-side flight computer status and provides quick command buttons.
 * Subscribes to stateManager for autopilot/navigation state.
 * Sends autopilot + set_course commands via wsClient.sendShipCommand().
 *
 * Command mapping:
 *   Navigate  -> sendShipCommand("set_course", {x, y, z})
 *   Rendezvous, Intercept, Match Vel -> sendShipCommand("autopilot", {program, target})
 *   Hold, Cruise, Orbit, Evasive     -> sendShipCommand("autopilot", {program})
 *   Manual / Abort                    -> sendShipCommand("autopilot", {program: "off"})
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class FlightComputerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._fcState = null;
    this._showCoordinateInput = false;
    this._selectedTarget = null;
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
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._fcState = this._extractAutopilotState();
      this._updateDisplay();
    });
  }

  /**
   * Extract autopilot state from navigation telemetry.
   * Server puts autopilot data in multiple paths depending on station filtering.
   */
  _extractAutopilotState() {
    const nav = stateManager.getNavigation();
    const autopilot = nav?.autopilot;
    const ship = stateManager.getShipState();

    // Build a unified state object from whichever path has data
    const mode = autopilot?.mode || ship?.nav_mode || ship?.autopilot?.mode || null;
    const program = autopilot?.program || ship?.autopilot_program || null;
    const phase = autopilot?.phase || autopilot?.autopilot_state || ship?.autopilot?.autopilot_state || null;
    const target = autopilot?.target || autopilot?.course?.target || null;

    if (!mode || mode === "off" || mode === "manual") {
      return null;
    }

    return {
      mode: "executing",
      command: (program || mode).toUpperCase(),
      phase: phase,
      target: target,
      status_text: target ? `Target: ${target}` : "",
      // These may come from burn plan data if available
      progress: autopilot?.progress,
      eta: autopilot?.eta,
      burn_plan: autopilot?.burn_plan,
      delta_v: autopilot?.delta_v,
    };
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        /* Mode display */
        .mode-display {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          margin-bottom: 16px;
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .mode-badge {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.1rem;
          font-weight: 700;
          letter-spacing: 2px;
          padding: 4px 12px;
          border-radius: 4px;
        }

        .mode-badge.idle {
          color: var(--text-dim, #555566);
          background: rgba(85, 85, 102, 0.15);
        }

        .mode-badge.executing {
          color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.1);
          animation: pulse-glow 2s ease-in-out infinite;
        }

        .mode-badge.manual {
          color: var(--status-info, #00aaff);
          background: rgba(0, 170, 255, 0.1);
        }

        @keyframes pulse-glow {
          0%, 100% { box-shadow: 0 0 4px rgba(0, 255, 136, 0.2); }
          50% { box-shadow: 0 0 12px rgba(0, 255, 136, 0.4); }
        }

        .mode-info {
          flex: 1;
          font-size: 0.8rem;
        }

        .mode-command {
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        .mode-phase {
          color: var(--text-secondary, #888899);
          font-size: 0.75rem;
        }

        .mode-status-text {
          color: var(--text-dim, #555566);
          font-size: 0.7rem;
          margin-top: 2px;
        }

        /* Progress bar */
        .progress-section {
          margin-bottom: 16px;
        }

        .progress-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 4px;
          font-size: 0.75rem;
        }

        .progress-label {
          color: var(--text-secondary, #888899);
        }

        .progress-eta {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .progress-bar {
          height: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
        }

        .progress-fill {
          height: 100%;
          background: var(--status-info, #00aaff);
          border-radius: 4px;
          transition: width 0.5s ease;
        }

        /* Burn plan details */
        .burn-details {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-bottom: 16px;
          padding: 10px;
          background: rgba(0, 170, 255, 0.05);
          border: 1px solid rgba(0, 170, 255, 0.15);
          border-radius: 6px;
        }

        .burn-item {
          text-align: center;
        }

        .burn-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .burn-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        /* Quick command buttons */
        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .command-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 6px;
          margin-bottom: 12px;
        }

        .cmd-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 2px;
          padding: 10px 6px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-secondary, #888899);
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          cursor: pointer;
          transition: all 0.1s ease;
          min-height: 44px;
          letter-spacing: 0.3px;
        }

        .cmd-label {
          font-size: 0.7rem;
          font-weight: 600;
        }

        .cmd-subtitle {
          font-size: 0.55rem;
          font-weight: 400;
          opacity: 0.6;
          letter-spacing: 0.3px;
          text-transform: lowercase;
        }

        .cmd-btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
          color: var(--text-primary, #e0e0e0);
        }

        .cmd-btn:active:not(:disabled) {
          transform: scale(0.96);
        }

        .cmd-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .cmd-btn.active {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .cmd-btn.danger {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .cmd-btn.danger:hover:not(:disabled) {
          background: rgba(255, 68, 68, 0.15);
          border-color: var(--status-critical, #ff4444);
        }

        .cmd-btn.wide {
          grid-column: span 2;
        }

        /* Coordinate input overlay */
        .coord-input-section {
          display: none;
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          margin-bottom: 12px;
        }

        .coord-input-section.visible {
          display: block;
        }

        .coord-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-bottom: 10px;
        }

        .coord-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .coord-group label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          text-align: center;
        }

        .coord-group input {
          padding: 8px;
          background: var(--bg-primary, #0a0a0f);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          text-align: center;
          min-height: 36px;
        }

        .coord-group input:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .coord-actions {
          display: flex;
          gap: 8px;
        }

        .coord-actions button {
          flex: 1;
          padding: 8px;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 36px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .coord-go-btn {
          background: var(--status-nominal, #00ff88);
          border: none;
          color: var(--bg-primary, #0a0a0f);
        }

        .coord-cancel-btn {
          background: transparent;
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-secondary, #888899);
        }

        /* Target select for intercept */
        .target-section {
          display: none;
          margin-bottom: 12px;
        }

        .target-section.visible {
          display: block;
        }

        .target-select {
          width: 100%;
          padding: 8px 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          min-height: 36px;
        }

        .target-select:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .hidden {
          display: none !important;
        }

        @media (max-width: 768px) {
          .command-grid {
            grid-template-columns: repeat(3, 1fr);
          }

          .burn-details {
            grid-template-columns: repeat(2, 1fr);
          }
        }
      </style>

      <!-- Flight Computer Mode Display -->
      <div class="mode-display" id="mode-display">
        <span class="mode-badge idle" id="mode-badge">IDLE</span>
        <div class="mode-info">
          <div class="mode-command" id="mode-command">No active command</div>
          <div class="mode-phase" id="mode-phase"></div>
          <div class="mode-status-text" id="mode-status-text"></div>
        </div>
      </div>

      <!-- Progress bar (visible when executing) -->
      <div class="progress-section hidden" id="progress-section">
        <div class="progress-header">
          <span class="progress-label">Progress</span>
          <span class="progress-eta" id="progress-eta">ETA: --</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
        </div>
      </div>

      <!-- Burn plan details (visible when executing) -->
      <div class="burn-details hidden" id="burn-details">
        <div class="burn-item">
          <div class="burn-label">Delta-V</div>
          <div class="burn-value" id="burn-dv">--</div>
        </div>
        <div class="burn-item">
          <div class="burn-label">Fuel Cost</div>
          <div class="burn-value" id="burn-fuel">--</div>
        </div>
        <div class="burn-item">
          <div class="burn-label">Confidence</div>
          <div class="burn-value" id="burn-confidence">--</div>
        </div>
      </div>

      <!-- Quick Commands -->
      <div class="section-title">Commands</div>

      <!-- Coordinate input (shown on Navigate click) -->
      <div class="coord-input-section" id="coord-section">
        <div class="coord-grid">
          <div class="coord-group">
            <label>X (m)</label>
            <input type="number" id="nav-x" value="0" step="100" />
          </div>
          <div class="coord-group">
            <label>Y (m)</label>
            <input type="number" id="nav-y" value="0" step="100" />
          </div>
          <div class="coord-group">
            <label>Z (m)</label>
            <input type="number" id="nav-z" value="0" step="100" />
          </div>
        </div>
        <div class="coord-actions">
          <button class="coord-go-btn" id="nav-go-btn">Navigate</button>
          <button class="coord-cancel-btn" id="nav-cancel-btn">Cancel</button>
        </div>
      </div>

      <!-- Target select for intercept/match_velocity -->
      <div class="target-section" id="target-section">
        <select class="target-select" id="target-select">
          <option value="">-- Select Target --</option>
        </select>
      </div>

      <div class="command-grid">
        <button class="cmd-btn wide" id="cmd-rendezvous" title="Approach and arrive at target with zero velocity (flip-and-burn)">
          <span class="cmd-label">Rendezvous</span>
          <span class="cmd-subtitle">flip & arrive</span>
        </button>
        <button class="cmd-btn" id="cmd-navigate" title="Navigate to coordinates (x, y, z). Uses autopilot course-following.">
          <span class="cmd-label">Navigate</span>
          <span class="cmd-subtitle">go to coords</span>
        </button>
        <button class="cmd-btn" id="cmd-intercept" title="Chase a moving target using lead pursuit. Requires target selected.">
          <span class="cmd-label">Intercept</span>
          <span class="cmd-subtitle">chase target</span>
        </button>
        <button class="cmd-btn" id="cmd-match" title="Match speed and direction with target. Zeroes relative velocity. Requires target selected.">
          <span class="cmd-label">Match Vel</span>
          <span class="cmd-subtitle">zero rel-v</span>
        </button>
        <button class="cmd-btn" id="cmd-hold" title="Station-keep at current position. Fires thrusters to counteract drift. (H)">
          <span class="cmd-label">Hold</span>
          <span class="cmd-subtitle">station-keep</span>
        </button>
        <button class="cmd-btn" id="cmd-orbit" title="Maintain circular orbit around a point. Best for surveillance or patrol.">
          <span class="cmd-label">Orbit</span>
          <span class="cmd-subtitle">circle point</span>
        </button>
        <button class="cmd-btn" id="cmd-evasive" title="Random jinking pattern to avoid incoming fire. Unpredictable thrust changes.">
          <span class="cmd-label">Evasive</span>
          <span class="cmd-subtitle">jink & dodge</span>
        </button>
        <button class="cmd-btn" id="cmd-manual" title="Disengage autopilot. Returns to manual control. (M)">
          <span class="cmd-label">Manual</span>
          <span class="cmd-subtitle">manual ctrl</span>
        </button>
        <button class="cmd-btn danger" id="cmd-abort" title="Abort current autopilot program and return to manual control. (Esc)">
          <span class="cmd-label">Abort</span>
          <span class="cmd-subtitle">disengage AP</span>
        </button>
      </div>
    `;
  }

  _setupInteraction() {
    // Navigate button - toggles coordinate input
    this.shadowRoot.getElementById("cmd-navigate").addEventListener("click", () => {
      this._toggleCoordInput();
    });

    // Navigate go
    this.shadowRoot.getElementById("nav-go-btn").addEventListener("click", () => {
      this._sendNavigate();
    });

    // Navigate cancel
    this.shadowRoot.getElementById("nav-cancel-btn").addEventListener("click", () => {
      this._hideCoordInput();
    });

    // Rendezvous - requires target, show target select
    this.shadowRoot.getElementById("cmd-rendezvous").addEventListener("click", () => {
      this._showTargetSelect("rendezvous");
    });

    // Intercept - show target select then send
    this.shadowRoot.getElementById("cmd-intercept").addEventListener("click", () => {
      this._showTargetSelect("intercept");
    });

    // Match velocity - show target select then send
    this.shadowRoot.getElementById("cmd-match").addEventListener("click", () => {
      this._showTargetSelect("match");
    });

    // Simple autopilot programs (no target required)
    this.shadowRoot.getElementById("cmd-hold").addEventListener("click", () => {
      this._sendAutopilot("hold");
    });

    this.shadowRoot.getElementById("cmd-orbit").addEventListener("click", () => {
      this._sendAutopilot("orbit");
    });

    this.shadowRoot.getElementById("cmd-evasive").addEventListener("click", () => {
      this._sendAutopilot("evasive");
    });

    // Manual and abort both disengage autopilot
    this.shadowRoot.getElementById("cmd-manual").addEventListener("click", () => {
      this._sendAutopilot("off");
    });

    this.shadowRoot.getElementById("cmd-abort").addEventListener("click", () => {
      this._sendAutopilot("off");
    });

    // Target select change - auto-send if a pending action
    this.shadowRoot.getElementById("target-select").addEventListener("change", (e) => {
      if (e.target.value && this._pendingAction) {
        this._sendTargetCommand(this._pendingAction, e.target.value);
        this._hideTargetSelect();
      }
    });

    // Keyboard shortcuts
    this._keyHandler = (e) => {
      const tag = e.target.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if (e.composedPath().some(el => {
        const t = el.tagName?.toLowerCase();
        return t === "input" || t === "textarea" || t === "select";
      })) return;

      switch (e.key.toUpperCase()) {
        case "H":
          e.preventDefault();
          this._sendAutopilot("hold");
          break;
        case "M":
          e.preventDefault();
          this._sendAutopilot("off");
          break;
        case "ESCAPE":
          if (this._showCoordinateInput) {
            this._hideCoordInput();
          } else {
            this._sendAutopilot("off");
          }
          break;
      }
    };
    document.addEventListener("keydown", this._keyHandler);
  }

  _toggleCoordInput() {
    this._showCoordinateInput = !this._showCoordinateInput;
    const section = this.shadowRoot.getElementById("coord-section");
    section.classList.toggle("visible", this._showCoordinateInput);
    this._hideTargetSelect();
  }

  _hideCoordInput() {
    this._showCoordinateInput = false;
    this.shadowRoot.getElementById("coord-section").classList.remove("visible");
  }

  _showTargetSelect(action) {
    this._pendingAction = action;
    this._hideCoordInput();

    // Update target dropdown
    const contacts = stateManager.getContacts();
    const select = this.shadowRoot.getElementById("target-select");
    select.innerHTML = '<option value="">-- Select Target --</option>';
    contacts.forEach(contact => {
      const id = contact.contact_id || contact.id;
      const option = document.createElement("option");
      option.value = id;
      option.textContent = `${id} — ${contact.name || contact.classification || "UNKNOWN"}`;
      select.appendChild(option);
    });

    this.shadowRoot.getElementById("target-section").classList.add("visible");
  }

  _hideTargetSelect() {
    this._pendingAction = null;
    this.shadowRoot.getElementById("target-section").classList.remove("visible");
  }

  /**
   * Send a simple autopilot command (no target needed).
   * Maps to: wsClient.sendShipCommand("autopilot", { program })
   */
  async _sendAutopilot(program) {
    try {
      const args = { program };
      console.log("Flight computer autopilot:", args);
      const response = await wsClient.sendShipCommand("autopilot", args);
      if (response?.error) {
        this._showMessage(`Autopilot error: ${response.error}`, "error");
      } else {
        const label = program === "off" ? "disengaged" : program;
        this._showMessage(`Autopilot: ${label}`, "success");
      }
    } catch (error) {
      this._showMessage(`Command failed: ${error.message}`, "error");
    }
  }

  /**
   * Send navigate command using set_course.
   * Maps to: wsClient.sendShipCommand("set_course", { x, y, z })
   */
  async _sendNavigate() {
    const x = parseFloat(this.shadowRoot.getElementById("nav-x").value) || 0;
    const y = parseFloat(this.shadowRoot.getElementById("nav-y").value) || 0;
    const z = parseFloat(this.shadowRoot.getElementById("nav-z").value) || 0;

    try {
      console.log("Flight computer set_course:", { x, y, z });
      const response = await wsClient.sendShipCommand("set_course", { x, y, z });
      if (response?.error) {
        this._showMessage(`Navigate error: ${response.error}`, "error");
      } else {
        this._showMessage(`Navigating to (${x}, ${y}, ${z})`, "success");
        this._hideCoordInput();
      }
    } catch (error) {
      this._showMessage(`Navigate failed: ${error.message}`, "error");
    }
  }

  /**
   * Send an autopilot command that requires a target (intercept, match, rendezvous).
   * Maps to: wsClient.sendShipCommand("autopilot", { program, target })
   */
  async _sendTargetCommand(action, targetId) {
    try {
      const args = { program: action, target: targetId };
      console.log("Flight computer autopilot (target):", args);
      const response = await wsClient.sendShipCommand("autopilot", args);
      if (response?.error) {
        this._showMessage(`${action} error: ${response.error}`, "error");
      } else {
        this._showMessage(`${action}: ${targetId}`, "success");
      }
    } catch (error) {
      this._showMessage(`${action} failed: ${error.message}`, "error");
    }
  }

  _updateDisplay() {
    const fc = this._fcState;
    const badge = this.shadowRoot.getElementById("mode-badge");
    const command = this.shadowRoot.getElementById("mode-command");
    const phase = this.shadowRoot.getElementById("mode-phase");
    const statusText = this.shadowRoot.getElementById("mode-status-text");
    const progressSection = this.shadowRoot.getElementById("progress-section");
    const burnDetails = this.shadowRoot.getElementById("burn-details");

    if (!fc) {
      badge.className = "mode-badge idle";
      badge.textContent = "IDLE";
      command.textContent = "No active command";
      phase.textContent = "";
      statusText.textContent = "";
      progressSection.classList.add("hidden");
      burnDetails.classList.add("hidden");
      return;
    }

    // Mode badge
    const mode = (fc.mode || "idle").toLowerCase();
    badge.className = `mode-badge ${mode}`;
    badge.textContent = (fc.mode || "IDLE").toUpperCase();

    // Command info
    command.textContent = fc.command || "No active command";
    phase.textContent = fc.phase ? `Phase: ${fc.phase}` : "";
    statusText.textContent = fc.status_text || "";

    // Progress
    if (mode === "executing" && fc.progress !== undefined) {
      progressSection.classList.remove("hidden");
      const progressFill = this.shadowRoot.getElementById("progress-fill");
      const progressEta = this.shadowRoot.getElementById("progress-eta");
      const percent = Math.min(100, Math.max(0, (fc.progress || 0) * 100));
      progressFill.style.width = `${percent}%`;
      progressEta.textContent = fc.eta ? `ETA: ${this._formatTime(fc.eta)}` : "ETA: --";
    } else {
      progressSection.classList.add("hidden");
    }

    // Burn plan details
    if (fc.burn_plan || fc.delta_v !== undefined) {
      burnDetails.classList.remove("hidden");
      const plan = fc.burn_plan || fc;
      this.shadowRoot.getElementById("burn-dv").textContent =
        plan.delta_v !== undefined ? `${plan.delta_v.toFixed(1)} m/s` : "--";
      this.shadowRoot.getElementById("burn-fuel").textContent =
        plan.fuel_cost !== undefined ? `${plan.fuel_cost.toFixed(1)} kg` : "--";
      this.shadowRoot.getElementById("burn-confidence").textContent =
        plan.confidence !== undefined ? `${(plan.confidence * 100).toFixed(0)}%` : "--";
    } else {
      burnDetails.classList.add("hidden");
    }
  }

  _formatTime(seconds) {
    if (seconds === null || seconds === undefined || !isFinite(seconds)) return "--";
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("flight-computer-panel", FlightComputerPanel);
export { FlightComputerPanel };
