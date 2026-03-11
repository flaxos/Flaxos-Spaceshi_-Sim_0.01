/**
 * Flight Computer Panel — Unified Command Panel
 * Combines autopilot mode selection, coordinate navigation, inline status,
 * nav solution profiles, and course options into a single command interface.
 *
 * Command mapping:
 *   Navigate  -> sendShipCommand("set_course", {x, y, z, stop, tolerance, max_thrust, profile})
 *   Rendezvous, Intercept, Match Vel -> sendShipCommand("autopilot", {program, target, profile})
 *   Hold, Cruise, Orbit, Evasive     -> sendShipCommand("autopilot", {program})
 *   Manual / Abort                    -> sendShipCommand("autopilot", {program: "off"})
 *
 * Nav solutions:
 *   get_nav_solutions returns 3 profiles (aggressive/balanced/conservative) with
 *   ETA, fuel cost, accuracy, and risk. Cards are shown when a target is selected
 *   or coordinates are entered. Auto-polls every 5s while visible.
 *
 * Tier awareness:
 *   ARCADE:     full command grid + nav solution cards
 *   CPU-ASSIST: hides Match Vel, Orbit, Evasive (too granular) + shows nav solution cards
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

// Profile color/label config for nav solution cards
const PROFILE_CONFIG = {
  aggressive:   { label: "Aggressive",   accent: "#ff6644", riskColor: "#ff4444", riskLabel: "HIGH" },
  balanced:     { label: "Balanced",     accent: "#4488ff", riskColor: "#ffaa00", riskLabel: "MEDIUM" },
  conservative: { label: "Conservative", accent: "#00cc66", riskColor: "#00cc66", riskLabel: "LOW" },
};

// Programs that support nav solution profiles
const PROFILE_PROGRAMS = ["rendezvous", "intercept", "match"];

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

    // Nav solutions state
    this._selectedProfile = "balanced";
    this._navSolutions = null;       // last response from get_nav_solutions
    this._navSolPollInterval = null;  // 5s refresh timer
    this._lastSolTarget = null;       // target_id used for last fetch
    this._lastSolCoords = null;       // {x,y,z} used for last fetch
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
    this._stopNavSolPolling();
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._fcState = extractAutopilotState();
      this._updateDisplay();
    });
  }

  /** Hide granular commands in CPU-ASSIST tier; hide nav solutions in RAW tier */
  _applyTier() {
    const tier = window.controlTier || "arcade";
    const isCpuAssist = tier === "cpu-assist";
    const isRaw = tier === "raw";
    GRANULAR_CMD_IDS.forEach(id => {
      const btn = this.shadowRoot.getElementById(id);
      if (btn) btn.classList.toggle("hidden", isCpuAssist);
    });
    // Nav solutions: hidden in RAW (manual only, no computer help)
    const navSolSection = this.shadowRoot.getElementById("nav-solutions");
    if (navSolSection) navSolSection.classList.toggle("tier-hidden", isRaw);
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
        .tier-hidden { display: none !important; }

        /* --- Nav Solutions Cards --- */
        .nav-solutions { display: none; margin-bottom: 12px; }
        .nav-solutions.visible { display: block; }
        .nav-solutions.tier-hidden { display: none !important; }
        .nav-sol-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
        .nav-sol-title { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary, #888899); }
        .nav-sol-meta { font-size: 0.6rem; color: var(--text-dim, #555566); font-family: var(--font-mono, "JetBrains Mono", monospace); }
        .nav-sol-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
        .nav-sol-card {
          padding: 10px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s ease;
          position: relative;
        }
        .nav-sol-card:hover { background: var(--bg-hover, #22222e); }
        .nav-sol-card.selected { border-width: 2px; }
        .nav-sol-card.selected::after {
          content: "SELECTED";
          position: absolute;
          top: 4px;
          right: 6px;
          font-size: 0.5rem;
          font-weight: 700;
          letter-spacing: 0.5px;
          opacity: 0.8;
        }
        .nav-sol-card.aggressive { border-color: #ff6644; }
        .nav-sol-card.aggressive.selected { background: rgba(255, 102, 68, 0.08); }
        .nav-sol-card.aggressive.selected::after { color: #ff6644; }
        .nav-sol-card.balanced { border-color: #4488ff; }
        .nav-sol-card.balanced.selected { background: rgba(68, 136, 255, 0.08); }
        .nav-sol-card.balanced.selected::after { color: #4488ff; }
        .nav-sol-card.conservative { border-color: #00cc66; }
        .nav-sol-card.conservative.selected { background: rgba(0, 204, 102, 0.08); }
        .nav-sol-card.conservative.selected::after { color: #00cc66; }

        .sol-profile-name { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 6px; }
        .nav-sol-card.aggressive .sol-profile-name { color: #ff6644; }
        .nav-sol-card.balanced .sol-profile-name { color: #4488ff; }
        .nav-sol-card.conservative .sol-profile-name { color: #00cc66; }

        .sol-stat { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
        .sol-stat-lbl { font-size: 0.6rem; color: var(--text-dim, #555566); text-transform: uppercase; }
        .sol-stat-val { font-size: 0.7rem; font-family: var(--font-mono, "JetBrains Mono", monospace); color: var(--text-primary, #e0e0e0); }

        /* Fuel bar */
        .sol-fuel-bar { height: 4px; background: var(--bg-primary, #0a0a0f); border-radius: 2px; margin-top: 2px; margin-bottom: 4px; overflow: hidden; }
        .sol-fuel-fill { height: 100%; border-radius: 2px; transition: width 0.3s ease; }
        .nav-sol-card.aggressive .sol-fuel-fill { background: #ff6644; }
        .nav-sol-card.balanced .sol-fuel-fill { background: #4488ff; }
        .nav-sol-card.conservative .sol-fuel-fill { background: #00cc66; }

        /* Risk badge */
        .sol-risk-badge { display: inline-block; font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px; padding: 1px 6px; border-radius: 3px; }
        .sol-risk-badge.high { color: #ff4444; background: rgba(255, 68, 68, 0.15); }
        .sol-risk-badge.medium { color: #ffaa00; background: rgba(255, 170, 0, 0.15); }
        .sol-risk-badge.low { color: #00cc66; background: rgba(0, 204, 102, 0.15); }

        .nav-sol-desc { font-size: 0.55rem; color: var(--text-dim, #555566); font-style: italic; margin-top: 4px; line-height: 1.3; }

        .nav-sol-loading { text-align: center; padding: 16px; font-size: 0.7rem; color: var(--text-dim, #555566); font-style: italic; }
        .nav-sol-error { text-align: center; padding: 8px; font-size: 0.7rem; color: var(--status-critical, #ff4444); }

        /* Active profile indicator in inline status */
        .active-profile-badge { font-size: 0.65rem; font-weight: 600; padding: 1px 6px; border-radius: 3px; margin-left: 6px; }
        .active-profile-badge.aggressive { color: #ff6644; background: rgba(255, 102, 68, 0.15); }
        .active-profile-badge.balanced { color: #4488ff; background: rgba(68, 136, 255, 0.15); }
        .active-profile-badge.conservative { color: #00cc66; background: rgba(0, 204, 102, 0.15); }

        @media (max-width: 768px) {
          .command-grid { grid-template-columns: repeat(3, 1fr); }
          .nav-sol-grid { grid-template-columns: 1fr; }
        }
      </style>

      <!-- Inline autopilot status (compact, from autopilot-status data) -->
      <div class="inline-status hidden" id="inline-status">
        <div class="status-header">
          <span class="mode-badge executing" id="mode-badge">AUTOPILOT</span>
          <span class="status-command" id="status-command">--</span>
          <span class="active-profile-badge hidden" id="active-profile-badge"></span>
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

      <!-- Nav Solutions (shown when target selected or coords entered) -->
      <div class="nav-solutions" id="nav-solutions">
        <div class="nav-sol-header">
          <span class="nav-sol-title">Nav Solutions</span>
          <span class="nav-sol-meta" id="nav-sol-meta"></span>
        </div>
        <div id="nav-sol-content">
          <div class="nav-sol-grid" id="nav-sol-grid"></div>
        </div>
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

    // Navigate button - toggles coordinate input and fetches solutions for coords
    $("cmd-navigate").addEventListener("click", () => this._toggleCoordInput());
    $("nav-go-btn").addEventListener("click", () => this._sendNavigate());
    $("nav-cancel-btn").addEventListener("click", () => { this._hideCoordInput(); this._hideNavSolutions(); });

    // Fetch nav solutions when coordinate inputs change (debounced)
    let coordDebounce = null;
    const coordInputHandler = () => {
      clearTimeout(coordDebounce);
      coordDebounce = setTimeout(() => {
        if (!this._showCoordinateInput) return;
        const x = parseFloat($("nav-x").value) || 0;
        const y = parseFloat($("nav-y").value) || 0;
        const z = parseFloat($("nav-z").value) || 0;
        // Only fetch if at least one coord is non-zero
        if (x !== 0 || y !== 0 || z !== 0) {
          this._fetchNavSolutions({ target_position: { x, y, z } });
          this._showNavSolutions();
        }
      }, 800);
    };
    $("nav-x").addEventListener("input", coordInputHandler);
    $("nav-y").addEventListener("input", coordInputHandler);
    $("nav-z").addEventListener("input", coordInputHandler);

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

    // Target select change — fetch nav solutions, then wait for user to confirm
    $("target-select").addEventListener("change", (e) => {
      if (e.target.value && this._pendingAction) {
        // For profile-supporting programs, fetch solutions before sending
        if (PROFILE_PROGRAMS.includes(this._pendingAction)) {
          this._fetchNavSolutions({ target_id: e.target.value });
          this._showNavSolutions();
          // Don't auto-send yet — user picks a profile card then confirms via card click
        } else {
          this._sendTargetCommand(this._pendingAction, e.target.value);
          this._hideTargetSelect();
        }
      }
    });

    // Nav solution card clicks (delegated)
    $("nav-sol-grid").addEventListener("click", (e) => {
      const card = e.target.closest(".nav-sol-card");
      if (!card) return;
      const profile = card.dataset.profile;
      if (!profile) return;
      this._selectedProfile = profile;
      this._renderNavSolCards();
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
    this._hideNavSolutions();
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
    const profile = this._selectedProfile || "balanced";

    try {
      const response = await wsClient.sendShipCommand("set_course", { x, y, z, tolerance, max_thrust, stop, profile });
      if (response?.error) {
        this._showMessage(`Navigate error: ${response.error}`, "error");
      } else {
        this._showMessage(`Navigating to (${x}, ${y}, ${z}) [${profile}]`, "success");
        this._hideCoordInput();
        this._hideNavSolutions();
      }
    } catch (error) {
      this._showMessage(`Navigate failed: ${error.message}`, "error");
    }
  }

  async _sendTargetCommand(action, targetId) {
    const profile = PROFILE_PROGRAMS.includes(action) ? (this._selectedProfile || "balanced") : undefined;
    try {
      const params = { program: action, target: targetId };
      if (profile) params.profile = profile;
      const response = await wsClient.sendShipCommand("autopilot", params);
      if (response?.error) {
        this._showMessage(`${action} error: ${response.error}`, "error");
      } else {
        const profileNote = profile ? ` [${profile}]` : "";
        this._showMessage(`${action}: ${targetId}${profileNote}`, "success");
        this._hideNavSolutions();
      }
    } catch (error) {
      this._showMessage(`${action} failed: ${error.message}`, "error");
    }
  }

  // --- Nav Solutions ---

  /** Show the nav solutions section */
  _showNavSolutions() {
    const section = this.shadowRoot.getElementById("nav-solutions");
    if (section) section.classList.add("visible");
  }

  /** Hide the nav solutions section and stop polling */
  _hideNavSolutions() {
    const section = this.shadowRoot.getElementById("nav-solutions");
    if (section) section.classList.remove("visible");
    this._stopNavSolPolling();
    this._navSolutions = null;
    this._lastSolTarget = null;
    this._lastSolCoords = null;
  }

  /** Fetch nav solutions from the server and start auto-refresh polling */
  async _fetchNavSolutions(params) {
    // Save the query params so we can re-poll
    if (params.target_id) {
      this._lastSolTarget = params.target_id;
      this._lastSolCoords = null;
    } else if (params.target_position) {
      this._lastSolCoords = params.target_position;
      this._lastSolTarget = null;
    }

    // Show loading on first fetch
    const content = this.shadowRoot.getElementById("nav-sol-content");
    if (!this._navSolutions) {
      content.innerHTML = '<div class="nav-sol-loading">Computing solutions...</div>';
    }

    try {
      const raw = await wsClient.sendShipCommand("get_nav_solutions", params);
      // Station dispatcher wraps in {ok, message, response: {solutions, range, ...}}
      const resp = raw?.response || raw;
      if (resp?.error || raw?.error) {
        content.innerHTML = `<div class="nav-sol-error">${resp?.error || raw?.error}</div>`;
        this._navSolutions = null;
        return;
      }
      this._navSolutions = resp;
      // Restore the grid container (loading may have replaced it)
      content.innerHTML = '<div class="nav-sol-grid" id="nav-sol-grid"></div>';
      // Re-attach click delegation on the new grid element
      this.shadowRoot.getElementById("nav-sol-grid").addEventListener("click", (e) => {
        const card = e.target.closest(".nav-sol-card");
        if (!card) return;
        const profile = card.dataset.profile;
        if (profile) {
          this._selectedProfile = profile;
          this._renderNavSolCards();
        }
      });
      this._renderNavSolCards();
      this._updateNavSolMeta();
    } catch (err) {
      content.innerHTML = `<div class="nav-sol-error">Failed: ${err.message}</div>`;
      this._navSolutions = null;
    }

    // Start 5-second refresh polling if not already running
    this._startNavSolPolling();
  }

  /** Re-poll solutions using the last known target/coords */
  _repollNavSolutions() {
    if (this._lastSolTarget) {
      this._fetchNavSolutions({ target_id: this._lastSolTarget });
    } else if (this._lastSolCoords) {
      this._fetchNavSolutions({ target_position: this._lastSolCoords });
    }
  }

  _startNavSolPolling() {
    if (this._navSolPollInterval) return;
    this._navSolPollInterval = setInterval(() => this._repollNavSolutions(), 5000);
  }

  _stopNavSolPolling() {
    if (this._navSolPollInterval) {
      clearInterval(this._navSolPollInterval);
      this._navSolPollInterval = null;
    }
  }

  /** Update the meta text (range + closing speed from last response) */
  _updateNavSolMeta() {
    const meta = this.shadowRoot.getElementById("nav-sol-meta");
    if (!meta || !this._navSolutions) return;
    const range = this._navSolutions.range;
    const closing = this._navSolutions.closing_speed;
    const parts = [];
    if (range != null) parts.push(`Range: ${formatDistance(range)}`);
    if (closing != null) parts.push(`Close: ${closing.toFixed(1)} m/s`);
    meta.textContent = parts.join(" | ");
  }

  /** Render the 3 solution cards into the grid */
  _renderNavSolCards() {
    const grid = this.shadowRoot.getElementById("nav-sol-grid");
    if (!grid || !this._navSolutions?.solutions) return;

    const solutions = this._navSolutions.solutions;
    grid.innerHTML = "";

    for (const key of ["aggressive", "balanced", "conservative"]) {
      const sol = solutions[key];
      if (!sol) continue;
      const cfg = PROFILE_CONFIG[key];
      const isSelected = this._selectedProfile === key;
      const riskClass = (sol.risk_level || cfg.riskLabel).toLowerCase();

      const card = document.createElement("div");
      card.className = `nav-sol-card ${key}${isSelected ? " selected" : ""}`;
      card.dataset.profile = key;
      card.title = sol.description || `${cfg.label} approach profile`;

      const fuelPct = Math.min(100, Math.round((sol.fuel_cost || 0) * 100));

      card.innerHTML = `
        <div class="sol-profile-name">${cfg.label}</div>
        <div class="sol-stat">
          <span class="sol-stat-lbl">ETA</span>
          <span class="sol-stat-val">${formatEta(sol.total_time)}</span>
        </div>
        <div class="sol-stat">
          <span class="sol-stat-lbl">Fuel</span>
          <span class="sol-stat-val">${fuelPct}%</span>
        </div>
        <div class="sol-fuel-bar"><div class="sol-fuel-fill" style="width: ${fuelPct}%"></div></div>
        <div class="sol-stat">
          <span class="sol-stat-lbl">Accuracy</span>
          <span class="sol-stat-val">${formatDistance(sol.accuracy)}</span>
        </div>
        <div class="sol-stat">
          <span class="sol-stat-lbl">Risk</span>
          <span class="sol-risk-badge ${riskClass}">${(sol.risk_level || cfg.riskLabel).toUpperCase()}</span>
        </div>
        ${sol.description ? `<div class="nav-sol-desc">${sol.description}</div>` : ""}
      `;

      grid.appendChild(card);
    }

    // If a target is selected and a profile-supporting action is pending,
    // show a confirm/engage button below the cards
    this._renderEngageButton();
  }

  /** Show an "Engage" button below nav sol cards when a target + profile are ready */
  _renderEngageButton() {
    let engageBtn = this.shadowRoot.getElementById("nav-sol-engage");
    const targetSelect = this.shadowRoot.getElementById("target-select");
    const targetId = targetSelect?.value;

    if (this._pendingAction && PROFILE_PROGRAMS.includes(this._pendingAction) && targetId) {
      if (!engageBtn) {
        engageBtn = document.createElement("button");
        engageBtn.id = "nav-sol-engage";
        engageBtn.className = "coord-go-btn";
        engageBtn.style.cssText = "width: 100%; margin-top: 8px; padding: 10px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; border: none; background: var(--status-nominal, #00ff88); color: var(--bg-primary, #0a0a0f); font-family: var(--font-sans, 'Inter', sans-serif);";
        engageBtn.addEventListener("click", () => {
          const tgt = this.shadowRoot.getElementById("target-select")?.value;
          if (tgt && this._pendingAction) {
            this._sendTargetCommand(this._pendingAction, tgt);
            this._hideTargetSelect();
          }
        });
        const section = this.shadowRoot.getElementById("nav-solutions");
        section.appendChild(engageBtn);
      }
      const profileLabel = PROFILE_CONFIG[this._selectedProfile]?.label || this._selectedProfile;
      engageBtn.textContent = `Engage ${this._pendingAction.toUpperCase()} [${profileLabel}]`;
      engageBtn.style.display = "block";
    } else if (engageBtn) {
      engageBtn.style.display = "none";
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

    // Header: badge, command, active profile, target
    const programLabel = (fc.program || "").toUpperCase().replace(/_/g, " ");
    this.shadowRoot.getElementById("status-command").textContent = programLabel || "AUTOPILOT";
    this.shadowRoot.getElementById("status-target").textContent = fc.target ? `-> ${fc.target}` : "";
    this.shadowRoot.getElementById("status-text").textContent = fc.statusText || "";

    // Show active profile badge if autopilot is using a profile-supporting program
    const profileBadge = this.shadowRoot.getElementById("active-profile-badge");
    if (profileBadge) {
      const isProfileProgram = PROFILE_PROGRAMS.includes(fc.program?.toLowerCase()) ||
        fc.program?.toLowerCase() === "goto_position" || fc.program?.toLowerCase() === "set_course";
      if (isProfileProgram && this._selectedProfile) {
        const cfg = PROFILE_CONFIG[this._selectedProfile];
        profileBadge.textContent = (cfg?.label || this._selectedProfile).toUpperCase();
        profileBadge.className = `active-profile-badge ${this._selectedProfile}`;
      } else {
        profileBadge.classList.add("hidden");
      }
    }

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
