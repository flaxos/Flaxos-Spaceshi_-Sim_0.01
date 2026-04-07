/**
 * Mass Estimation Game (ARCADE tier)
 *
 * Physics puzzle mini-game for the Science station. The player observes a
 * contact's thrust output (F) and measured acceleration (a), then adjusts
 * a mass slider to balance F = m * a. When the estimate is correct, a
 * balance scale tips into equilibrium and ship class suggestions appear.
 *
 * This is Newton's second law as gameplay. The player applies real physics
 * reasoning to classify unknown contacts by mass.
 *
 * State reads:
 *   sensor_contacts — array of contact objects
 *   targeting — for selected contact
 *   Contact fields: acceleration_magnitude, thrust_estimate, ir_brightness
 *
 * Commands sent:
 *   estimate_mass { contact_id, estimated_mass_kg } — when scale balanced
 *
 * Visible only in ARCADE tier (Science view).
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getDegradation } from "../js/minigame-difficulty.js";

// Canvas dimensions
const CANVAS_W = 400;
const CANVAS_H = 300;

// Balance scale geometry
const SCALE_CENTER_X = CANVAS_W / 2;
const SCALE_PIVOT_Y = 160;
const SCALE_ARM_LEN = 100;
const SCALE_BASE_Y = 240;
const PAN_RADIUS = 28;

// Mass slider range (kg) — covers small craft to capital ships
const MASS_MIN = 1000;        // 1 ton
const MASS_MAX = 5000000;     // 5000 tons
const MASS_DEFAULT = 100000;  // 100 tons

// Ship class brackets for suggestions
const SHIP_CLASSES = [
  { name: "Shuttle",     min: 1000,     max: 10000 },
  { name: "Fighter",     min: 10000,    max: 50000 },
  { name: "Corvette",    min: 50000,    max: 200000 },
  { name: "Frigate",     min: 200000,   max: 500000 },
  { name: "Destroyer",   min: 500000,   max: 2000000 },
  { name: "Cruiser",     min: 2000000,  max: 5000000 },
];

// Match tolerance: how close mass estimate needs to be (percentage)
const BALANCE_TOLERANCE = 0.15;  // 15% error is "balanced"
const BALANCE_TIGHT = 0.05;     // 5% error is "precise"
const CMD_COOLDOWN_MS = 3000;

// Colors
const BG_COLOR = "#0a0a14";
const GRID_COLOR = "#1a1a2a";
const SCALE_COLOR = "#6688cc";
const SCALE_BALANCED_COLOR = "#00ff88";
const FORCE_COLOR = "#ff8800";
const ACCEL_COLOR = "#ff4444";
const MASS_COLOR = "#4488ff";
const DIM_COLOR = "#445577";
const LABEL_COLOR = "#6688cc";

class MassEstimationGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    // Contact data
    this._contactId = null;
    this._thrustF = 0;       // Newtons
    this._accelA = 0;        // m/s^2
    this._trueMass = 0;      // kg (derived: F/a)

    // Player estimate
    this._estimatedMass = MASS_DEFAULT;

    // Scale animation state
    this._scaleAngle = 0;       // current tilt (radians), animated
    this._targetAngle = 0;      // target tilt
    this._balanceGlow = 0;      // glow intensity when balanced

    // Command state
    this._lastCmdTime = 0;
    this._cmdSent = false;

    // Animation
    this._animFrame = null;
    this._lastFrameTime = 0;
    this._pulsePhase = 0;

    // Subscriptions
    this._unsubscribe = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";

    // Canvas
    this._canvas = null;
    this._ctx = null;

    // Bound handlers
    this._boundFrame = this._frame.bind(this);
    this._boundSlider = this._onMassSlider.bind(this);
  }

  connectedCallback() {
    this._render();
    this._canvas = this.shadowRoot.getElementById("mass-canvas");
    this._ctx = this._canvas.getContext("2d");

    // Wire slider
    const slider = this.shadowRoot.getElementById("mass-slider");
    if (slider) slider.addEventListener("input", this._boundSlider);

    // State subscription
    this._unsubscribe = stateManager.subscribe("*", () => this._onStateUpdate());

    // Tier change
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._updateVisibility();
    };
    document.addEventListener("tier-change", this._tierHandler);

    this._onStateUpdate();
    this._startAnimation();
  }

  disconnectedCallback() {
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  // --- State ---

  _onStateUpdate() {
    this._updateVisibility();
    this._updateContactData();
  }

  _updateVisibility() {
    const isArcade = this._tier === "arcade";
    this.style.display = isArcade ? "block" : "none";
  }

  /**
   * Extract thrust and acceleration data from the selected contact.
   * If exact telemetry fields don't exist, derive from available data
   * or use plausible mock values with a procedural seed.
   */
  _updateContactData() {
    const targeting = stateManager.getTargeting();
    const contacts = stateManager.getContacts() || [];
    const selectedId = targeting?.designated_target || targeting?.locked_target || targeting?.target_id;

    let contact = null;
    if (selectedId && contacts.length > 0) {
      contact = contacts.find(c => (c.contact_id || c.id) === selectedId);
    }
    if (!contact && contacts.length > 0) {
      contact = contacts[0];
    }

    const contactId = contact ? (contact.contact_id || contact.id) : null;

    if (contactId !== this._contactId) {
      this._contactId = contactId;
      this._cmdSent = false;
    }

    if (contact) {
      // Try to read real telemetry fields
      const accel = contact.acceleration_magnitude ??
                    contact.accel_magnitude ??
                    contact.observed_accel ??
                    null;
      const thrust = contact.thrust_estimate ??
                     contact.ir_brightness ??
                     null;

      if (accel !== null && thrust !== null && accel > 0) {
        // Real data available
        this._accelA = accel;
        this._thrustF = thrust;
        this._trueMass = thrust / accel;
      } else if (accel !== null && accel > 0) {
        // Only acceleration available — estimate thrust from plausible mass range
        this._accelA = accel;
        // Seed a plausible mass from contact hash for consistent gameplay
        const seed = this._hashString(contactId || "unknown");
        const rng = this._seededRandom(seed);
        const logMass = Math.log10(MASS_MIN) + rng() * (Math.log10(MASS_MAX) - Math.log10(MASS_MIN));
        this._trueMass = Math.pow(10, logMass);
        this._thrustF = this._trueMass * accel;
      } else {
        // No real data — generate plausible mock values from contact ID
        const seed = this._hashString(contactId || "practice");
        const rng = this._seededRandom(seed);
        const logMass = Math.log10(MASS_MIN) + rng() * (Math.log10(MASS_MAX) - Math.log10(MASS_MIN));
        this._trueMass = Math.pow(10, logMass);
        this._accelA = 5 + rng() * 45;  // 5-50 m/s^2
        this._thrustF = this._trueMass * this._accelA;
      }
    } else {
      // Practice mode: generate fixed values
      const seed = Math.floor(Date.now() / 60000); // changes every minute
      const rng = this._seededRandom(seed);
      const logMass = Math.log10(MASS_MIN) + rng() * (Math.log10(MASS_MAX) - Math.log10(MASS_MIN));
      this._trueMass = Math.pow(10, logMass);
      this._accelA = 5 + rng() * 45;
      this._thrustF = this._trueMass * this._accelA;
    }
  }

  // --- Input ---

  _onMassSlider() {
    const slider = this.shadowRoot.getElementById("mass-slider");
    if (!slider) return;

    // Logarithmic slider mapping for wide mass range
    const t = Number(slider.value) / 1000; // 0..1
    const logMin = Math.log10(MASS_MIN);
    const logMax = Math.log10(MASS_MAX);
    this._estimatedMass = Math.pow(10, logMin + t * (logMax - logMin));

    // Update display
    const valEl = this.shadowRoot.getElementById("mass-val");
    if (valEl) valEl.textContent = this._formatMass(this._estimatedMass);
  }

  // --- Animation ---

  _startAnimation() {
    this._lastFrameTime = performance.now();
    this._animFrame = requestAnimationFrame(this._boundFrame);
  }

  _frame(timestamp) {
    const dt = Math.min((timestamp - this._lastFrameTime) / 1000, 0.1);
    this._lastFrameTime = timestamp;
    this._pulsePhase += dt * 2.0;

    // Calculate balance error
    const playerProduct = this._estimatedMass * this._accelA;
    const ratio = this._thrustF > 0 ? playerProduct / this._thrustF : 0;
    // ratio=1 means perfect balance; <1 means too light; >1 means too heavy
    const error = Math.abs(1 - ratio);
    const isBalanced = error <= BALANCE_TOLERANCE;
    const isTight = error <= BALANCE_TIGHT;

    // Target angle: tilts based on how far off the estimate is
    // Clamp to +/- 0.4 radians (~23 degrees)
    this._targetAngle = Math.max(-0.4, Math.min(0.4, (ratio - 1) * 0.8));

    // Smooth animation toward target angle
    this._scaleAngle += (this._targetAngle - this._scaleAngle) * Math.min(1, dt * 6);

    // Glow when balanced
    if (isBalanced) {
      this._balanceGlow = Math.min(1, this._balanceGlow + dt * 3);
    } else {
      this._balanceGlow = Math.max(0, this._balanceGlow - dt * 3);
    }

    // Send command when balanced
    if (isBalanced && !this._cmdSent && this._contactId &&
        timestamp - this._lastCmdTime > CMD_COOLDOWN_MS) {
      this._lastCmdTime = timestamp;
      this._cmdSent = true;
      wsClient.sendShipCommand("estimate_mass", {
        contact_id: this._contactId,
        estimated_mass_kg: Math.round(this._estimatedMass)
      }).catch(() => {
        // Best-effort
      });
    }

    // Reset command sent if player moves away
    if (!isBalanced) {
      this._cmdSent = false;
    }

    // Draw
    this._draw(ratio, isBalanced, isTight);

    this._animFrame = requestAnimationFrame(this._boundFrame);
  }

  // --- Drawing ---

  _draw(ratio, isBalanced, isTight) {
    const ctx = this._ctx;
    if (!ctx) return;
    const w = CANVAS_W;
    const h = CANVAS_H;

    // Clear
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, w, h);

    // Subtle grid
    ctx.strokeStyle = GRID_COLOR;
    ctx.lineWidth = 0.5;
    for (let x = 20; x < w; x += 30) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }

    // Header
    ctx.font = "bold 9px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillStyle = LABEL_COLOR;
    ctx.fillText("MASS ESTIMATION", 12, 14);

    ctx.textAlign = "right";
    ctx.fillStyle = DIM_COLOR;
    if (this._contactId) {
      ctx.fillText(`[${this._contactId}]`, w - 12, 14);
    } else {
      ctx.fillText("[PRACTICE MODE]", w - 12, 14);
    }

    // --- Top section: Contact data readouts ---
    this._drawDataReadouts(ctx);

    // --- Middle: Balance scale ---
    this._drawBalanceScale(ctx, isBalanced, isTight);

    // --- Bottom: Ship class suggestions ---
    this._drawShipClassSuggestions(ctx, isBalanced);
  }

  _drawDataReadouts(ctx) {
    const y = 36;
    const col1 = 30;
    const col2 = CANVAS_W / 2 + 20;

    // Sensor damage adds display jitter to measurement values
    const dmg = getDegradation("sensors");
    const jitter = (Math.random() - 0.5) * dmg * 15;
    const displayThrust = this._thrustF + jitter * this._thrustF * 0.01;
    const displayAccel = this._accelA + jitter * this._accelA * 0.01;

    // Thrust readout (left)
    ctx.font = "bold 8px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillStyle = DIM_COLOR;
    ctx.fillText("THRUST (F)", col1, y);

    ctx.font = "bold 16px 'JetBrains Mono', monospace";
    ctx.fillStyle = FORCE_COLOR;
    ctx.fillText(this._formatForce(displayThrust), col1, y + 18);

    // Thrust bar
    const barW = 140;
    const barH = 5;
    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(col1, y + 24, barW, barH);
    // Animated "plume" bar
    const plumeW = barW * (0.7 + Math.sin(this._pulsePhase * 3) * 0.1);
    ctx.fillStyle = FORCE_COLOR;
    ctx.globalAlpha = 0.6;
    ctx.fillRect(col1, y + 24, plumeW, barH);
    ctx.globalAlpha = 1.0;

    // Acceleration readout (right)
    ctx.font = "bold 8px 'JetBrains Mono', monospace";
    ctx.fillStyle = DIM_COLOR;
    ctx.fillText("OBSERVED ACCEL (a)", col2, y);

    ctx.font = "bold 16px 'JetBrains Mono', monospace";
    ctx.fillStyle = ACCEL_COLOR;
    ctx.fillText(`${displayAccel.toFixed(1)} m/s\u00B2`, col2, y + 18);

    // Accel indicator bar
    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(col2, y + 24, barW, barH);
    const accelFill = Math.min(1, this._accelA / 50) * barW;
    ctx.fillStyle = ACCEL_COLOR;
    ctx.globalAlpha = 0.6;
    ctx.fillRect(col2, y + 24, accelFill, barH);
    ctx.globalAlpha = 1.0;
  }

  _drawBalanceScale(ctx, isBalanced, isTight) {
    const cx = SCALE_CENTER_X;
    const py = SCALE_PIVOT_Y;
    const angle = this._scaleAngle;
    const armLen = SCALE_ARM_LEN;

    const scaleColor = isBalanced ? SCALE_BALANCED_COLOR : SCALE_COLOR;

    // Balanced glow background
    if (this._balanceGlow > 0) {
      const glowAlpha = this._balanceGlow * 0.08;
      ctx.fillStyle = `rgba(0, 255, 136, ${glowAlpha})`;
      ctx.beginPath();
      ctx.arc(cx, py, armLen + 30, 0, Math.PI * 2);
      ctx.fill();
    }

    // Pivot post
    ctx.strokeStyle = "#2a2a3a";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(cx, py);
    ctx.lineTo(cx, SCALE_BASE_Y);
    ctx.stroke();

    // Base
    ctx.fillStyle = "#2a2a3a";
    ctx.fillRect(cx - 30, SCALE_BASE_Y - 2, 60, 6);

    // Pivot triangle
    ctx.fillStyle = scaleColor;
    ctx.beginPath();
    ctx.moveTo(cx, py - 8);
    ctx.lineTo(cx - 6, py);
    ctx.lineTo(cx + 6, py);
    ctx.closePath();
    ctx.fill();

    // Scale arm (tilted by angle)
    const leftX = cx - Math.cos(angle) * armLen;
    const leftY = py - Math.sin(angle) * armLen;
    const rightX = cx + Math.cos(angle) * armLen;
    const rightY = py + Math.sin(angle) * armLen;

    ctx.strokeStyle = scaleColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(leftX, leftY);
    ctx.lineTo(rightX, rightY);
    ctx.stroke();

    // Left pan: Force (F)
    this._drawPan(ctx, leftX, leftY, FORCE_COLOR, "F", isBalanced);

    // Right pan: m x a
    this._drawPan(ctx, rightX, rightY, MASS_COLOR, "m\u00D7a", isBalanced);

    // "BALANCED" label when matched
    if (isBalanced) {
      ctx.font = "bold 10px 'JetBrains Mono', monospace";
      ctx.textAlign = "center";
      ctx.fillStyle = SCALE_BALANCED_COLOR;
      ctx.globalAlpha = 0.7 + Math.sin(this._pulsePhase * 3) * 0.3;
      const label = isTight ? "PRECISE MATCH" : "BALANCED";
      ctx.fillText(label, cx, py - 18);
      ctx.globalAlpha = 1.0;
    }

    // Estimated mass readout below scale
    ctx.font = "bold 11px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = MASS_COLOR;
    ctx.fillText(`Est. Mass: ${this._formatMass(this._estimatedMass)}`, cx, SCALE_BASE_Y + 18);
  }

  _drawPan(ctx, x, y, color, label, isBalanced) {
    const r = PAN_RADIUS;

    // Pan chains (vertical lines from arm to pan)
    ctx.strokeStyle = isBalanced ? SCALE_BALANCED_COLOR : "#3a3a4a";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x - r * 0.6, y);
    ctx.lineTo(x - r * 0.6, y + 15);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x + r * 0.6, y);
    ctx.lineTo(x + r * 0.6, y + 15);
    ctx.stroke();

    // Pan body (arc)
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.globalAlpha = 0.8;
    ctx.beginPath();
    ctx.arc(x, y + 15 + r * 0.3, r, Math.PI * 0.15, Math.PI * 0.85);
    ctx.stroke();
    ctx.globalAlpha = 1.0;

    // Label inside pan
    ctx.font = "bold 11px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = color;
    ctx.fillText(label, x, y + 15 + r * 0.5);
  }

  _drawShipClassSuggestions(ctx, isBalanced) {
    const y = SCALE_BASE_Y + 34;
    const mass = this._estimatedMass;

    ctx.font = "bold 7px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillStyle = DIM_COLOR;
    ctx.fillText("SHIP CLASS ESTIMATE", 12, y);

    // Draw class brackets
    const startX = 12;
    const bracketW = (CANVAS_W - 24) / SHIP_CLASSES.length;

    for (let i = 0; i < SHIP_CLASSES.length; i++) {
      const cls = SHIP_CLASSES[i];
      const bx = startX + i * bracketW;
      const isMatch = mass >= cls.min && mass < cls.max;

      // Background
      if (isMatch) {
        const alpha = isBalanced ? 0.2 : 0.08;
        ctx.fillStyle = `rgba(68, 136, 255, ${alpha})`;
        ctx.fillRect(bx, y + 4, bracketW - 2, 22);

        // Border
        ctx.strokeStyle = isBalanced ? SCALE_BALANCED_COLOR : MASS_COLOR;
        ctx.lineWidth = 1;
        ctx.strokeRect(bx, y + 4, bracketW - 2, 22);
      }

      // Class name
      ctx.font = "bold 7px 'JetBrains Mono', monospace";
      ctx.textAlign = "center";
      ctx.fillStyle = isMatch ? (isBalanced ? SCALE_BALANCED_COLOR : MASS_COLOR) : DIM_COLOR;
      ctx.fillText(cls.name.toUpperCase(), bx + bracketW / 2, y + 14);

      // Mass range
      ctx.font = "6px 'JetBrains Mono', monospace";
      ctx.fillStyle = DIM_COLOR;
      ctx.globalAlpha = 0.6;
      ctx.fillText(`${this._formatMassShort(cls.min)}-${this._formatMassShort(cls.max)}`, bx + bracketW / 2, y + 22);
      ctx.globalAlpha = 1.0;
    }
  }

  // --- Utility ---

  _formatForce(newtons) {
    if (newtons >= 1e6) return `${(newtons / 1e6).toFixed(1)} MN`;
    if (newtons >= 1e3) return `${(newtons / 1e3).toFixed(1)} kN`;
    return `${newtons.toFixed(0)} N`;
  }

  _formatMass(kg) {
    if (kg >= 1e6) return `${(kg / 1000).toFixed(0)} tons`;
    if (kg >= 1e3) return `${(kg / 1000).toFixed(1)} tons`;
    return `${kg.toFixed(0)} kg`;
  }

  _formatMassShort(kg) {
    if (kg >= 1e6) return `${(kg / 1000).toFixed(0)}t`;
    if (kg >= 1e3) return `${(kg / 1000).toFixed(0)}t`;
    return `${kg}kg`;
  }

  _hashString(str) {
    let hash = 5381;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0;
    }
    return Math.abs(hash);
  }

  _seededRandom(seed) {
    let s = seed;
    return () => {
      s = (s * 1664525 + 1013904223) & 0x7fffffff;
      return s / 0x7fffffff;
    };
  }

  // --- Render ---

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: none;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .mass-container {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 8px;
        }

        .game-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.65rem;
          color: ${LABEL_COLOR};
          text-transform: uppercase;
          letter-spacing: 0.1em;
        }

        .game-header .hint {
          color: ${DIM_COLOR};
          font-style: italic;
          font-size: 0.6rem;
        }

        #mass-canvas {
          border: 1px solid #2a2a3a;
          border-radius: 4px;
          width: 100%;
          max-width: ${CANVAS_W}px;
          aspect-ratio: ${CANVAS_W} / ${CANVAS_H};
          background: ${BG_COLOR};
        }

        .mass-slider-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 0 4px;
          font-size: 0.7rem;
        }

        .mass-slider-label {
          width: 90px;
          color: ${LABEL_COLOR};
          font-size: 0.65rem;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          flex-shrink: 0;
        }

        .mass-slider-value {
          width: 80px;
          text-align: right;
          color: ${MASS_COLOR};
          font-size: 0.7rem;
          font-weight: 600;
          flex-shrink: 0;
        }

        input[type="range"] {
          flex: 1;
          height: 6px;
          -webkit-appearance: none;
          appearance: none;
          background: linear-gradient(90deg, #1a1a2e 0%, #2a2a4e 50%, #1a1a2e 100%);
          border-radius: 3px;
          outline: none;
        }

        input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: ${MASS_COLOR};
          border: 2px solid #6699ff;
          cursor: pointer;
        }

        input[type="range"]::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: ${MASS_COLOR};
          border: 2px solid #6699ff;
          cursor: pointer;
        }

        .formula-hint {
          text-align: center;
          font-size: 0.6rem;
          color: ${DIM_COLOR};
          letter-spacing: 0.1em;
          padding: 2px 0;
        }
      </style>

      <div class="mass-container">
        <div class="game-header">
          <span>F = m \u00D7 a</span>
          <span class="hint">estimate contact mass</span>
        </div>

        <canvas id="mass-canvas" width="${CANVAS_W}" height="${CANVAS_H}"></canvas>

        <div class="mass-slider-row">
          <span class="mass-slider-label">Est. Mass</span>
          <input type="range" id="mass-slider" min="0" max="1000" value="500">
          <span class="mass-slider-value" id="mass-val">${this._formatMass(MASS_DEFAULT)}</span>
        </div>

        <div class="formula-hint">BALANCE THE SCALE: F should equal m \u00D7 a</div>
      </div>
    `;
  }
}

customElements.define("mass-estimation-game", MassEstimationGame);
