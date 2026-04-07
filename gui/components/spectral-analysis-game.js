/**
 * Spectral Analysis Game (ARCADE tier)
 *
 * Puzzle mini-game for the Science station. The player adjusts three sensor
 * filter sliders (IR Band, EM Frequency, RCS Sensitivity) to match an
 * unknown contact's emission spectrum. Better match = higher classification
 * confidence sent to the server.
 *
 * The game reads sensor_contacts from stateManager and picks the currently
 * selected/locked contact. If no contact is available, it generates a
 * procedural waveform for practice mode.
 *
 * State reads:
 *   sensor_contacts — array of contact objects
 *   targeting.designated_target or targeting.locked_target — selected contact
 *
 * Commands sent:
 *   analyze_contact { contact_id, confidence_boost } — on match >80%
 *
 * Visible only in ARCADE tier (Science view).
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getDegradation } from "../js/minigame-difficulty.js";

// Canvas dimensions
const CANVAS_W = 400;
const CANVAS_H = 260;

// Waveform parameters
const WAVE_POINTS = 128;         // resolution of waveform
const WAVE_Y_TOP = 20;           // top waveform y offset
const WAVE_Y_BOT = 150;          // bottom waveform y offset
const WAVE_HEIGHT = 50;          // waveform amplitude in px
const WAVE_X_PAD = 20;           // left/right padding

// Match thresholds
const MATCH_SEND_THRESHOLD = 0.80;  // 80% match triggers command
const CMD_COOLDOWN_MS = 3000;       // don't spam analyze commands

// Colors
const BG_COLOR = "#0a0a14";
const GRID_COLOR = "#1a1a2a";
const TARGET_WAVE_COLOR = "#ff8800";
const PLAYER_WAVE_COLOR = "#4488ff";
const MATCH_GOOD_COLOR = "#00ff88";
const MATCH_MED_COLOR = "#ffcc00";
const MATCH_LOW_COLOR = "#ff4444";
const LABEL_COLOR = "#6688cc";
const DIM_COLOR = "#445577";

class SpectralAnalysisGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    // Slider values (0-100)
    this._irBand = 50;
    this._emFreq = 50;
    this._rcsSens = 50;

    // Target waveform (generated from contact data or procedural)
    this._targetWave = null;
    this._targetContactId = null;

    // Match state
    this._matchPercent = 0;
    this._lastCmdTime = 0;
    this._matchSent = false; // whether we sent a command for this contact

    // Animation
    this._animFrame = null;
    this._lastFrameTime = 0;
    this._pulsePhase = 0; // for subtle animation on match indicator

    // Subscriptions
    this._unsubscribe = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";

    // Canvas ref
    this._canvas = null;
    this._ctx = null;

    // Bound handlers
    this._boundFrame = this._frame.bind(this);
    this._boundSliderInput = this._onSliderInput.bind(this);
  }

  connectedCallback() {
    this._render();
    this._canvas = this.shadowRoot.getElementById("spectral-canvas");
    this._ctx = this._canvas.getContext("2d");

    // Wire up sliders
    this.shadowRoot.querySelectorAll("input[type=range]").forEach(s => {
      s.addEventListener("input", this._boundSliderInput);
    });

    // State subscription
    this._unsubscribe = stateManager.subscribe("*", () => this._onStateUpdate());

    // Tier change
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._updateVisibility();
    };
    document.addEventListener("tier-change", this._tierHandler);

    // Initial update
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
    this._updateTargetWaveform();
  }

  _updateVisibility() {
    const isArcade = this._tier === "arcade";
    this.style.display = isArcade ? "block" : "none";
  }

  /**
   * Pick the best contact to analyze and generate its waveform.
   * Uses targeting data to find the selected contact, falls back to
   * the first sensor contact, or generates a procedural practice waveform.
   */
  _updateTargetWaveform() {
    const targeting = stateManager.getTargeting();
    const contacts = stateManager.getContacts() || [];
    const selectedId = targeting?.designated_target || targeting?.locked_target || targeting?.target_id;

    // Find the selected contact object
    let contact = null;
    if (selectedId && contacts.length > 0) {
      contact = contacts.find(c => (c.contact_id || c.id) === selectedId);
    }
    if (!contact && contacts.length > 0) {
      contact = contacts[0];
    }

    const contactId = contact ? (contact.contact_id || contact.id) : null;

    // If contact changed, regenerate waveform and reset match state
    if (contactId !== this._targetContactId) {
      this._targetContactId = contactId;
      this._targetWave = this._generateWaveform(contact);
      this._matchSent = false;
      // Don't reset sliders — let the player keep their position
    }
  }

  /**
   * Generate a deterministic waveform from contact data.
   * Uses a hash of the contact's classification/name/id to seed
   * the waveform shape, so the same contact always produces the
   * same puzzle. If no contact, generates a random practice waveform.
   */
  _generateWaveform(contact) {
    const wave = new Float32Array(WAVE_POINTS);

    // Seed from contact data for deterministic waveform
    let seed;
    if (contact) {
      const seedStr = (contact.classification || "") + (contact.name || "") + (contact.contact_id || contact.id || "");
      seed = this._hashString(seedStr);
    } else {
      // Practice mode: random seed, changes every 30 seconds
      seed = Math.floor(Date.now() / 30000);
    }

    // Generate waveform as sum of sinusoids with seeded parameters
    // Three frequency bands corresponding to IR, EM, RCS
    const rng = this._seededRandom(seed);
    const irTarget = rng() * 100;      // target IR band value
    const emTarget = rng() * 100;      // target EM freq value
    const rcsTarget = rng() * 100;     // target RCS sensitivity value

    // Store target values for match calculation
    this._targetIR = irTarget;
    this._targetEM = emTarget;
    this._targetRCS = rcsTarget;

    // Build the waveform from the target parameters
    for (let i = 0; i < WAVE_POINTS; i++) {
      const t = i / WAVE_POINTS;
      // Low frequency (IR band contribution)
      wave[i] += Math.sin(t * Math.PI * 2 * (1 + irTarget / 25)) * (0.3 + irTarget / 200);
      // Mid frequency (EM contribution)
      wave[i] += Math.sin(t * Math.PI * 2 * (3 + emTarget / 20)) * (0.2 + emTarget / 250);
      // High frequency (RCS contribution)
      wave[i] += Math.sin(t * Math.PI * 2 * (7 + rcsTarget / 15)) * (0.15 + rcsTarget / 300);
      // Add some noise for visual interest
      wave[i] += (rng() - 0.5) * 0.1;
    }

    return wave;
  }

  /**
   * Build the player's waveform from current slider positions.
   * Uses the same formula as _generateWaveform but with player values.
   */
  _buildPlayerWave() {
    const wave = new Float32Array(WAVE_POINTS);
    const ir = this._irBand;
    const em = this._emFreq;
    const rcs = this._rcsSens;

    for (let i = 0; i < WAVE_POINTS; i++) {
      const t = i / WAVE_POINTS;
      wave[i] += Math.sin(t * Math.PI * 2 * (1 + ir / 25)) * (0.3 + ir / 200);
      wave[i] += Math.sin(t * Math.PI * 2 * (3 + em / 20)) * (0.2 + em / 250);
      wave[i] += Math.sin(t * Math.PI * 2 * (7 + rcs / 15)) * (0.15 + rcs / 300);
    }

    return wave;
  }

  /**
   * Calculate match quality between target and player waveforms.
   * Returns 0.0 (no match) to 1.0 (perfect match).
   */
  _calculateMatch(targetWave, playerWave) {
    if (!targetWave || !playerWave) return 0;

    let totalError = 0;
    let maxAmplitude = 0;

    for (let i = 0; i < WAVE_POINTS; i++) {
      const diff = Math.abs(targetWave[i] - playerWave[i]);
      totalError += diff;
      maxAmplitude = Math.max(maxAmplitude, Math.abs(targetWave[i]));
    }

    // Normalize: perfect match = 0 error, worst case = large error
    const avgError = totalError / WAVE_POINTS;
    const maxPossibleError = maxAmplitude * 2 + 0.5;
    const match = Math.max(0, 1.0 - avgError / maxPossibleError);
    return match;
  }

  // --- Input ---

  _onSliderInput() {
    const ir = this.shadowRoot.getElementById("slider-ir");
    const em = this.shadowRoot.getElementById("slider-em");
    const rcs = this.shadowRoot.getElementById("slider-rcs");

    this._irBand = ir ? Number(ir.value) : 50;
    this._emFreq = em ? Number(em.value) : 50;
    this._rcsSens = rcs ? Number(rcs.value) : 50;

    // Update value displays
    const irVal = this.shadowRoot.getElementById("val-ir");
    const emVal = this.shadowRoot.getElementById("val-em");
    const rcsVal = this.shadowRoot.getElementById("val-rcs");
    if (irVal) irVal.textContent = this._irBand;
    if (emVal) emVal.textContent = this._emFreq;
    if (rcsVal) rcsVal.textContent = this._rcsSens;
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

    // Sensor damage causes target waveform drift
    const dmg = getDegradation("sensors");
    if (dmg > 0 && this._targetWave) {
      this._targetDrift = (this._targetDrift || 0) + (Math.random() - 0.5) * dmg * 0.02;
      for (let i = 0; i < this._targetWave.length; i++) {
        this._targetWave[i] += this._targetDrift * 0.01;
      }
    }

    // Build player waveform from current slider values
    const playerWave = this._buildPlayerWave();

    // Calculate match
    this._matchPercent = this._calculateMatch(this._targetWave, playerWave);

    // Send command on good match (with cooldown)
    if (this._matchPercent >= MATCH_SEND_THRESHOLD && !this._matchSent &&
        this._targetContactId && timestamp - this._lastCmdTime > CMD_COOLDOWN_MS) {
      this._lastCmdTime = timestamp;
      this._matchSent = true;
      const boost = Math.round(this._matchPercent * 100);
      wsClient.sendShipCommand("analyze_contact", {
        contact_id: this._targetContactId,
        confidence_boost: boost
      }).catch(() => {
        // Best-effort: silently ignore failures
      });
    }

    // Reset matchSent if player moves sliders away from match
    if (this._matchPercent < MATCH_SEND_THRESHOLD * 0.9) {
      this._matchSent = false;
    }

    // Draw
    this._draw(playerWave);

    this._animFrame = requestAnimationFrame(this._boundFrame);
  }

  // --- Drawing ---

  _draw(playerWave) {
    const ctx = this._ctx;
    if (!ctx) return;
    const w = CANVAS_W;
    const h = CANVAS_H;

    // Clear
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, w, h);

    // Grid lines
    ctx.strokeStyle = GRID_COLOR;
    ctx.lineWidth = 0.5;
    for (let x = WAVE_X_PAD; x < w - WAVE_X_PAD; x += 30) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }

    // Divider line between top and bottom waveforms
    const dividerY = (WAVE_Y_TOP + WAVE_HEIGHT + WAVE_Y_BOT) / 2 + 15;
    ctx.strokeStyle = "#2a2a3a";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(WAVE_X_PAD, dividerY);
    ctx.lineTo(w - WAVE_X_PAD, dividerY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Labels
    ctx.font = "bold 9px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";

    // Top label
    ctx.fillStyle = TARGET_WAVE_COLOR;
    ctx.fillText("UNKNOWN CONTACT SIGNATURE", WAVE_X_PAD, WAVE_Y_TOP - 5);

    // Contact info (right-aligned)
    ctx.textAlign = "right";
    ctx.fillStyle = DIM_COLOR;
    if (this._targetContactId) {
      ctx.fillText(`[${this._targetContactId}]`, w - WAVE_X_PAD, WAVE_Y_TOP - 5);
    } else {
      ctx.fillText("[PRACTICE MODE]", w - WAVE_X_PAD, WAVE_Y_TOP - 5);
    }

    // Bottom label
    ctx.textAlign = "left";
    ctx.fillStyle = PLAYER_WAVE_COLOR;
    ctx.fillText("YOUR FILTER CONFIGURATION", WAVE_X_PAD, WAVE_Y_BOT - 5);

    // Draw target waveform (top)
    if (this._targetWave) {
      this._drawWaveform(ctx, this._targetWave, WAVE_Y_TOP, TARGET_WAVE_COLOR, 0.9);
    }

    // Draw player waveform (bottom)
    if (playerWave) {
      this._drawWaveform(ctx, playerWave, WAVE_Y_BOT, PLAYER_WAVE_COLOR, 0.9);
    }

    // Match indicator
    this._drawMatchIndicator(ctx);
  }

  _drawWaveform(ctx, wave, yCenter, color, alpha) {
    const xStart = WAVE_X_PAD;
    const xEnd = CANVAS_W - WAVE_X_PAD;
    const xRange = xEnd - xStart;

    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = alpha;
    ctx.beginPath();

    for (let i = 0; i < WAVE_POINTS; i++) {
      const x = xStart + (i / (WAVE_POINTS - 1)) * xRange;
      const y = yCenter + wave[i] * WAVE_HEIGHT;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();

    // Subtle glow effect (draw again with blur)
    ctx.globalAlpha = alpha * 0.3;
    ctx.lineWidth = 4;
    ctx.stroke();

    ctx.globalAlpha = 1.0;
    ctx.lineWidth = 1;
  }

  _drawMatchIndicator(ctx) {
    const pct = Math.round(this._matchPercent * 100);
    const x = CANVAS_W - WAVE_X_PAD;
    const y = CANVAS_H - 20;

    // Pick color based on match quality
    let color;
    if (this._matchPercent >= MATCH_SEND_THRESHOLD) {
      color = MATCH_GOOD_COLOR;
    } else if (this._matchPercent >= 0.5) {
      color = MATCH_MED_COLOR;
    } else {
      color = MATCH_LOW_COLOR;
    }

    // Pulsing glow when matched
    let extraAlpha = 0;
    if (this._matchPercent >= MATCH_SEND_THRESHOLD) {
      extraAlpha = 0.15 + Math.sin(this._pulsePhase * 3) * 0.1;
      // Draw glow rectangle behind text
      ctx.fillStyle = `rgba(0, 255, 136, ${extraAlpha})`;
      ctx.fillRect(x - 120, y - 12, 125, 18);
    }

    // Match percentage text
    ctx.font = "bold 11px 'JetBrains Mono', monospace";
    ctx.textAlign = "right";
    ctx.fillStyle = color;
    ctx.fillText(`MATCH ${pct}%`, x, y);

    // "ANALYZING..." flash when command was sent
    if (this._matchSent) {
      ctx.font = "bold 9px 'JetBrains Mono', monospace";
      ctx.fillStyle = MATCH_GOOD_COLOR;
      ctx.globalAlpha = 0.5 + Math.sin(this._pulsePhase * 4) * 0.3;
      ctx.fillText("ANALYZING...", x, y + 14);
      ctx.globalAlpha = 1.0;
    }

    // Match bar (bottom-left)
    const barX = WAVE_X_PAD;
    const barY = CANVAS_H - 18;
    const barW = 150;
    const barH = 6;

    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(barX, barY, barW, barH);
    ctx.strokeStyle = "#2a2a3a";
    ctx.lineWidth = 1;
    ctx.strokeRect(barX, barY, barW, barH);

    const fillW = barW * Math.min(1, this._matchPercent);
    if (fillW > 0) {
      ctx.fillStyle = color;
      ctx.fillRect(barX + 1, barY + 1, fillW - 2, barH - 2);
    }

    ctx.font = "7px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillStyle = DIM_COLOR;
    ctx.fillText("CONFIDENCE", barX, barY - 3);
  }

  // --- Utility ---

  /** Simple string hash for deterministic waveform generation */
  _hashString(str) {
    let hash = 5381;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0;
    }
    return Math.abs(hash);
  }

  /** Seeded pseudo-random number generator (LCG) */
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

        .spectral-container {
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

        #spectral-canvas {
          border: 1px solid #2a2a3a;
          border-radius: 4px;
          width: 100%;
          max-width: ${CANVAS_W}px;
          aspect-ratio: ${CANVAS_W} / ${CANVAS_H};
          background: ${BG_COLOR};
        }

        .sliders {
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 0 4px;
        }

        .slider-row {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.7rem;
        }

        .slider-label {
          width: 90px;
          color: ${LABEL_COLOR};
          font-size: 0.65rem;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          flex-shrink: 0;
        }

        .slider-value {
          width: 28px;
          text-align: right;
          color: ${DIM_COLOR};
          font-size: 0.65rem;
          flex-shrink: 0;
        }

        input[type="range"] {
          flex: 1;
          height: 4px;
          -webkit-appearance: none;
          appearance: none;
          background: #1a1a2e;
          border-radius: 2px;
          outline: none;
        }

        input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: #4488ff;
          border: 2px solid #6699ff;
          cursor: pointer;
        }

        input[type="range"]::-moz-range-thumb {
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: #4488ff;
          border: 2px solid #6699ff;
          cursor: pointer;
        }

        /* Color-code each slider for visual clarity */
        .slider-ir input[type="range"]::-webkit-slider-thumb { background: #ff4444; border-color: #ff6666; }
        .slider-ir input[type="range"]::-moz-range-thumb { background: #ff4444; border-color: #ff6666; }
        .slider-em input[type="range"]::-webkit-slider-thumb { background: #ffcc00; border-color: #ffdd44; }
        .slider-em input[type="range"]::-moz-range-thumb { background: #ffcc00; border-color: #ffdd44; }
        .slider-rcs input[type="range"]::-webkit-slider-thumb { background: #00ccff; border-color: #44ddff; }
        .slider-rcs input[type="range"]::-moz-range-thumb { background: #00ccff; border-color: #44ddff; }
      </style>

      <div class="spectral-container">
        <div class="game-header">
          <span>SPECTRAL ANALYSIS</span>
          <span class="hint">tune filters to match signature</span>
        </div>

        <canvas id="spectral-canvas" width="${CANVAS_W}" height="${CANVAS_H}"></canvas>

        <div class="sliders">
          <div class="slider-row slider-ir">
            <span class="slider-label">IR Band</span>
            <input type="range" id="slider-ir" min="0" max="100" value="50">
            <span class="slider-value" id="val-ir">50</span>
          </div>
          <div class="slider-row slider-em">
            <span class="slider-label">EM Frequency</span>
            <input type="range" id="slider-em" min="0" max="100" value="50">
            <span class="slider-value" id="val-em">50</span>
          </div>
          <div class="slider-row slider-rcs">
            <span class="slider-label">RCS Sensitivity</span>
            <input type="range" id="slider-rcs" min="0" max="100" value="50">
            <span class="slider-value" id="val-rcs">50</span>
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define("spectral-analysis-game", SpectralAnalysisGame);
