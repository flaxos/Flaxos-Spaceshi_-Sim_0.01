/**
 * Radiator Deploy Game (ARCADE tier)
 *
 * Visual radiator management mini-game. Ship has retractable radiator panels
 * that can be deployed (better cooling, but vulnerable to weapons fire) or
 * retracted (protected, but ship overheats). Player clicks panels to toggle.
 *
 * Reads from stateManager: engineering (radiators_deployed, radiator_priority)
 * and thermal (hull_temperature, max_temperature, heat_generated, heat_radiated).
 * Sends: manage_radiators command on panel click.
 *
 * The server currently models radiators as a single deployed/retracted state.
 * This game presents them as individual panels for visual interest — clicking
 * ANY panel sends the global deploy/retract toggle. When the server gains
 * per-panel control, the command can be updated to include panel_id.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getDegradation } from "../js/minigame-difficulty.js";

// Canvas dimensions
const CANVAS_W = 480;
const CANVAS_H = 340;

// Ship body geometry (centered in canvas)
const SHIP_CX = CANVAS_W / 2;
const SHIP_CY = CANVAS_H / 2 + 10;

// Radiator panel definitions — positions relative to ship center
// Each panel has: id, label, x/y offset from ship center, width, height, side
const PANELS = [
  { id: "port_fore",      label: "P1", side: "port",      ox: -70, oy: -30, w: 50, h: 14 },
  { id: "port_aft",       label: "P2", side: "port",      ox: -70, oy:  16, w: 50, h: 14 },
  { id: "starboard_fore", label: "S1", side: "starboard", ox:  20, oy: -30, w: 50, h: 14 },
  { id: "starboard_aft",  label: "S2", side: "starboard", ox:  20, oy:  16, w: 50, h: 14 },
  { id: "dorsal",         label: "D1", side: "dorsal",    ox: -14, oy: -65, w: 28, h: 40 },
  { id: "ventral",        label: "V1", side: "ventral",   ox: -14, oy:  30, w: 28, h: 40 },
];

// Heat particle pool
const MAX_PARTICLES = 60;

class RadiatorDeployGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._animFrame = null;
    this._lastTime = 0;

    // Radiator state — currently global (all deploy/retract together)
    this._deployed = true;
    this._priority = "balanced";

    // Per-panel visual state (for animation; all share server-side deployed state)
    this._panelStates = {};
    for (const p of PANELS) {
      this._panelStates[p.id] = { deployed: true, damaged: false, animProgress: 1.0 };
    }

    // Thermal state from telemetry
    this._hullTemp = 300;
    this._maxTemp = 500;
    this._warnTemp = 400;
    this._heatGen = 0;
    this._heatRad = 0;

    // Heat particles for deployed radiators
    this._particles = [];
    this._particleTimer = 0;
  }

  connectedCallback() {
    this._render();
    this._setupCanvas();
    this._setupListeners();
    this._subscribe();
    this._startAnimation();
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 0;
        }

        .radiator-container {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 12px;
        }

        canvas {
          width: 100%;
          height: auto;
          border-radius: 3px;
          background: #06060e;
          cursor: pointer;
          image-rendering: auto;
        }

        /* --- Heat bar at top --- */
        .heat-bar-wrapper {
          position: relative;
          height: 18px;
          border-radius: 2px;
          overflow: hidden;
          background: #0a0a14;
          border: 1px solid #1a1a2e;
        }

        .heat-bar-fill {
          position: absolute;
          top: 0;
          left: 0;
          bottom: 0;
          width: 0%;
          border-radius: 1px;
          transition: width 0.3s ease-out, background 0.3s ease;
        }

        .heat-bar-fill.cool {
          background: linear-gradient(90deg, #2244aa, #3366cc);
        }
        .heat-bar-fill.warm {
          background: linear-gradient(90deg, #aa8822, #ccaa33);
        }
        .heat-bar-fill.hot {
          background: linear-gradient(90deg, #cc4422, #ee3322);
          animation: heat-pulse 0.4s ease-in-out infinite alternate;
        }

        @keyframes heat-pulse {
          from { opacity: 0.8; }
          to { opacity: 1; }
        }

        .heat-bar-label {
          position: absolute;
          right: 6px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 0.65rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: #aab;
          z-index: 1;
          text-shadow: 0 0 4px rgba(0, 0, 0, 0.8);
        }

        .heat-bar-title {
          position: absolute;
          left: 6px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 0.6rem;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: #667;
          z-index: 1;
        }

        /* --- Priority buttons --- */
        .priority-row {
          display: flex;
          gap: 6px;
        }

        .priority-btn {
          flex: 1;
          padding: 5px 0;
          font-size: 0.65rem;
          font-weight: 600;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          background: #0a0a14;
          color: #556;
          cursor: pointer;
          transition: all 0.2s ease;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .priority-btn:hover {
          background: #121224;
          border-color: #334;
        }

        .priority-btn.active {
          border-color: #4488ff;
          color: #4488ff;
          background: #0a1a2e;
          box-shadow: 0 0 6px rgba(68, 136, 255, 0.2);
        }

        /* --- Status line --- */
        .status-line {
          font-size: 0.65rem;
          color: #667;
          text-align: center;
          letter-spacing: 0.08em;
        }

        .status-line .deployed { color: #4a8; }
        .status-line .retracted { color: #884; }

        /* --- Legend --- */
        .legend {
          display: flex;
          justify-content: center;
          gap: 14px;
          font-size: 0.6rem;
          color: #556;
        }

        .legend-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .legend-dot {
          width: 8px;
          height: 8px;
          border-radius: 2px;
        }

        .legend-dot.deployed { background: #4488cc; box-shadow: 0 0 4px rgba(68, 136, 204, 0.5); }
        .legend-dot.retracted { background: #333; }
        .legend-dot.damaged { background: #aa3322; }
      </style>

      <div class="radiator-container">
        <div class="heat-bar-wrapper">
          <span class="heat-bar-title">HULL HEAT</span>
          <div class="heat-bar-fill cool"></div>
          <span class="heat-bar-label">300 K</span>
        </div>

        <canvas width="${CANVAS_W}" height="${CANVAS_H}"></canvas>

        <div class="priority-row">
          <button class="priority-btn active" data-priority="balanced">Balanced</button>
          <button class="priority-btn" data-priority="cooling">Max Cool</button>
          <button class="priority-btn" data-priority="stealth">Stealth</button>
        </div>

        <div class="status-line">
          Radiators: <span class="deployed">DEPLOYED</span>
        </div>

        <div class="legend">
          <span class="legend-item"><span class="legend-dot deployed"></span> Deployed</span>
          <span class="legend-item"><span class="legend-dot retracted"></span> Retracted</span>
          <span class="legend-item"><span class="legend-dot damaged"></span> Damaged</span>
        </div>
      </div>
    `;
  }

  _setupCanvas() {
    this._canvas = this.shadowRoot.querySelector("canvas");
    this._ctx = this._canvas.getContext("2d");
  }

  _setupListeners() {
    // Canvas click — detect which radiator panel was clicked
    this._canvas.addEventListener("click", (e) => {
      const rect = this._canvas.getBoundingClientRect();
      // Scale from CSS size to canvas coordinate space
      const scaleX = CANVAS_W / rect.width;
      const scaleY = CANVAS_H / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      for (const panel of PANELS) {
        const ps = this._panelStates[panel.id];
        if (ps.damaged) continue; // can't toggle damaged panels

        // Compute panel screen rect
        const px = SHIP_CX + panel.ox;
        const py = SHIP_CY + panel.oy;

        // Expand hit area slightly for deployed panels
        const ext = ps.deployed ? this._getDeployExtent(panel) : 0;
        const hitX = panel.side === "port" ? px - ext : px;
        const hitW = panel.w + ext;
        const hitY = (panel.side === "dorsal") ? py - ext : py;
        const hitH = panel.h + ((panel.side === "dorsal" || panel.side === "ventral") ? ext : 0);

        if (mx >= hitX && mx <= hitX + hitW && my >= hitY && my <= hitY + hitH) {
          // Toggle global deploy state (server is global, not per-panel)
          const newDeployed = !this._deployed;
          wsClient.sendShipCommand("manage_radiators", { deployed: newDeployed });
          return;
        }
      }
    });

    // Priority buttons
    for (const btn of this.shadowRoot.querySelectorAll(".priority-btn")) {
      btn.addEventListener("click", () => {
        const priority = btn.dataset.priority;
        wsClient.sendShipCommand("manage_radiators", { priority });
      });
    }
  }

  /**
   * Get the visual extension distance for a deployed panel (how far it sticks out).
   */
  _getDeployExtent(panel) {
    if (panel.side === "port" || panel.side === "starboard") return 30;
    if (panel.side === "dorsal" || panel.side === "ventral") return 25;
    return 20;
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._readTelemetry();
    });
  }

  _readTelemetry() {
    const ship = stateManager.getShipState();
    const eng = ship?.engineering || {};
    const thermal = stateManager.getThermal() || {};
    const systems = stateManager.getSystems() || {};

    // Radiator global state
    if (eng.radiators_deployed !== undefined) {
      this._deployed = eng.radiators_deployed;
    }
    if (eng.radiator_priority) {
      this._priority = eng.radiator_priority;
    }

    // Sync all panel visual states to the global deployed state
    for (const p of PANELS) {
      this._panelStates[p.id].deployed = this._deployed;
    }

    // Check if radiator system is damaged via subsystem status
    const radStatus = systems.radiators;
    if (radStatus === "destroyed") {
      // Mark all panels as damaged
      for (const p of PANELS) {
        this._panelStates[p.id].damaged = true;
      }
    }

    // Thermal
    this._hullTemp = thermal.hull_temperature ?? 300;
    this._maxTemp = thermal.max_temperature ?? 500;
    this._warnTemp = thermal.warning_temperature ?? 400;
    this._heatGen = thermal.heat_generated ?? 0;
    this._heatRad = thermal.heat_radiated ?? 0;

    // Update heat bar
    this._updateHeatBar();

    // Update priority button active state
    for (const btn of this.shadowRoot.querySelectorAll(".priority-btn")) {
      btn.classList.toggle("active", btn.dataset.priority === this._priority);
    }

    // Update status text
    const statusEl = this.shadowRoot.querySelector(".status-line");
    if (statusEl) {
      const span = statusEl.querySelector("span");
      span.textContent = this._deployed ? "DEPLOYED" : "RETRACTED";
      span.className = this._deployed ? "deployed" : "retracted";
    }
  }

  _updateHeatBar() {
    const fill = this.shadowRoot.querySelector(".heat-bar-fill");
    const label = this.shadowRoot.querySelector(".heat-bar-label");
    if (!fill) return;

    const pct = Math.min(100, (this._hullTemp / this._maxTemp) * 100);
    fill.style.width = `${pct}%`;
    label.textContent = `${this._hullTemp.toFixed(0)} K`;

    fill.classList.remove("cool", "warm", "hot");
    if (pct > 80) {
      fill.classList.add("hot");
    } else if (pct > 55) {
      fill.classList.add("warm");
    } else {
      fill.classList.add("cool");
    }
  }

  _startAnimation() {
    const loop = (time) => {
      const dt = Math.min((time - this._lastTime) / 1000, 0.1);
      this._lastTime = time;
      this._updateParticles(dt);
      this._drawCanvas(dt);
      this._animFrame = requestAnimationFrame(loop);
    };
    this._animFrame = requestAnimationFrame(loop);
  }

  /**
   * Spawn and update heat particles flowing through deployed radiators.
   */
  _updateParticles(dt) {
    this._particleTimer += dt;

    // Spawn new particles from deployed radiators
    if (this._particleTimer > 0.05 && this._particles.length < MAX_PARTICLES) {
      this._particleTimer = 0;

      for (const panel of PANELS) {
        const ps = this._panelStates[panel.id];
        if (!ps.deployed || ps.damaged) continue;

        // Spawn particle at panel center, flowing outward
        const px = SHIP_CX + panel.ox + panel.w / 2;
        const py = SHIP_CY + panel.oy + panel.h / 2;

        let vx = 0, vy = 0;
        const speed = 30 + Math.random() * 20;
        if (panel.side === "port") { vx = -speed; vy = (Math.random() - 0.5) * 10; }
        else if (panel.side === "starboard") { vx = speed; vy = (Math.random() - 0.5) * 10; }
        else if (panel.side === "dorsal") { vy = -speed; vx = (Math.random() - 0.5) * 10; }
        else if (panel.side === "ventral") { vy = speed; vx = (Math.random() - 0.5) * 10; }

        this._particles.push({
          x: px + (Math.random() - 0.5) * panel.w * 0.6,
          y: py + (Math.random() - 0.5) * panel.h * 0.6,
          vx, vy,
          life: 1.0,
          size: 1.5 + Math.random() * 1.5,
        });
      }
    }

    // Update existing particles
    for (let i = this._particles.length - 1; i >= 0; i--) {
      const p = this._particles[i];
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.life -= dt * 1.2;
      if (p.life <= 0) {
        this._particles.splice(i, 1);
      }
    }
  }

  _drawCanvas(dt) {
    const ctx = this._ctx;
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

    // Draw ship body (angular top-down silhouette)
    this._drawShipBody(ctx);

    // Radiator damage randomly jams panels (deterministic per-panel)
    const radDmg = getDegradation("radiators");
    for (let i = 0; i < PANELS.length; i++) {
      const isStuck = radDmg > 0 && (i * 7 + 3) % 10 < radDmg * 10;
      if (isStuck) {
        this._panelStates[PANELS[i].id].deployed = false;
      }
    }

    // Draw radiator panels
    for (const panel of PANELS) {
      this._drawPanel(ctx, panel);
    }

    // Draw heat particles
    this._drawParticles(ctx);

    // Draw "click to toggle" hint
    ctx.fillStyle = "#334";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("CLICK PANELS TO TOGGLE", SHIP_CX, CANVAS_H - 8);
  }

  /**
   * Draw the ship body as an angular top-down silhouette.
   */
  _drawShipBody(ctx) {
    ctx.save();
    ctx.translate(SHIP_CX, SHIP_CY);

    // Angular corvette shape — pointed nose, wider stern
    ctx.beginPath();
    ctx.moveTo(0, -55);    // nose
    ctx.lineTo(12, -30);
    ctx.lineTo(16, 0);
    ctx.lineTo(18, 30);
    ctx.lineTo(14, 50);    // stern
    ctx.lineTo(-14, 50);
    ctx.lineTo(-18, 30);
    ctx.lineTo(-16, 0);
    ctx.lineTo(-12, -30);
    ctx.closePath();

    ctx.fillStyle = "#141422";
    ctx.strokeStyle = "#2a2a44";
    ctx.lineWidth = 1.5;
    ctx.fill();
    ctx.stroke();

    // Center spine line
    ctx.strokeStyle = "#1a1a33";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, -48);
    ctx.lineTo(0, 45);
    ctx.stroke();

    // Drive glow at stern
    const glowGrad = ctx.createRadialGradient(0, 50, 2, 0, 55, 20);
    glowGrad.addColorStop(0, "rgba(80, 140, 255, 0.4)");
    glowGrad.addColorStop(1, "rgba(80, 140, 255, 0)");
    ctx.fillStyle = glowGrad;
    ctx.fillRect(-20, 40, 40, 30);

    ctx.restore();
  }

  /**
   * Draw a single radiator panel with deploy/retract/damage state.
   */
  _drawPanel(ctx, panel) {
    const ps = this._panelStates[panel.id];
    const baseX = SHIP_CX + panel.ox;
    const baseY = SHIP_CY + panel.oy;

    // Animate deploy extension
    const targetProgress = ps.deployed ? 1.0 : 0.0;
    const animSpeed = 3.0; // per second
    if (ps.animProgress < targetProgress) {
      ps.animProgress = Math.min(targetProgress, ps.animProgress + animSpeed * 0.016);
    } else if (ps.animProgress > targetProgress) {
      ps.animProgress = Math.max(targetProgress, ps.animProgress - animSpeed * 0.016);
    }

    const ext = this._getDeployExtent(panel) * ps.animProgress;
    let drawX = baseX;
    let drawY = baseY;
    let drawW = panel.w;
    let drawH = panel.h;

    // Extend the panel outward from the ship
    if (panel.side === "port") {
      drawX = baseX - ext;
      drawW = panel.w + ext;
    } else if (panel.side === "starboard") {
      drawW = panel.w + ext;
    } else if (panel.side === "dorsal") {
      drawY = baseY - ext;
      drawH = panel.h + ext;
    } else if (panel.side === "ventral") {
      drawH = panel.h + ext;
    }

    // Panel color
    let fillColor, strokeColor;
    if (ps.damaged) {
      fillColor = "rgba(170, 50, 30, 0.4)";
      strokeColor = "#aa3322";
    } else if (ps.deployed) {
      // Blue-white glow when deployed, intensity based on heat dissipation
      const intensity = 0.3 + ps.animProgress * 0.4;
      fillColor = `rgba(68, 136, 204, ${intensity})`;
      strokeColor = "#6699cc";
    } else {
      fillColor = "rgba(40, 40, 60, 0.5)";
      strokeColor = "#333";
    }

    ctx.fillStyle = fillColor;
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1;
    ctx.fillRect(drawX, drawY, drawW, drawH);
    ctx.strokeRect(drawX, drawY, drawW, drawH);

    // Panel label
    ctx.fillStyle = ps.damaged ? "#aa3322" : (ps.deployed ? "#8ab" : "#445");
    ctx.font = "bold 8px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(panel.label, drawX + drawW / 2, drawY + drawH / 2);

    // Deployed glow effect — subtle edge highlight
    if (ps.deployed && !ps.damaged && ps.animProgress > 0.5) {
      ctx.shadowColor = "rgba(100, 180, 255, 0.3)";
      ctx.shadowBlur = 8;
      ctx.strokeStyle = "rgba(100, 180, 255, 0.3)";
      ctx.strokeRect(drawX, drawY, drawW, drawH);
      ctx.shadowBlur = 0;
    }
  }

  /**
   * Draw heat particles flowing outward through deployed radiators.
   */
  _drawParticles(ctx) {
    for (const p of this._particles) {
      const alpha = p.life * 0.6;
      // Color shifts from white (hot, near ship) to blue (cooled, far)
      const heat = Math.max(0, p.life - 0.3);
      const r = Math.round(150 + heat * 105);
      const g = Math.round(180 + heat * 75);
      const b = 255;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
      ctx.fill();
    }
  }
}

customElements.define("radiator-deploy-game", RadiatorDeployGame);
