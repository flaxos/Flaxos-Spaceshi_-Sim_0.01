/**
 * RCS Thruster Display — top-down ship diagram showing all 12 RCS thrusters
 * with live throttle visualization and manual fire controls.
 *
 * Tier-aware:
 *   MANUAL — full interactive: click to select, throttle slider, FIRE button
 *   RAW    — read-only display (no fire controls)
 *   ARCADE / CPU-ASSIST — hidden via tiers.css
 *
 * Data source: stateManager.getShipState()?.systems?.rcs
 *   .thrusters[]  — per-thruster { id, throttle, max_thrust, fuel_rate, torque, position, direction }
 *   .total_torque  — [roll, pitch, yaw] in N*m
 *   .control_mode  — "rate" | "attitude" | "direct"
 *   .controller    — { kp, kd, max_rate, smoothed_target }
 *
 * Command: rcs_fire_thruster { thruster_id, throttle (0-1), duration (seconds) }
 */
import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

// Thruster layout mapping: ship-space positions to SVG coordinates.
// Ship nose points RIGHT (+X). SVG viewBox is 0 0 250 150.
// Ship center is at (125, 75).
const THRUSTER_LAYOUT = {
  // Bow thrusters (+X = 5) -> SVG x ~200
  pitch_up:       { sx: 200, sy: 50, dx: 0, dy: -1, label: "Pitch+" },
  pitch_down:     { sx: 200, sy: 100, dx: 0, dy: 1,  label: "Pitch-" },
  yaw_left:       { sx: 210, sy: 60,  dx: 0, dy: -1, label: "Yaw L" },
  yaw_right:      { sx: 210, sy: 90,  dx: 0, dy: 1,  label: "Yaw R" },
  // Stern thrusters (-X = -5) -> SVG x ~50
  pitch_up_aft:   { sx: 50, sy: 50,  dx: 0, dy: -1, label: "Pitch+ Aft" },
  pitch_down_aft: { sx: 50, sy: 100, dx: 0, dy: 1,  label: "Pitch- Aft" },
  yaw_left_aft:   { sx: 40, sy: 60,  dx: 0, dy: -1, label: "Yaw L Aft" },
  yaw_right_aft:  { sx: 40, sy: 90,  dx: 0, dy: 1,  label: "Yaw R Aft" },
  // Port/Starboard roll thrusters (y = +/-3) -> SVG y ~30 / ~120
  roll_cw:        { sx: 140, sy: 120, dx: 0, dy: 1,  label: "Roll CW" },
  roll_ccw:       { sx: 110, sy: 30,  dx: 0, dy: -1, label: "Roll CCW" },
  roll_cw_2:      { sx: 110, sy: 120, dx: 0, dy: -1, label: "Roll CW 2" },   // note: z- at bottom = thrust up
  roll_ccw_2:     { sx: 140, sy: 30,  dx: 0, dy: 1,  label: "Roll CCW 2" },
};

class RcsThrusterDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._selectedThruster = null;
    this._tier = window.controlTier || "arcade";
    this._lastUpdate = 0;
    this._updateInterval = 200; // 5 Hz throttle
    this._rafId = null;
    this._onTier = null;
    // Cache thruster data to avoid redundant redraws
    this._cachedThrusters = null;
    this._cachedRcs = null;
  }

  connectedCallback() {
    this._render();
    this._unsub = stateManager.subscribe("*", () => this._throttledUpdate());
    this._onTier = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._updateFireControls();
    };
    document.addEventListener("tier-change", this._onTier);
    this._updateFromState();
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
    if (this._onTier) { document.removeEventListener("tier-change", this._onTier); this._onTier = null; }
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
  }

  /** Rate-limit state updates to ~5 Hz */
  _throttledUpdate() {
    const now = performance.now();
    if (now - this._lastUpdate < this._updateInterval) return;
    this._lastUpdate = now;
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = requestAnimationFrame(() => {
      this._rafId = null;
      this._updateFromState();
    });
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${RcsThrusterDisplay._styles()}</style>
      <div class="rcs-display">
        <div class="svg-container">
          <svg viewBox="0 0 250 150" xmlns="http://www.w3.org/2000/svg" class="ship-svg">
            ${RcsThrusterDisplay._shipHullSVG()}
            <g class="thrusters">${this._thrustersSVG()}</g>
          </svg>
        </div>

        <!-- Selected thruster detail + controls -->
        <div class="detail-panel" id="detail-panel" style="display:none">
          <div class="detail-header">
            <span class="detail-id" id="detail-id">--</span>
            <button class="detail-close" id="detail-close" title="Deselect">&times;</button>
          </div>
          <div class="detail-row"><span class="dlbl">Throttle</span><span class="dval" id="detail-throttle">0%</span></div>
          <div class="detail-row"><span class="dlbl">Max Thrust</span><span class="dval" id="detail-max-thrust">-- N</span></div>
          <div class="detail-row"><span class="dlbl">Torque</span><span class="dval" id="detail-torque">--</span></div>
          <div class="fire-controls" id="fire-controls">
            <div class="slider-row">
              <label class="slider-label">Power</label>
              <input type="range" min="0" max="100" value="50" class="throttle-slider" id="fire-slider">
              <span class="slider-val" id="fire-slider-val">50%</span>
            </div>
            <div class="btn-row">
              <button class="btn-fire" id="btn-fire">FIRE</button>
              <button class="btn-clear" id="btn-clear-all">CLEAR ALL</button>
            </div>
          </div>
        </div>

        <!-- Aggregate readouts -->
        <div class="readouts">
          <div class="readout-row">
            <span class="rlbl">Total Torque</span>
            <span class="rval" id="total-torque">R:0 P:0 Y:0</span>
          </div>
          <div class="readout-row">
            <span class="rlbl">Control Mode</span>
            <span class="rval" id="control-mode">--</span>
          </div>
          <div class="readout-row">
            <span class="rlbl">PD Gains</span>
            <span class="rval" id="pd-gains">kp:-- kd:--</span>
          </div>
          <div class="readout-row">
            <span class="rlbl">Active</span>
            <span class="rval" id="active-count">0 / 12</span>
          </div>
        </div>
      </div>
    `;
    this._bindEvents();
  }

  _bindEvents() {
    const root = this.shadowRoot;

    // Thruster click selection
    root.querySelector(".ship-svg").addEventListener("click", (e) => {
      const thrusterEl = e.target.closest("[data-thruster-id]");
      if (thrusterEl) {
        const id = thrusterEl.dataset.thrusterId;
        this._selectThruster(id === this._selectedThruster ? null : id);
      }
    });

    // Close detail panel
    root.getElementById("detail-close").addEventListener("click", () => this._selectThruster(null));

    // Slider live value
    const slider = root.getElementById("fire-slider");
    const sliderVal = root.getElementById("fire-slider-val");
    slider.addEventListener("input", () => {
      sliderVal.textContent = `${slider.value}%`;
    });

    // FIRE button
    root.getElementById("btn-fire").addEventListener("click", () => {
      if (!this._selectedThruster) return;
      const throttle = parseInt(slider.value, 10) / 100;
      wsClient.sendShipCommand("rcs_fire_thruster", {
        thruster_id: this._selectedThruster,
        throttle,
        duration: 1.0,
      }).catch(err => console.warn("rcs_fire_thruster failed:", err.message));
    });

    // CLEAR ALL button
    root.getElementById("btn-clear-all").addEventListener("click", () => {
      // Send zero throttle to all known thrusters
      const rcs = stateManager.getShipState()?.systems?.rcs;
      const thrusters = rcs?.thrusters || [];
      for (const t of thrusters) {
        wsClient.sendShipCommand("rcs_fire_thruster", {
          thruster_id: t.id,
          throttle: 0,
          duration: 0,
        }).catch(() => {});
      }
    });
  }

  _selectThruster(id) {
    this._selectedThruster = id;
    const root = this.shadowRoot;

    // Update SVG selection highlight
    root.querySelectorAll("[data-thruster-id]").forEach(el => {
      el.classList.toggle("selected", el.dataset.thrusterId === id);
    });

    const panel = root.getElementById("detail-panel");
    if (!id) {
      panel.style.display = "none";
      return;
    }
    panel.style.display = "";
    this._updateDetailPanel();
  }

  _updateDetailPanel() {
    if (!this._selectedThruster) return;
    const rcs = stateManager.getShipState()?.systems?.rcs;
    const thrusters = rcs?.thrusters || [];
    const t = thrusters.find(t => t.id === this._selectedThruster);
    const root = this.shadowRoot;

    root.getElementById("detail-id").textContent = this._selectedThruster;

    if (t) {
      const pct = Math.round((t.throttle || 0) * 100);
      root.getElementById("detail-throttle").textContent = `${pct}%`;
      root.getElementById("detail-max-thrust").textContent = `${t.max_thrust || 0} N`;
      const torque = t.torque || [0, 0, 0];
      root.getElementById("detail-torque").textContent =
        `[${torque.map(v => v.toFixed(0)).join(", ")}] N\u00b7m`;
    } else {
      root.getElementById("detail-throttle").textContent = "--";
      root.getElementById("detail-max-thrust").textContent = "--";
      root.getElementById("detail-torque").textContent = "--";
    }

    this._updateFireControls();
  }

  /** Show/hide fire controls based on tier */
  _updateFireControls() {
    const fc = this.shadowRoot.getElementById("fire-controls");
    if (!fc) return;
    // Only MANUAL tier gets interactive fire controls
    fc.style.display = (this._tier === "manual") ? "" : "none";
  }

  _updateFromState() {
    const rcs = stateManager.getShipState()?.systems?.rcs;
    if (!rcs) return;

    const thrusters = rcs.thrusters || [];
    const root = this.shadowRoot;

    // Update thruster indicators in SVG
    for (const t of thrusters) {
      const layout = THRUSTER_LAYOUT[t.id];
      if (!layout) continue;

      const group = root.querySelector(`[data-thruster-id="${t.id}"]`);
      if (!group) continue;

      const throttle = t.throttle || 0;
      const isActive = throttle > 0.01;

      // Update triangle fill color based on throttle
      const tri = group.querySelector(".thruster-tri");
      if (tri) {
        if (isActive) {
          // Interpolate from dim amber to bright amber
          const brightness = Math.round(40 + throttle * 215);
          const g = Math.round(throttle * 136);
          tri.setAttribute("fill", `rgb(${brightness}, ${g}, 0)`);
          tri.setAttribute("fill-opacity", (0.4 + throttle * 0.6).toFixed(2));
        } else {
          tri.setAttribute("fill", "#333");
          tri.setAttribute("fill-opacity", "0.6");
        }
      }

      // Update plume line visibility and length
      const plume = group.querySelector(".thruster-plume");
      if (plume) {
        if (isActive) {
          const len = 4 + throttle * 12;
          const x2 = layout.sx + layout.dx * len;
          const y2 = layout.sy + layout.dy * len;
          plume.setAttribute("x2", x2);
          plume.setAttribute("y2", y2);
          plume.setAttribute("stroke-opacity", (0.5 + throttle * 0.5).toFixed(2));
          plume.style.display = "";
        } else {
          plume.style.display = "none";
        }
      }
    }

    // Update selected thruster detail if open
    if (this._selectedThruster) {
      this._updateDetailPanel();
    }

    // Update aggregate readouts
    const totalTorque = rcs.total_torque || [0, 0, 0];
    root.getElementById("total-torque").textContent =
      `R:${totalTorque[0]?.toFixed(0) || 0} P:${totalTorque[1]?.toFixed(0) || 0} Y:${totalTorque[2]?.toFixed(0) || 0}`;

    root.getElementById("control-mode").textContent = rcs.control_mode || "--";

    const ctrl = rcs.controller || {};
    root.getElementById("pd-gains").textContent =
      `kp:${ctrl.kp?.toFixed(1) ?? "--"} kd:${ctrl.kd?.toFixed(1) ?? "--"}`;

    const activeCount = thrusters.filter(t => (t.throttle || 0) > 0.01).length;
    root.getElementById("active-count").textContent = `${activeCount} / ${thrusters.length || 12}`;
  }

  /** Generate SVG groups for all 12 thrusters */
  _thrustersSVG() {
    let svg = "";
    for (const [id, layout] of Object.entries(THRUSTER_LAYOUT)) {
      const { sx, sy, dx, dy } = layout;
      // Triangle points: 5px equilateral pointing in thrust direction
      const size = 5;
      // Base perpendicular to thrust direction
      const px = -dy, py = dx; // perpendicular
      const tipX = sx + dx * size;
      const tipY = sy + dy * size;
      const baseAx = sx + px * (size * 0.6);
      const baseAy = sy + py * (size * 0.6);
      const baseBx = sx - px * (size * 0.6);
      const baseBy = sy - py * (size * 0.6);

      // Plume line extends from tip in thrust direction (hidden by default)
      const plumeX2 = sx + dx * 16;
      const plumeY2 = sy + dy * 16;

      svg += `
        <g data-thruster-id="${id}" class="thruster-group" style="cursor:pointer">
          <circle cx="${sx}" cy="${sy}" r="8" fill="transparent" stroke="none" class="thruster-hit"/>
          <polygon class="thruster-tri"
            points="${tipX},${tipY} ${baseAx},${baseAy} ${baseBx},${baseBy}"
            fill="#333" fill-opacity="0.6" stroke="#555" stroke-width="0.5"/>
          <line class="thruster-plume" x1="${tipX}" y1="${tipY}" x2="${plumeX2}" y2="${plumeY2}"
            stroke="#ff8800" stroke-width="2" stroke-linecap="round" stroke-opacity="0.8" style="display:none"/>
        </g>`;
    }
    return svg;
  }

  /** Ship hull SVG: elongated hexagon, nose right */
  static _shipHullSVG() {
    // Diamond/hexagon shape centered at 125,75
    return `
      <polygon class="ship-hull"
        points="220,75 170,35 80,35 30,75 80,115 170,115"
        fill="rgba(20,20,30,0.3)" stroke="#2a2a3a" stroke-width="1.5"/>
      <!-- Nose marker -->
      <line x1="220" y1="75" x2="235" y2="75" stroke="#2a2a3a" stroke-width="1" stroke-dasharray="3,2"/>
      <text x="238" y="78" fill="#555" font-size="8" font-family="monospace">FWD</text>
      <!-- Center cross -->
      <line x1="120" y1="75" x2="130" y2="75" stroke="#2a2a3a" stroke-width="0.5"/>
      <line x1="125" y1="70" x2="125" y2="80" stroke="#2a2a3a" stroke-width="0.5"/>
    `;
  }

  static _styles() {
    return `
      :host {
        display: block;
        font-family: var(--font-mono, 'JetBrains Mono', 'Fira Code', monospace);
        color: var(--text-primary, #e0e0e0);
      }

      .rcs-display {
        padding: 10px;
      }

      /* -- SVG area -- */
      .svg-container {
        background: #0a0a12;
        border: 1px solid #1a1a2a;
        border-radius: 4px;
        padding: 4px;
        margin-bottom: 8px;
      }

      .ship-svg {
        width: 100%;
        height: auto;
        max-height: 160px;
      }

      /* Thruster hover highlight */
      .thruster-group:hover .thruster-tri {
        stroke: #ff8800;
        stroke-width: 1;
      }

      .thruster-group.selected .thruster-tri {
        stroke: #ff8800;
        stroke-width: 1.5;
        filter: drop-shadow(0 0 3px #ff8800);
      }

      /* Pulsing blue border for override thrusters */
      @keyframes override-pulse {
        0%, 100% { stroke: #4488ff; stroke-opacity: 0.4; }
        50%      { stroke: #4488ff; stroke-opacity: 1.0; }
      }

      .thruster-group.override .thruster-hit {
        stroke-width: 1.5;
        animation: override-pulse 1.2s ease-in-out infinite;
      }

      /* -- Detail panel -- */
      .detail-panel {
        background: #0e0e18;
        border: 1px solid #2a2a3a;
        border-radius: 4px;
        padding: 8px 10px;
        margin-bottom: 8px;
        font-size: 0.75rem;
      }

      .detail-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
      }

      .detail-id {
        font-weight: 700;
        color: #ff8800;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }

      .detail-close {
        background: none;
        border: none;
        color: #666;
        font-size: 1rem;
        cursor: pointer;
        padding: 0 4px;
        line-height: 1;
      }
      .detail-close:hover { color: #ff4444; }

      .detail-row {
        display: flex;
        justify-content: space-between;
        padding: 2px 0;
      }

      .dlbl {
        color: #555566;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }

      .dval {
        color: #e0e0e0;
        font-size: 0.75rem;
      }

      /* -- Fire controls (MANUAL only) -- */
      .fire-controls {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid #1a1a2a;
      }

      .slider-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
      }

      .slider-label {
        font-size: 0.65rem;
        color: #555566;
        text-transform: uppercase;
        min-width: 3em;
      }

      .throttle-slider {
        flex: 1;
        height: 4px;
        -webkit-appearance: none;
        appearance: none;
        background: #1a1a2a;
        border-radius: 2px;
        outline: none;
      }

      .throttle-slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #ff8800;
        cursor: pointer;
        border: 2px solid #0a0a12;
      }

      .throttle-slider::-moz-range-thumb {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #ff8800;
        cursor: pointer;
        border: 2px solid #0a0a12;
      }

      .slider-val {
        min-width: 3em;
        text-align: right;
        font-size: 0.75rem;
        color: #ff8800;
      }

      .btn-row {
        display: flex;
        gap: 6px;
      }

      .btn-fire, .btn-clear {
        flex: 1;
        padding: 6px 10px;
        font-family: inherit;
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        border-radius: 3px;
        cursor: pointer;
        transition: background 0.15s, border-color 0.15s;
      }

      .btn-fire {
        background: rgba(255, 136, 0, 0.15);
        border: 1px solid #ff8800;
        color: #ff8800;
      }
      .btn-fire:hover {
        background: rgba(255, 136, 0, 0.3);
      }

      .btn-clear {
        background: rgba(255, 68, 68, 0.1);
        border: 1px solid #553333;
        color: #ff6666;
      }
      .btn-clear:hover {
        background: rgba(255, 68, 68, 0.2);
        border-color: #ff4444;
      }

      /* -- Aggregate readouts -- */
      .readouts {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 4px 12px;
        font-size: 0.7rem;
      }

      .readout-row {
        display: flex;
        justify-content: space-between;
        padding: 2px 0;
      }

      .rlbl {
        color: #555566;
        font-size: 0.6rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }

      .rval {
        color: #ccc;
        font-size: 0.7rem;
      }

      /* -- No-data fallback -- */
      .no-data {
        text-align: center;
        color: #555566;
        font-size: 0.75rem;
        padding: 20px;
      }

      /* Responsive: stack readouts on narrow panels */
      @media (max-width: 320px) {
        .readouts {
          grid-template-columns: 1fr;
        }
      }
    `;
  }
}

customElements.define("rcs-thruster-display", RcsThrusterDisplay);
