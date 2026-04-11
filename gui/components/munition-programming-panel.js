/**
 * Munition Programming Panel (MANUAL tier only)
 *
 * Dense 2-column form for pre-configuring torpedo/missile parameters
 * before launch.  Wraps the server-side `program_munition` command
 * which stores a config consumed on the next matching launch.
 *
 * All nine tunable parameters from the server handler are exposed:
 *   munition_type, guidance_mode, warhead_type, flight_profile,
 *   pn_gain, fuse_distance, terminal_range, boost_duration, datalink
 *
 * Data flow: GUI -> wsClient.sendShipCommand("program_munition", {...})
 *            -> server stores program -> consumed on next launch
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

class MunitionProgrammingPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._lastProgramStatus = null;
  }

  connectedCallback() {
    this._render();
    this._setupInteraction();
    this._unsub = stateManager.subscribe("*", () => this._updateStatus());
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 12px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          color: var(--text-primary, #e0e0e0);
        }

        .form-grid {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 6px 12px;
          align-items: center;
        }

        .form-label {
          color: var(--text-dim, #555566);
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          white-space: nowrap;
        }

        /* Radio toggle group for munition type */
        .radio-group {
          display: flex;
          gap: 4px;
        }

        .radio-btn {
          flex: 1;
          padding: 5px 8px;
          background: rgba(255, 136, 0, 0.05);
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-dim, #555566);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          text-align: center;
          transition: all 0.15s ease;
        }

        .radio-btn:hover {
          border-color: #ff8800;
          color: var(--text-primary, #e0e0e0);
        }

        .radio-btn.active {
          background: rgba(255, 136, 0, 0.15);
          border-color: #ff8800;
          color: #ff8800;
        }

        select, input[type="number"] {
          background: var(--bg-input, #1a1a24);
          color: var(--text-primary, #e0e0e0);
          border: 1px solid var(--border-default, #2a2a3a);
          padding: 4px 6px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.72rem;
          width: 100%;
          box-sizing: border-box;
        }

        select:focus, input:focus {
          outline: none;
          border-color: #ff8800;
        }

        input[type="number"] {
          width: 80px;
        }

        .input-unit {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .unit-label {
          color: var(--text-dim, #555566);
          font-size: 0.6rem;
        }

        /* Checkbox toggle */
        .check-group {
          display: flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
        }

        .check-group input[type="checkbox"] {
          accent-color: #ff8800;
          width: 14px;
          height: 14px;
        }

        .check-label {
          color: var(--text-primary, #e0e0e0);
          font-size: 0.72rem;
        }

        /* Separator */
        .form-separator {
          grid-column: 1 / -1;
          height: 1px;
          background: var(--border-default, #2a2a3a);
          margin: 4px 0;
        }

        /* Program button */
        .program-btn {
          grid-column: 1 / -1;
          margin-top: 8px;
          padding: 8px 12px;
          background: rgba(255, 136, 0, 0.1);
          border: 1px solid #ff8800;
          color: #ff8800;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .program-btn:hover {
          background: rgba(255, 136, 0, 0.2);
          box-shadow: 0 0 8px rgba(255, 136, 0, 0.3);
        }

        .program-btn:active {
          background: rgba(255, 136, 0, 0.3);
        }

        /* Status feedback */
        .status-line {
          grid-column: 1 / -1;
          font-size: 0.65rem;
          text-align: center;
          margin-top: 4px;
          min-height: 1.2em;
          transition: color 0.2s ease;
        }

        .status-line.ok {
          color: #ff8800;
        }

        .status-line.err {
          color: var(--status-critical, #ff4444);
        }

        /* Current program readout */
        .current-program {
          grid-column: 1 / -1;
          margin-top: 6px;
          padding: 6px 8px;
          background: rgba(255, 136, 0, 0.05);
          border-left: 2px solid #ff8800;
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          line-height: 1.5;
        }

        .current-program strong {
          color: #ff8800;
        }
      </style>

      <div class="form-grid">
        <!-- Munition type radio toggle -->
        <span class="form-label">TYPE</span>
        <div class="radio-group">
          <button class="radio-btn active" id="type-torpedo" data-type="torpedo">TORPEDO</button>
          <button class="radio-btn" id="type-missile" data-type="missile">MISSILE</button>
        </div>

        <div class="form-separator"></div>

        <!-- Guidance mode -->
        <span class="form-label">GUIDANCE</span>
        <select id="guidance-mode">
          <option value="dumb">DUMB (no corrections)</option>
          <option value="guided" selected>GUIDED (PN tracking)</option>
          <option value="smart">SMART (predictive)</option>
        </select>

        <!-- Warhead type -->
        <span class="form-label">WARHEAD</span>
        <select id="warhead-type">
          <option value="fragmentation" selected>FRAGMENTATION</option>
          <option value="shaped_charge">SHAPED CHARGE</option>
          <option value="emp">EMP</option>
        </select>

        <!-- Flight profile -->
        <span class="form-label">PROFILE</span>
        <select id="flight-profile">
          <option value="direct" selected>DIRECT</option>
          <option value="evasive">EVASIVE (weave)</option>
          <option value="terminal_pop">TERMINAL POP (dive)</option>
          <option value="bracket">BRACKET (multi-vector)</option>
        </select>

        <div class="form-separator"></div>

        <!-- PN gain -->
        <span class="form-label">PN GAIN</span>
        <div class="input-unit">
          <input type="number" id="pn-gain" min="1.0" max="8.0" step="0.1" value="3.0">
          <span class="unit-label">N</span>
        </div>

        <!-- Fuse distance -->
        <span class="form-label">FUSE DIST</span>
        <div class="input-unit">
          <input type="number" id="fuse-distance" min="5" max="200" step="5" value="50">
          <span class="unit-label">m</span>
        </div>

        <!-- Terminal range -->
        <span class="form-label">TERM RANGE</span>
        <div class="input-unit">
          <input type="number" id="terminal-range" min="500" max="20000" step="500" value="5000">
          <span class="unit-label">m</span>
        </div>

        <!-- Boost duration -->
        <span class="form-label">BOOST DUR</span>
        <div class="input-unit">
          <input type="number" id="boost-duration" min="1.0" max="30.0" step="0.5" value="10">
          <span class="unit-label">s</span>
        </div>

        <div class="form-separator"></div>

        <!-- Datalink toggle -->
        <span class="form-label">DATALINK</span>
        <label class="check-group">
          <input type="checkbox" id="datalink" checked>
          <span class="check-label">Active</span>
        </label>

        <!-- Program button -->
        <button class="program-btn" id="program-btn">PROGRAM MUNITION</button>

        <!-- Status feedback -->
        <div class="status-line" id="status-line"></div>

        <!-- Current program readout from telemetry -->
        <div class="current-program" id="current-program" style="display: none;"></div>
      </div>
    `;
  }

  _setupInteraction() {
    const root = this.shadowRoot;

    // Munition type radio toggle
    root.querySelectorAll(".radio-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        root.querySelectorAll(".radio-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        // Update defaults based on type
        this._applyTypeDefaults(btn.dataset.type);
      });
    });

    // Guidance mode changes default PN gain
    root.getElementById("guidance-mode").addEventListener("change", (e) => {
      const defaults = { dumb: 0, guided: 4.0, smart: 6.0 };
      root.getElementById("pn-gain").value = defaults[e.target.value] ?? 3.0;
    });

    // Program button
    root.getElementById("program-btn").addEventListener("click", () => {
      this._sendProgram();
    });
  }

  /**
   * Apply sensible defaults when switching munition type.
   * Torpedoes: longer boost, wider fuse, lower PN gain.
   * Missiles: shorter boost, tighter fuse, higher PN gain.
   */
  _applyTypeDefaults(type) {
    const root = this.shadowRoot;
    if (type === "torpedo") {
      root.getElementById("pn-gain").value = 4.0;
      root.getElementById("fuse-distance").value = 100;
      root.getElementById("boost-duration").value = 8.0;
      root.getElementById("terminal-range").value = 5000;
    } else {
      root.getElementById("pn-gain").value = 5.0;
      root.getElementById("fuse-distance").value = 30;
      root.getElementById("boost-duration").value = 3.0;
      root.getElementById("terminal-range").value = 3000;
    }
  }

  _sendProgram() {
    const root = this.shadowRoot;

    // Read munition type from radio group
    const activeType = root.querySelector(".radio-btn.active");
    const munitionType = activeType?.dataset.type || "torpedo";

    const params = {
      munition_type: munitionType,
      guidance_mode: root.getElementById("guidance-mode").value,
      warhead_type: root.getElementById("warhead-type").value,
      flight_profile: root.getElementById("flight-profile").value,
      pn_gain: parseFloat(root.getElementById("pn-gain").value) || 3.0,
      fuse_distance: parseFloat(root.getElementById("fuse-distance").value) || 50,
      terminal_range: parseFloat(root.getElementById("terminal-range").value) || 5000,
      boost_duration: parseFloat(root.getElementById("boost-duration").value) || 10,
      datalink: root.getElementById("datalink").checked,
    };

    wsClient.sendShipCommand("program_munition", params);

    // Show feedback
    const statusEl = root.getElementById("status-line");
    statusEl.textContent =
      `${munitionType.toUpperCase()} programmed: ${params.guidance_mode.toUpperCase()}, ` +
      `PN=${params.pn_gain}, ${params.flight_profile.toUpperCase()}, ` +
      `fuse=${params.fuse_distance}m, boost=${params.boost_duration}s`;
    statusEl.className = "status-line ok";
    this._lastProgramStatus = params;
  }

  /**
   * Update current program readout from server telemetry if available.
   * The combat system stores _munition_program and may expose it via
   * telemetry; if not, we show last locally-sent program.
   */
  _updateStatus() {
    if (!this.offsetParent) return;
    const combat = stateManager.getCombat();
    const programEl = this.shadowRoot.getElementById("current-program");
    if (!programEl) return;

    // Check if server echoes munition_program in combat telemetry
    const serverProgram = combat?.munition_program;
    const program = serverProgram || this._lastProgramStatus;

    if (program) {
      programEl.style.display = "block";
      const parts = [];
      parts.push(`<strong>${(program.munition_type || "---").toUpperCase()}</strong>`);
      if (program.guidance_mode) parts.push(`guidance: ${program.guidance_mode}`);
      if (program.warhead_type) parts.push(`warhead: ${program.warhead_type}`);
      if (program.flight_profile) parts.push(`profile: ${program.flight_profile}`);
      if (program.pn_gain != null) parts.push(`PN: ${program.pn_gain}`);
      if (program.fuse_distance != null) parts.push(`fuse: ${program.fuse_distance}m`);
      if (program.terminal_range != null) parts.push(`terminal: ${program.terminal_range}m`);
      if (program.boost_duration != null) parts.push(`boost: ${program.boost_duration}s`);
      if (program.datalink != null) parts.push(`datalink: ${program.datalink ? "ON" : "OFF"}`);
      programEl.innerHTML = parts.join(" | ");
    } else {
      programEl.style.display = "none";
    }
  }
}

customElements.define("munition-programming-panel", MunitionProgrammingPanel);
