/**
 * Reactor Balance Game (ARCADE tier)
 *
 * Real-time reactor power/heat balancing mini-game. The reactor generates power
 * but also heat. Player adjusts reactor output to stay in the "sweet spot"
 * between power demand and thermal capacity.
 *
 * Reads from stateManager: engineering (reactor_output, reactor_percent) and
 * thermal (hull_temperature, max_temperature, heat_generated, heat_radiated).
 * Sends: set_reactor_output command on slider change.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

// Zone boundaries (percent of reactor output)
const GREEN_MIN = 60;
const GREEN_MAX = 100;
const YELLOW_MAX = 110;
// Above YELLOW_MAX = red zone (overstress)

// Canvas dimensions
const CANVAS_W = 480;
const CANVAS_H = 280;

class ReactorBalanceGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._animFrame = null;
    this._lastTime = 0;

    // State from telemetry
    this._reactorPercent = 50;
    this._hullTemp = 300;
    this._maxTemp = 500;
    this._warnTemp = 400;
    this._heatGen = 0;
    this._heatRad = 0;

    // Reactor core animation state
    this._pulsePhase = 0;
    this._particleAngle = 0;

    // Slider drag state
    this._dragging = false;
    this._sliderValue = 50; // local slider value (percent 0-120)
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

        .reactor-container {
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
          image-rendering: auto;
        }

        /* --- Slider control --- */
        .slider-row {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .slider-label {
          font-size: 0.65rem;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: #667;
          white-space: nowrap;
          min-width: 54px;
        }

        input[type="range"] {
          flex: 1;
          -webkit-appearance: none;
          height: 6px;
          border-radius: 3px;
          background: #1a1a2e;
          outline: none;
        }

        input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: #4488ff;
          border: 2px solid #224;
          cursor: pointer;
          box-shadow: 0 0 6px rgba(68, 136, 255, 0.4);
        }

        input[type="range"]::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: #4488ff;
          border: 2px solid #224;
          cursor: pointer;
        }

        .slider-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: #aab;
          min-width: 40px;
          text-align: right;
        }

        /* --- Status row --- */
        .status-row {
          display: flex;
          justify-content: space-between;
          font-size: 0.65rem;
          color: #667;
          letter-spacing: 0.08em;
        }

        .status-row .value {
          color: #99a;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .status-row .nominal { color: #4a4; }
        .status-row .warning { color: #cc8; }
        .status-row .critical { color: #c44; }

        .idle-msg {
          text-align: center;
          color: #445;
          font-size: 0.75rem;
          padding: 20px 0;
          letter-spacing: 0.05em;
        }
      </style>

      <div class="reactor-container">
        <canvas width="${CANVAS_W}" height="${CANVAS_H}"></canvas>

        <div class="slider-row">
          <span class="slider-label">OUTPUT</span>
          <input type="range" min="0" max="120" step="1" value="50">
          <span class="slider-value">50%</span>
        </div>

        <div class="status-row">
          <span>HEAT: <span class="value heat-status">--</span></span>
          <span>NET: <span class="value net-status">--</span></span>
          <span>TEMP: <span class="value temp-status">--</span></span>
        </div>
      </div>
    `;
  }

  _setupCanvas() {
    this._canvas = this.shadowRoot.querySelector("canvas");
    this._ctx = this._canvas.getContext("2d");
  }

  _setupListeners() {
    const slider = this.shadowRoot.querySelector('input[type="range"]');
    const valueDisplay = this.shadowRoot.querySelector(".slider-value");

    slider.addEventListener("input", (e) => {
      const val = parseInt(e.target.value, 10);
      this._sliderValue = val;
      valueDisplay.textContent = `${val}%`;
    });

    // Send command on change (mouseup / touchend) to avoid spamming
    slider.addEventListener("change", (e) => {
      const val = parseInt(e.target.value, 10);
      wsClient.sendShipCommand("set_reactor_output", { output: val });
    });
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._readTelemetry();
    });
  }

  _readTelemetry() {
    // Engineering telemetry: reactor_output (0-1), reactor_percent (0-100)
    const ship = stateManager.getShipState();
    const eng = ship?.engineering || {};
    const thermal = stateManager.getThermal() || {};

    if (eng.reactor_percent !== undefined) {
      this._reactorPercent = eng.reactor_percent;
      // Sync slider if user is not actively dragging
      if (!this._dragging) {
        const slider = this.shadowRoot.querySelector('input[type="range"]');
        const valueDisplay = this.shadowRoot.querySelector(".slider-value");
        if (slider && Math.abs(this._sliderValue - this._reactorPercent) > 2) {
          this._sliderValue = Math.round(this._reactorPercent);
          slider.value = this._sliderValue;
          valueDisplay.textContent = `${this._sliderValue}%`;
        }
      }
    }

    this._hullTemp = thermal.hull_temperature ?? 300;
    this._maxTemp = thermal.max_temperature ?? 500;
    this._warnTemp = thermal.warning_temperature ?? 400;
    this._heatGen = thermal.heat_generated ?? 0;
    this._heatRad = thermal.heat_radiated ?? 0;

    // Update status row
    this._updateStatusRow();
  }

  _updateStatusRow() {
    const heatEl = this.shadowRoot.querySelector(".heat-status");
    const netEl = this.shadowRoot.querySelector(".net-status");
    const tempEl = this.shadowRoot.querySelector(".temp-status");
    if (!heatEl) return;

    const netRate = this._heatGen - this._heatRad;
    const tempPct = (this._hullTemp / this._maxTemp) * 100;

    heatEl.textContent = `${this._heatGen.toFixed(0)} W`;
    netEl.textContent = `${netRate >= 0 ? "+" : ""}${netRate.toFixed(0)} W/s`;
    tempEl.textContent = `${this._hullTemp.toFixed(0)} K`;

    // Color coding
    netEl.className = "value " + (netRate > 50 ? "critical" : netRate > 0 ? "warning" : "nominal");
    tempEl.className = "value " + (tempPct > 80 ? "critical" : tempPct > 60 ? "warning" : "nominal");
  }

  _startAnimation() {
    const loop = (time) => {
      const dt = Math.min((time - this._lastTime) / 1000, 0.1);
      this._lastTime = time;
      this._drawCanvas(dt);
      this._animFrame = requestAnimationFrame(loop);
    };
    this._animFrame = requestAnimationFrame(loop);
  }

  _drawCanvas(dt) {
    const ctx = this._ctx;
    const W = CANVAS_W;
    const H = CANVAS_H;

    ctx.clearRect(0, 0, W, H);

    // Update animation phases
    this._pulsePhase += dt * 2.0;
    this._particleAngle += dt * 0.8;

    const output = this._sliderValue; // 0-120
    const tempPct = Math.min(1, this._hullTemp / this._maxTemp);

    // --- Left gauge: Power Output ---
    this._drawGauge(ctx, 40, 30, 80, 200, output / 120, "POWER", `${output}%`, [
      { start: 0,    end: GREEN_MIN / 120, color: "#334" },        // below useful
      { start: GREEN_MIN / 120, end: GREEN_MAX / 120, color: "#2a5a2a" },  // green zone
      { start: GREEN_MAX / 120, end: YELLOW_MAX / 120, color: "#5a5a2a" }, // yellow zone
      { start: YELLOW_MAX / 120, end: 1.0, color: "#5a2a2a" },              // red zone
    ]);

    // --- Right gauge: Heat Level ---
    this._drawGauge(ctx, W - 120, 30, 80, 200, tempPct, "HEAT", `${this._hullTemp.toFixed(0)}K`, [
      { start: 0,   end: 0.5,  color: "#2a3a5a" },  // cool
      { start: 0.5, end: 0.75, color: "#5a5a2a" },   // warm
      { start: 0.75, end: 1.0, color: "#5a2a2a" },   // hot
    ]);

    // --- Center: Reactor core visualization ---
    this._drawReactorCore(ctx, W / 2, H / 2, output, tempPct);

    // --- Sweet spot indicator ---
    this._drawSweetSpot(ctx, W / 2, H - 20, output);
  }

  /**
   * Draw a vertical gauge bar with colored zones.
   */
  _drawGauge(ctx, x, y, w, h, fillPct, label, valueText, zones) {
    // Background
    ctx.fillStyle = "#0a0a14";
    ctx.strokeStyle = "#1a1a2e";
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);

    // Zone backgrounds
    for (const zone of zones) {
      const zy = y + h * (1 - zone.end);
      const zh = h * (zone.end - zone.start);
      ctx.fillStyle = zone.color;
      ctx.globalAlpha = 0.3;
      ctx.fillRect(x + 1, zy, w - 2, zh);
    }
    ctx.globalAlpha = 1;

    // Fill bar (bottom-up)
    const fillH = h * Math.min(1, fillPct);
    const fillY = y + h - fillH;

    // Determine fill color based on value
    let fillColor;
    if (fillPct > YELLOW_MAX / 120) {
      fillColor = "#ee3322";
    } else if (fillPct > GREEN_MAX / 120) {
      fillColor = "#ccaa22";
    } else if (fillPct > GREEN_MIN / 120) {
      fillColor = "#44aa44";
    } else {
      fillColor = "#4466aa";
    }

    ctx.fillStyle = fillColor;
    ctx.globalAlpha = 0.7;
    ctx.fillRect(x + 2, fillY, w - 4, fillH);
    ctx.globalAlpha = 1;

    // Level marker line
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, fillY);
    ctx.lineTo(x + w, fillY);
    ctx.stroke();

    // Label above
    ctx.fillStyle = "#667";
    ctx.font = "bold 9px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label, x + w / 2, y - 6);

    // Value below
    ctx.fillStyle = "#aab";
    ctx.font = "12px monospace";
    ctx.fillText(valueText, x + w / 2, y + h + 16);
  }

  /**
   * Draw the central animated reactor core.
   */
  _drawReactorCore(ctx, cx, cy, output, tempPct) {
    const baseRadius = 35;
    const pulse = Math.sin(this._pulsePhase) * 0.15 + 1.0;
    const radius = baseRadius * pulse;

    // Determine core color based on output level
    let r, g, b;
    if (output > YELLOW_MAX) {
      // Red — overstress
      r = 255; g = 60; b = 30;
    } else if (output > GREEN_MAX) {
      // Orange-yellow — pushing limits
      r = 240; g = 180; b = 40;
    } else if (output > GREEN_MIN) {
      // Cyan-green — nominal sweet spot
      r = 60; g = 200; b = 220;
    } else {
      // Dim blue — low power
      r = 40; g = 80; b = 180;
    }

    // Outer glow
    const glowAlpha = 0.15 + (output / 120) * 0.3;
    const gradient = ctx.createRadialGradient(cx, cy, radius * 0.3, cx, cy, radius * 2.5);
    gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${glowAlpha})`);
    gradient.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(cx - radius * 3, cy - radius * 3, radius * 6, radius * 6);

    // Core circle
    const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    coreGrad.addColorStop(0, `rgba(${Math.min(255, r + 80)}, ${Math.min(255, g + 80)}, ${Math.min(255, b + 80)}, 0.9)`);
    coreGrad.addColorStop(0.6, `rgba(${r}, ${g}, ${b}, 0.7)`);
    coreGrad.addColorStop(1, `rgba(${r >> 1}, ${g >> 1}, ${b >> 1}, 0.3)`);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = coreGrad;
    ctx.fill();

    // Spinning particle ring
    const particleCount = 8;
    for (let i = 0; i < particleCount; i++) {
      const angle = this._particleAngle + (i / particleCount) * Math.PI * 2;
      const orbitR = radius * 1.6;
      const px = cx + Math.cos(angle) * orbitR;
      const py = cy + Math.sin(angle) * orbitR;
      const pSize = 2 + (output / 120) * 2;

      ctx.beginPath();
      ctx.arc(px, py, pSize, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.5)`;
      ctx.fill();
    }

    // Center text
    ctx.fillStyle = "#fff";
    ctx.font = "bold 14px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${output}%`, cx, cy);
  }

  /**
   * Draw the sweet-spot indicator at the bottom: a small bar showing
   * where current output sits relative to optimal.
   */
  _drawSweetSpot(ctx, cx, cy, output) {
    const barW = 200;
    const barH = 6;
    const x = cx - barW / 2;
    const y = cy - barH / 2;

    // Background
    ctx.fillStyle = "#0a0a14";
    ctx.fillRect(x, y, barW, barH);

    // Sweet spot zone (60-100%)
    const sweetL = x + (GREEN_MIN / 120) * barW;
    const sweetW = ((GREEN_MAX - GREEN_MIN) / 120) * barW;
    ctx.fillStyle = "rgba(0, 255, 100, 0.15)";
    ctx.fillRect(sweetL, y, sweetW, barH);

    // Current position marker
    const markerX = x + (output / 120) * barW;
    ctx.fillStyle = "#fff";
    ctx.fillRect(markerX - 1, y - 2, 2, barH + 4);

    // Label
    ctx.fillStyle = "#556";
    ctx.font = "8px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("SWEET SPOT", cx, cy - 8);
  }
}

customElements.define("reactor-balance-game", ReactorBalanceGame);
