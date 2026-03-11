/**
 * Flight Computer Panel — Unified Command Panel
 * Combines autopilot mode selection, coordinate navigation, inline status,
 * and course options into a single command interface.
 *
 * Command mapping:
 *   Navigate  -> sendShipCommand("set_course", {x, y, z, stop, tolerance, max_thrust})
 *   Rendezvous, Intercept, Match Vel -> sendShipCommand("autopilot", {program, target})
 *   Hold, Cruise, Orbit, Evasive     -> sendShipCommand("autopilot", {program})
 *   Manual / Abort                    -> sendShipCommand("autopilot", {program: "off"})
 *
 * Tier awareness:
 *   ARCADE:     full command grid
 *   CPU-ASSIST: hides Match Vel, Orbit, Evasive (too granular)
 *   RAW:        hidden by tiers.css; shows collapsed disabled-reason if forced visible
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import {
  PHASE_SEGMENT_CSS,
  buildPhaseProgressHtml,
  extractAutopilotState,
  formatDistance,
  formatEta,
} from "../js/autopilot-utils.js";

// Modes hidden in CPU-ASSIST tier (too granular for order-based play)
const GRANULAR_CMD_IDS = ["cmd-match", "cmd-orbit", "cmd-evasive"];

class FlightComputerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._fcState = null;
    this._showCoordinateInput = false;
    this._showAdvanced = false;
    this._pendingAction = null;
    this._keyHandler = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();
    this._applyTier();
    // Listen for tier changes
    this._tierHandler = () => this._applyTier();
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) { this._unsubscribe(); this._unsubscribe = null; }
    if (this._keyHandler) { document.removeEventListener("keydown", this._keyHandler); this._keyHandler = null; }
    if (this._tierHandler) { document.removeEventListener("tier-change", this._tierHandler); this._tierHandler = null; }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._fcState = extractAutopilotState();
      this._updateDisplay();
    });
  }

  /** Hide granular commands in CPU-ASSIST tier */
  _applyTier() {
    const tier = window.controlTier || "arcade";
    const isCpuAssist = tier === "cpu-assist";
    GRANULAR_CMD_IDS.forEach(id => {
      const btn = this.shadowRoot.getElementById(id);
      if (btn) btn.classList.toggle("hidden", isCpuAssist);
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 16px; font-family: var(--font-sans, "Inter", sans-serif); }

        /* --- Inline autopilot status --- */
        .inline-status { margin-bottom: 12px; padding: 10px; background: var(--bg-input, #1a1a24); border-radius: 8px; border: 1px solid var(--border-default, #2a2a3a); }
        .inline-status.hidden { display: none !important; }
        .status-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .mode-badge { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.75rem; font-weight: 700; letter-spacing: 1px; padding: 2px 8px; border-radius: 4px; }
        .mode-badge.idle { color: var(--text-dim, #555566); background: rgba(85,85,102,0.15); }
        .mode-badge.executing { color: var(--status-nominal, #00ff88); background: rgba(0,255,136,0.1); animation: pulse-glow 2s ease-in-out infinite; }
        @keyframes pulse-glow { 0%,100%{box-shadow:0 0 4px rgba(0,255,136,0.2)} 50%{box-shadow:0 0 12px rgba(0,255,136,0.4)} }
        .status-command { font-size: 0.8rem; font-weight: 600; color: var(--text-primary, #e0e0e0); }
        .status-target { font-size: 0.7rem; color: var(--text-dim, #555566); margin-left: auto; }
        .status-text-line { font-size: 0.7rem; color: var(--text-secondary, #888899); font-style: italic; margin-bottom: 4px; }
        .status-text-line:empty { display: none; }

        /* Phase bar (from autopilot-utils) */
        .phase-progress { margin-bottom: 6px; }
        ${PHASE_SEGMENT_CSS}

        /* Compact info row: distance | closing | ETA */
        .info-row { display: flex; gap: 12px; font-size: 0.7rem; }
        .info-row .info-item { display: flex; gap: 4px; align-items: baseline; }
        .info-row .info-lbl { color: var(--text-dim, #555566); text-transform: uppercase; font-size: 0.6rem; }
        .info-row .info-val { font-family: var(--font-mono, "JetBrains Mono", monospace); color: var(--text-primary, #e0e0e0); }

        /* --- Disengage bar --- */
        .disengage-bar { display: none; margin-bottom: 12px; }
        .disengage-bar.visible { display: block; }
        .disengage-btn { width: 100%; padding: 10px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; background: transparent; border: 1px solid var(--status-warning, #ffaa00); color: var(--status-warning, #ffaa00); font-family: var(--font-sans, "Inter", sans-serif); }
        .disengage-btn:hover { background: rgba(255,170,0,0.1); }

        /* --- Command grid --- */
        .section-title { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary, #888899); margin-bottom: 8px; }
        .command-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 12px; }
        .cmd-btn { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; padding: 10px 6px; background: var(--bg-input, #1a1a24); border: 1px solid var(--border-default, #2a2a3a); border-radius: 6px; color: var(--text-secondary, #888899); font-family: var(--font-sans, "Inter", sans-serif); font-size: 0.65rem; font-weight: 600; text-transform: uppercase; cursor: pointer; transition: all 0.1s ease; min-height: 44px; letter-spacing: 0.3px; }
        .cmd-label { font-size: 0.7rem; font-weight: 600; }
        .cmd-subtitle { font-size: 0.55rem; font-weight: 400; opacity: 0.6; letter-spacing: 0.3px; text-transform: lowercase; }
        .cmd-btn:hover:not(:disabled) { background: var(--bg-hover, #22222e); border-color: var(--status-info, #00aaff); color: var(--text-primary, #e0e0e0); }
        .cmd-btn:active:not(:disabled) { transform: scale(0.96); }
        .cmd-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .cmd-btn.active { background: var(--status-info, #00aaff); border-color: var(--status-info, #00aaff); color: var(--bg-primary, #0a0a0f); }
        .cmd-btn.danger { border-color: var(--status-critical, #ff4444); color: var(--status-critical, #ff4444); }
        .cmd-btn.danger:hover:not(:disabled) { background: rgba(255,68,68,0.15); border-color: var(--status-critical, #ff4444); }
        .cmd-btn.wide { grid-column: span 2; }
        .cmd-btn.hidden { display: none !important; }

        /* --- Coordinate input + advanced options --- */
        .coord-input-section { display: none; padding: 12px; background: var(--bg-input, #1a1a24); border: 1px solid var(--border-default, #2a2a3a); border-radius: 8px; margin-bottom: 12px; }
        .coord-input-section.visible { display: block; }
        .coord-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px; }
        .coord-group { display: flex; flex-direction: column; gap: 4px; }
        .coord-group label { font-size: 0.65rem; color: var(--text-dim, #555566); text-transform: uppercase; text-align: center; }
        .coord-group input { padding: 8px; background: var(--bg-primary, #0a0a0f); border: 1px solid var(--border-default, #2a2a3a); border-radius: 4px; color: var(--text-primary, #e0e0e0); font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.8rem; text-align: center; min-height: 36px; }
        .coord-group input:focus { outline: none; border-color: var(--status-info, #00aaff); }

        /* Advanced course options */
        .advanced-toggle { font-size: 0.65rem; color: var(--text-dim, #555566); cursor: pointer; margin-bottom: 8px; user-select: none; }
        .advanced-toggle:hover { color: var(--text-secondary, #888899); }
        .advanced-opts { display: none; margin-bottom: 10px; padding: 8px; background: var(--bg-primary, #0a0a0f); border-radius: 6px; }
        .advanced-opts.visible { display: block; }
        .opt-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .opt-row:last-child { margin-bottom: 0; }
        .opt-label { font-size: 0.65rem; color: var(--text-secondary, #888899); min-width: 70px; }
        .opt-input { width: 60px; padding: 4px 6px; background: var(--bg-input, #1a1a24); border: 1px solid var(--border-default, #2a2a3a); border-radius: 4px; color: var(--text-primary, #e0e0e0); font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.75rem; text-align: center; }
        .opt-checkbox { width: 16px; height: 16px; accent-color: var(--status-info, #00aaff); }
        .opt-slider { flex: 1; accent-color: var(--status-info, #00aaff); }
        .opt-val { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.7rem; color: var(--text-primary, #e0e0e0); min-width: 30px; text-align: right; }

        .coord-actions { display: flex; gap: 8px; }
        .coord-actions button { flex: 1; padding: 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; cursor: pointer; min-height: 36px; font-family: var(--font-sans, "Inter", sans-serif); }
        .coord-go-btn { background: var(--status-nominal, #00ff88); border: none; color: var(--bg-primary, #0a0a0f); }
        .coord-cancel-btn { background: transparent; border: 1px solid var(--border-default, #2a2a3a); color: var(--text-secondary, #888899); }

        /* --- Target select --- */
        .target-section { display: none; margin-bottom: 12px; }
        .target-section.visible { display: block; }
        .target-select { width: 100%; padding: 8px 12px; background: var(--bg-input, #1a1a24); border: 1px solid var(--border-default, #2a2a3a); border-radius: 6px; color: var(--text-primary, #e0e0e0); font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.8rem; min-height: 36px; }
        .target-select:focus { outline: none; border-color: var(--status-info, #00aaff); }

        .hidden { display: none !important; }

        @media (max-width: 768px) {
          .command-grid { grid-template-columns: repeat(3, 1fr); }
        }
      </style>

      <!-- Inline autopilot status (compact, from autopilot-status data) -->
      <div class="inline-status hidden" id="inline-status">
        <div class="status-header">
          <span class="mode-badge executing" id="mode-badge">AUTOPILOT</span>
          <span class="status-command" id="status-command">--</span>
          <span class="status-target" id="status-target"></span>
        </div>
        <div class="status-text-line" id="status-text"></div>
        <div class="phase-progress" id="phase-progress">
          <div class="phase-bar" id="phase-bar"></div>
          <div class="phase-labels" id="phase-labels"></div>
        </div>
        <div class="info-row">
          <div class="info-item"><span class="info-lbl">Dist</span><span class="info-val" id="info-dist">--</span></div>
          <div class="info-item"><span class="info-lbl">Close</span><span class="info-val" id="info-close">--</span></div>
          <div class="info-item"><span class="info-lbl">ETA</span><span class="info-val" id="info-eta">--</span></div>
        </div>
      </div>

      <!-- Disengage bar (visible when autopilot active) -->
      <div class="disengage-bar" id="disengage-bar">
        <button class="disengage-btn" id="disengage-btn" title="Disengage autopilot and return to manual control (Esc)">DISENGAGE AUTOPILOT</button>
      </div>

      <!-- Quick Commands -->
      <div class="section-title">Commands</div>

      <!-- Coordinate input (shown on Navigate click) -->
      <div class="coord-input-section" id="coord-section">
        <div class="coord-grid">
          <div class="coord-group"><label>X (m)</label><input type="number" id="nav-x" value="0" step="100" /></div>
          <div class="coord-group"><label>Y (m)</label><input type="number" id="nav-y" value="0" step="100" /></div>
          <div class="coord-group"><label>Z (m)</label><input type="number" id="nav-z" value="0" step="100" /></div>
        </div>
        <div class="advanced-toggle" id="adv-toggle">+ Advanced options</div>
        <div class="advanced-opts" id="adv-opts">
          <div class="opt-row">
            <span class="opt-label">Tolerance</span>
            <input type="number" class="opt-input" id="opt-tolerance" value="100" min="1" step="10" />
            <span class="opt-label" style="min-width:auto">m</span>
          </div>
          <div class="opt-row">
            <span class="opt-label">Max thrust</span>
            <input type="range" class="opt-slider" id="opt-thrust" min="0" max="100" value="100" />
            <span class="opt-val" id="opt-thrust-val">100%</span>
          </div>
          <div class="opt-row">
            <input type="checkbox" class="opt-checkbox" id="opt-stop" checked />
            <span class="opt-label" style="min-width:auto">Stop at target</span>
          </div>
        </div>
        <div class="coord-actions">
          <button class="coord-go-btn" id="nav-go-btn">Navigate</button>
          <button class="coord-cancel-btn" id="nav-cancel-btn">Cancel</button>
        </div>
      </div>

      <!-- Target select for intercept/match_velocity/rendezvous -->
      <div class="target-section" id="target-section">
        <select class="target-select" id="target-select">
          <option value="">-- Select Target --</option>
        </select>
      </div>

      <div class="command-grid" id="command-grid">
        <button class="cmd-btn wide" id="cmd-rendezvous" title="Approach and arrive at target with zero velocity (flip-and-burn). Requires target.">
          <span class="cmd-label">Rendezvous</span><span class="cmd-subtitle">flip & arrive</span>
        </button>
        <button class="cmd-btn" id="cmd-navigate" title="Navigate to coordinates (x, y, z). Uses autopilot course-following.">
          <span class="cmd-label">Navigate</span><span class="cmd-subtitle">go to coords</span>
        </button>
        <button class="cmd-btn" id="cmd-intercept" title="Chase a moving target using lead pursuit. Requires target selected.">
          <span class="cmd-label">Intercept</span><span class="cmd-subtitle">chase target</span>
        </button>
        <button class="cmd-btn" id="cmd-match" title="Match speed and direction with target. Zeroes relative velocity. Requires target.">
          <span class="cmd-label">Match Vel</span><span class="cmd-subtitle">zero rel-v</span>
        </button>
        <button class="cmd-btn" id="cmd-hold" title="Station-keep at current position. Fires thrusters to counteract drift. (H)">
          <span class="cmd-label">Hold</span><span class="cmd-subtitle">station-keep</span>
        </button>
        <button class="cmd-btn" id="cmd-orbit" title="Maintain circular orbit around a point. Best for surveillance or patrol.">
          <span class="cmd-label">Orbit</span><span class="cmd-subtitle">circle point</span>
        </button>
        <button class="cmd-btn" id="cmd-evasive" title="Random jinking pattern to avoid incoming fire. Unpredictable thrust changes.">
          <span class="cmd-label">Evasive</span><span class="cmd-subtitle">jink & dodge</span>
        </button>
        <button class="cmd-btn danger" id="cmd-abort" title="Abort current autopilot program and return to manual control. (Esc)">
          <span class="cmd-label">Abort</span><span class="cmd-subtitle">disengage AP</span>
        </button>
      </div>
    `;
  }

  _setupInteraction() {
    const $ = (id) => this.shadowRoot.getElementById(id);

    // Navigate button - toggles coordinate input
    $("cmd-navigate").addEventListener("click", () => this._toggleCoordInput());
    $("nav-go-btn").addEventListener("click", () => this._sendNavigate());
    $("nav-cancel-btn").addEventListener("click", () => this._hideCoordInput());

    // Advanced options toggle
    $("adv-toggle").addEventListener("click", () => {
      this._showAdvanced = !this._showAdvanced;
      $("adv-opts").classList.toggle("visible", this._showAdvanced);
      $("adv-toggle").textContent = this._showAdvanced ? "- Advanced options" : "+ Advanced options";
    });

    // Max thrust slider label
    $("opt-thrust").addEventListener("input", (e) => {
      $("opt-thrust-val").textContent = `${e.target.value}%`;
    });

    // Target-requiring commands
    $("cmd-rendezvous").addEventListener("click", () => this._showTargetSelect("rendezvous"));
    $("cmd-intercept").addEventListener("click", () => this._showTargetSelect("intercept"));
    $("cmd-match").addEventListener("click", () => this._showTargetSelect("match"));

    // Simple autopilot programs
    $("cmd-hold").addEventListener("click", () => this._sendAutopilot("hold"));
    $("cmd-orbit").addEventListener("click", () => this._sendAutopilot("orbit"));
    $("cmd-evasive").addEventListener("click", () => this._sendAutopilot("evasive"));

    // Abort / disengage
    $("cmd-abort").addEventListener("click", () => this._sendAutopilot("off"));
    $("disengage-btn").addEventListener("click", () => this._sendAutopilot("off"));

    // Target select change - auto-send if pending action
    $("target-select").addEventListener("change", (e) => {
      if (e.target.value && this._pendingAction) {
        this._sendTargetCommand(this._pendingAction, e.target.value);
        this._hideTargetSelect();
      }
    });

    // Keyboard shortcuts
    this._keyHandler = (e) => {
      // Skip if focus is in an input field
      if (e.composedPath().some(el => {
        const t = el.tagName?.toLowerCase();
        return t === "input" || t === "textarea" || t === "select";
      })) return;

      switch (e.key.toUpperCase()) {
        case "H": e.preventDefault(); this._sendAutopilot("hold"); break;
        case "M": e.preventDefault(); this._sendAutopilot("off"); break;
        case "ESCAPE":
          if (this._showCoordinateInput) this._hideCoordInput();
          else this._sendAutopilot("off");
          break;
      }
    };
    document.addEventListener("keydown", this._keyHandler);
  }

  // --- UI toggles ---

  _toggleCoordInput() {
    this._showCoordinateInput = !this._showCoordinateInput;
    this.shadowRoot.getElementById("coord-section").classList.toggle("visible", this._showCoordinateInput);
    this._hideTargetSelect();
  }

  _hideCoordInput() {
    this._showCoordinateInput = false;
    this.shadowRoot.getElementById("coord-section").classList.remove("visible");
  }

  _showTargetSelect(action) {
    this._pendingAction = action;
    this._hideCoordInput();
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

  // --- Commands ---

  async _sendAutopilot(program) {
    try {
      const response = await wsClient.sendShipCommand("autopilot", { program });
      if (response?.error) {
        this._showMessage(`Autopilot error: ${response.error}`, "error");
      } else {
        this._showMessage(`Autopilot: ${program === "off" ? "disengaged" : program}`, "success");
      }
    } catch (error) {
      this._showMessage(`Command failed: ${error.message}`, "error");
    }
  }

  async _sendNavigate() {
    const $ = (id) => this.shadowRoot.getElementById(id);
    const x = parseFloat($("nav-x").value) || 0;
    const y = parseFloat($("nav-y").value) || 0;
    const z = parseFloat($("nav-z").value) || 0;
    const tolerance = parseFloat($("opt-tolerance").value) || 100;
    const max_thrust = (parseFloat($("opt-thrust").value) || 100) / 100;
    const stop = $("opt-stop").checked;

    try {
      const response = await wsClient.sendShipCommand("set_course", { x, y, z, tolerance, max_thrust, stop });
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

  async _sendTargetCommand(action, targetId) {
    try {
      const response = await wsClient.sendShipCommand("autopilot", { program: action, target: targetId });
      if (response?.error) {
        this._showMessage(`${action} error: ${response.error}`, "error");
      } else {
        this._showMessage(`${action}: ${targetId}`, "success");
      }
    } catch (error) {
      this._showMessage(`${action} failed: ${error.message}`, "error");
    }
  }

  // --- Display update ---

  _updateDisplay() {
    const fc = this._fcState;
    const inlineStatus = this.shadowRoot.getElementById("inline-status");
    const disengageBar = this.shadowRoot.getElementById("disengage-bar");

    if (!fc) {
      inlineStatus.classList.add("hidden");
      disengageBar.classList.remove("visible");
      this._clearActiveButtons();
      return;
    }

    // Show inline status section
    inlineStatus.classList.remove("hidden");
    disengageBar.classList.add("visible");

    // Header: badge, command, target
    const programLabel = (fc.program || "").toUpperCase().replace(/_/g, " ");
    this.shadowRoot.getElementById("status-command").textContent = programLabel || "AUTOPILOT";
    this.shadowRoot.getElementById("status-target").textContent = fc.target ? `-> ${fc.target}` : "";
    this.shadowRoot.getElementById("status-text").textContent = fc.statusText || "";

    // Phase progress bar
    const { segmentsHtml, labelsHtml } = buildPhaseProgressHtml(fc.program, fc.phase);
    this.shadowRoot.getElementById("phase-bar").innerHTML = segmentsHtml;
    this.shadowRoot.getElementById("phase-labels").innerHTML = labelsHtml;

    // Compact info row
    this.shadowRoot.getElementById("info-dist").textContent = formatDistance(fc.range);
    this.shadowRoot.getElementById("info-close").textContent =
      fc.closingSpeed != null ? `${fc.closingSpeed.toFixed(1)} m/s` : "--";
    this.shadowRoot.getElementById("info-eta").textContent = formatEta(fc.eta);

    // Highlight the active command button
    this._highlightActiveButton(fc.program);
  }

  _highlightActiveButton(program) {
    // Map program names to button IDs
    const programToBtnId = {
      rendezvous: "cmd-rendezvous",
      intercept: "cmd-intercept",
      match: "cmd-match",
      hold: "cmd-hold",
      orbit: "cmd-orbit",
      evasive: "cmd-evasive",
      goto_position: "cmd-navigate",
      set_course: "cmd-navigate",
    };
    const activeId = programToBtnId[program?.toLowerCase()] || null;
    this.shadowRoot.querySelectorAll(".cmd-btn").forEach(btn => {
      btn.classList.toggle("active", btn.id === activeId);
    });
  }

  _clearActiveButtons() {
    this.shadowRoot.querySelectorAll(".cmd-btn.active").forEach(btn => btn.classList.remove("active"));
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) systemMessages.show({ type, text });
  }
}

customElements.define("flight-computer-panel", FlightComputerPanel);
export { FlightComputerPanel };
