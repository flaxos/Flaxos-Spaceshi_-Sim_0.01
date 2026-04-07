/**
 * Hail Frequency Game (ARCADE tier)
 *
 * Tune a frequency dial through noise to find a contact's communication
 * channel. Like tuning an old radio — the static clears into a clean signal
 * as you approach the target frequency.
 *
 * State reads:
 *   sensor_contacts — picks a contact for hailing
 *   comms state if available
 *   Target frequency generated from contact ID hash if no real comms telemetry
 *
 * On signal lock (within +/-1 MHz for 2s): sends hail_contact command.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";
import { getDegradation } from "../js/minigame-difficulty.js";

// Tuning thresholds
const FREQ_RANGE = 999;          // 0-999 MHz
const ACQUIRED_RANGE = 5;        // +/- 5 MHz = "SIGNAL ACQUIRED"
const LOCK_RANGE = 1;            // +/- 1 MHz = locked on
const LOCK_HOLD_MS = 2000;       // hold lock for 2s to send command
const DIAL_SENSITIVITY = 0.4;    // degrees of dial per pixel of drag

class HailFrequencyGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._animFrame = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";

    // Game state
    this._currentFreq = 500;        // player's current frequency (0-999)
    this._targetFreq = 0;           // target frequency to find
    this._targetContactId = null;    // contact we're hailing
    this._targetContactName = null;
    this._signalStrength = 0;        // 0-1, computed from distance to target
    this._lockStart = 0;             // timestamp when lock began
    this._lockSent = false;          // whether we sent the hail command
    this._contacts = [];

    // Interaction state
    this._dragging = false;
    this._dragStartX = 0;
    this._dragStartFreq = 0;

    // Canvas refs
    this._canvas = null;
    this._ctx = null;
    this._waveCanvas = null;
    this._waveCtx = null;

    // Noise pixel buffer (pre-allocated for performance)
    this._noiseData = null;
  }

  connectedCallback() {
    this._render();
    this._canvas = this.shadowRoot.querySelector(".noise-canvas");
    this._ctx = this._canvas?.getContext("2d");
    this._waveCanvas = this.shadowRoot.querySelector(".waveform-canvas");
    this._waveCtx = this._waveCanvas?.getContext("2d");
    this._setupInteraction();
    this._subscribe();
    this._startLoop();

    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
    };
    document.addEventListener("tier-change", this._tierHandler);
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
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._readState();
    });
  }

  /** Read contacts and comms state from server telemetry */
  _readState() {
    const contacts = stateManager.getContacts() || [];
    this._contacts = contacts;

    // Pick first available contact for hailing (prefer one with a name)
    if (contacts.length > 0 && !this._targetContactId) {
      const named = contacts.find(c => c.name);
      const target = named || contacts[0];
      this._setTarget(target);
    }

    // If our current target disappeared, clear it
    if (this._targetContactId) {
      const stillExists = contacts.find(
        c => (c.contact_id || c.id) === this._targetContactId
      );
      if (!stillExists) {
        this._targetContactId = null;
        this._targetContactName = null;
        this._lockSent = false;
        this._lockStart = 0;
      }
    }

    this._updateContactSelector();
  }

  /** Set target contact and derive frequency from its ID */
  _setTarget(contact) {
    const id = contact.contact_id || contact.id || "unknown";
    if (id === this._targetContactId) return;

    this._targetContactId = id;
    this._targetContactName = contact.name || contact.classification || id;
    this._lockSent = false;
    this._lockStart = 0;

    // Derive target frequency from contact ID hash (deterministic)
    let hash = 0;
    for (let i = 0; i < id.length; i++) {
      hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
    }
    this._targetFreq = Math.abs(hash) % FREQ_RANGE;
  }

  /** Update the contact selector dropdown */
  _updateContactSelector() {
    const select = this.shadowRoot.querySelector(".contact-select");
    if (!select) return;

    const currentVal = select.value;
    const options = this._contacts.map(c => {
      const id = c.contact_id || c.id;
      const label = c.name || c.classification || id;
      return `<option value="${id}" ${id === this._targetContactId ? "selected" : ""}>${label}</option>`;
    });

    if (this._contacts.length === 0) {
      select.innerHTML = '<option value="">No contacts</option>';
    } else {
      select.innerHTML = options.join("");
    }
  }

  /** Compute signal strength based on distance to target frequency */
  _computeSignalStrength() {
    const dist = Math.abs(this._currentFreq - this._targetFreq);
    // Signal strength: 1.0 at target, falls off with distance
    // Gaussian-like falloff: full at 0, ~0 at 50+ MHz away
    const sigma = 25;
    this._signalStrength = Math.exp(-(dist * dist) / (2 * sigma * sigma));
  }

  /** Evaluate lock state */
  _evaluateLock() {
    const dist = Math.abs(this._currentFreq - this._targetFreq);
    const now = performance.now();

    if (dist <= LOCK_RANGE) {
      if (this._lockStart === 0) {
        this._lockStart = now;
      }
      // Send hail after sustained lock
      if (!this._lockSent && (now - this._lockStart) >= LOCK_HOLD_MS) {
        wsClient.sendShipCommand("hail_contact", {
          contact_id: this._targetContactId,
          frequency: Math.round(this._currentFreq),
        });
        this._lockSent = true;
      }
    } else {
      this._lockStart = 0;
    }
  }

  /** Get lock status string */
  _getLockStatus() {
    const dist = Math.abs(this._currentFreq - this._targetFreq);
    if (this._lockSent) return "HAIL SENT";
    if (dist <= LOCK_RANGE) return "LOCKED";
    if (dist <= ACQUIRED_RANGE) return "SIGNAL ACQUIRED";
    if (this._signalStrength > 0.3) return "SIGNAL DETECTED";
    return "SCANNING";
  }

  /** Main animation loop */
  _startLoop() {
    const loop = (timestamp) => {
      this._animFrame = requestAnimationFrame(loop);
      this._computeSignalStrength();
      this._evaluateLock();
      this._drawNoise(timestamp);
      this._drawWaveform(timestamp);
      this._updateVisuals();
    };
    this._animFrame = requestAnimationFrame(loop);
  }

  /** Draw static noise on the background canvas — clears as signal strengthens */
  _drawNoise(timestamp) {
    const canvas = this._canvas;
    const ctx = this._ctx;
    if (!canvas || !ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    // Comms damage amplifies noise
    const dmg = getDegradation("comms");
    const noiseLevel = (1 - this._signalStrength * 0.85) * (1 + dmg * 2);

    ctx.fillStyle = "#080812";
    ctx.fillRect(0, 0, w, h);

    // Random bright pixels (static noise)
    const pixelCount = Math.floor(w * h * 0.04 * noiseLevel);
    for (let i = 0; i < pixelCount; i++) {
      const x = Math.random() * w;
      const y = Math.random() * h;
      const brightness = Math.floor(40 + Math.random() * 80 * noiseLevel);
      ctx.fillStyle = `rgba(${brightness}, ${brightness + 10}, ${brightness + 30}, ${0.3 + Math.random() * 0.4})`;
      ctx.fillRect(x, y, 1, 1);
    }

    // Occasional horizontal scan line artifact
    if (Math.random() < 0.08 * noiseLevel) {
      const y = Math.random() * h;
      ctx.fillStyle = `rgba(100, 120, 160, ${0.1 * noiseLevel})`;
      ctx.fillRect(0, y, w, 1 + Math.random() * 2);
    }
  }

  /** Draw waveform: from noise (jagged random) to clean sine wave */
  _drawWaveform(timestamp) {
    const canvas = this._waveCanvas;
    const ctx = this._waveCtx;
    if (!canvas || !ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    const mid = h / 2;
    const strength = this._signalStrength;

    ctx.clearRect(0, 0, w, h);

    // Center line
    ctx.strokeStyle = "rgba(40, 50, 70, 0.3)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(w, mid);
    ctx.stroke();

    // Waveform: blend between noise and clean sine
    const sineFreq = 0.05;
    const sineAmp = (h / 2) * 0.7;
    const t = timestamp * 0.003;

    ctx.strokeStyle = strength > 0.8
      ? `rgba(68, 255, 136, ${0.6 + strength * 0.4})`
      : `rgba(68, 136, 255, ${0.4 + strength * 0.4})`;
    ctx.lineWidth = 1.5;
    ctx.beginPath();

    for (let x = 0; x < w; x++) {
      // Clean sine component
      const sine = Math.sin(x * sineFreq + t) * sineAmp * strength;
      // Noise component
      const noise = (Math.random() - 0.5) * sineAmp * 2 * (1 - strength);
      const y = mid + sine + noise;

      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Glow effect when signal is strong
    if (strength > 0.6) {
      ctx.strokeStyle = `rgba(68, 255, 136, ${(strength - 0.6) * 0.3})`;
      ctx.lineWidth = 4;
      ctx.stroke();
    }
  }

  /** Update DOM elements (status, dial position, signal meter) */
  _updateVisuals() {
    const status = this._getLockStatus();
    const statusEl = this.shadowRoot.querySelector(".lock-status");
    const statusDot = this.shadowRoot.querySelector(".lock-dot");
    const freqReadout = this.shadowRoot.querySelector(".freq-readout");
    const strengthFill = this.shadowRoot.querySelector(".strength-fill");
    const dialPointer = this.shadowRoot.querySelector(".dial-pointer");
    const lockProgress = this.shadowRoot.querySelector(".lock-progress");
    const targetLabel = this.shadowRoot.querySelector(".target-label");

    if (statusEl) statusEl.textContent = status;
    if (statusDot) {
      statusDot.className = "lock-dot";
      if (status === "HAIL SENT") statusDot.classList.add("sent");
      else if (status === "LOCKED") statusDot.classList.add("locked");
      else if (status === "SIGNAL ACQUIRED") statusDot.classList.add("acquired");
      else if (status === "SIGNAL DETECTED") statusDot.classList.add("detected");
      else statusDot.classList.add("scanning");
    }

    if (freqReadout) {
      freqReadout.textContent = `${Math.round(this._currentFreq)} MHz`;
    }

    if (strengthFill) {
      strengthFill.style.height = `${this._signalStrength * 100}%`;
      const hue = this._signalStrength > 0.8 ? 140 : 220;
      strengthFill.style.background = `linear-gradient(0deg, hsl(${hue}, 70%, 30%), hsl(${hue}, 80%, 50%))`;
    }

    // Dial rotation: 0-999 maps to 0-300 degrees
    if (dialPointer) {
      const deg = (this._currentFreq / FREQ_RANGE) * 300 - 150;
      dialPointer.style.transform = `rotate(${deg}deg)`;
    }

    // Lock progress bar
    if (lockProgress) {
      const dist = Math.abs(this._currentFreq - this._targetFreq);
      if (dist <= LOCK_RANGE && this._lockStart > 0 && !this._lockSent) {
        const elapsed = performance.now() - this._lockStart;
        const pct = Math.min(1, elapsed / LOCK_HOLD_MS) * 100;
        lockProgress.style.width = `${pct}%`;
        lockProgress.style.opacity = "1";
      } else if (this._lockSent) {
        lockProgress.style.width = "100%";
        lockProgress.style.opacity = "1";
      } else {
        lockProgress.style.width = "0%";
        lockProgress.style.opacity = "0.3";
      }
    }

    if (targetLabel) {
      targetLabel.textContent = this._targetContactName || "No target";
    }
  }

  /** Set up mouse/touch interaction for dial dragging */
  _setupInteraction() {
    const dialArea = this.shadowRoot.querySelector(".dial-area");
    if (!dialArea) return;

    const startDrag = (clientX) => {
      this._dragging = true;
      this._dragStartX = clientX;
      this._dragStartFreq = this._currentFreq;
    };

    const updateDrag = (clientX) => {
      if (!this._dragging) return;
      const dx = clientX - this._dragStartX;
      const freqDelta = dx * DIAL_SENSITIVITY;
      this._currentFreq = Math.max(0, Math.min(FREQ_RANGE, this._dragStartFreq + freqDelta));
      // Reset lock state when moving
      if (Math.abs(freqDelta) > LOCK_RANGE) {
        this._lockSent = false;
      }
    };

    const stopDrag = () => {
      this._dragging = false;
    };

    // Mouse
    dialArea.addEventListener("mousedown", (e) => {
      e.preventDefault();
      startDrag(e.clientX);
    });
    // Listen on window so dragging works even when cursor leaves the dial
    window.addEventListener("mousemove", (e) => updateDrag(e.clientX));
    window.addEventListener("mouseup", stopDrag);

    // Touch
    dialArea.addEventListener("touchstart", (e) => {
      e.preventDefault();
      startDrag(e.touches[0].clientX);
    });
    dialArea.addEventListener("touchmove", (e) => {
      e.preventDefault();
      updateDrag(e.touches[0].clientX);
    });
    dialArea.addEventListener("touchend", stopDrag);
    dialArea.addEventListener("touchcancel", stopDrag);

    // Contact selector change
    const select = this.shadowRoot.querySelector(".contact-select");
    if (select) {
      select.addEventListener("change", (e) => {
        const id = e.target.value;
        const contact = this._contacts.find(c => (c.contact_id || c.id) === id);
        if (contact) {
          this._setTarget(contact);
        }
      });
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

        .hail-game-root {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 12px;
        }

        /* --- Header row: target select + status --- */
        .header-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .target-label {
          font-size: 0.7rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: #99a;
          font-weight: 600;
          flex-shrink: 0;
        }

        .contact-select {
          flex: 1;
          background: #0a0a14;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          color: #aab;
          font-size: 0.7rem;
          padding: 3px 6px;
          font-family: inherit;
        }

        .lock-status-row {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .lock-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #334;
          transition: background 0.2s, box-shadow 0.2s;
        }
        .lock-dot.sent {
          background: #0f0;
          box-shadow: 0 0 12px rgba(0, 255, 0, 0.8);
          animation: pulse-green 0.6s ease-in-out infinite alternate;
        }
        .lock-dot.locked {
          background: #0f0;
          box-shadow: 0 0 6px rgba(0, 255, 0, 0.5);
        }
        .lock-dot.acquired {
          background: #fc0;
          box-shadow: 0 0 6px rgba(255, 200, 0, 0.5);
        }
        .lock-dot.detected {
          background: #48f;
          box-shadow: 0 0 6px rgba(68, 136, 255, 0.5);
        }
        .lock-dot.scanning {
          background: #445;
        }

        @keyframes pulse-green {
          from { box-shadow: 0 0 8px rgba(0, 255, 0, 0.6); }
          to   { box-shadow: 0 0 20px rgba(0, 255, 0, 1.0); }
        }

        .lock-status {
          font-size: 0.7rem;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: #99a;
          font-weight: 600;
        }

        /* --- Lock progress bar --- */
        .lock-progress-track {
          height: 3px;
          background: #0a0a14;
          border-radius: 2px;
          overflow: hidden;
        }

        .lock-progress {
          height: 100%;
          width: 0%;
          background: linear-gradient(90deg, #0a4, #0f0);
          border-radius: 2px;
          transition: width 0.1s linear, opacity 0.3s;
          opacity: 0.3;
        }

        /* --- Main game area: dial + noise + meter --- */
        .game-area {
          display: flex;
          gap: 10px;
          align-items: stretch;
        }

        .dial-column {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        /* --- Noise canvas (static visualization) --- */
        .noise-canvas {
          width: 100%;
          height: 60px;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          display: block;
        }

        /* --- Dial area --- */
        .dial-area {
          position: relative;
          height: 100px;
          background: #060610;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          cursor: ew-resize;
          user-select: none;
          touch-action: none;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
        }

        .dial-circle {
          width: 80px;
          height: 80px;
          border-radius: 50%;
          border: 2px solid #2a2a3e;
          position: relative;
          background: radial-gradient(circle, #0e0e1a 0%, #060610 100%);
        }

        .dial-pointer {
          position: absolute;
          top: 4px;
          left: 50%;
          width: 2px;
          height: 36px;
          margin-left: -1px;
          background: linear-gradient(to bottom, #4488ff, transparent);
          border-radius: 1px;
          transform-origin: bottom center;
          box-shadow: 0 0 6px rgba(68, 136, 255, 0.4);
          transition: transform 0.05s linear;
        }

        .dial-center-dot {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 6px;
          height: 6px;
          margin: -3px 0 0 -3px;
          border-radius: 50%;
          background: #4488ff;
          box-shadow: 0 0 4px rgba(68, 136, 255, 0.6);
        }

        /* Tick marks around dial */
        .dial-ticks {
          position: absolute;
          inset: 0;
          pointer-events: none;
        }

        .dial-tick {
          position: absolute;
          width: 1px;
          height: 6px;
          background: #334;
          top: 0;
          left: 50%;
          transform-origin: bottom center;
        }

        .dial-tick.major {
          height: 10px;
          background: #556;
          width: 2px;
        }

        /* Frequency readout */
        .freq-readout {
          text-align: center;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 1.1rem;
          color: #aab;
          letter-spacing: 0.08em;
        }

        .freq-hint {
          text-align: center;
          font-size: 0.55rem;
          color: #445;
          text-transform: uppercase;
          letter-spacing: 0.1em;
        }

        /* --- Waveform canvas --- */
        .waveform-canvas {
          width: 100%;
          height: 48px;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          display: block;
        }

        /* --- Signal strength meter (vertical) --- */
        .strength-meter {
          width: 24px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          flex-shrink: 0;
        }

        .strength-label {
          font-size: 0.5rem;
          letter-spacing: 0.08em;
          color: #556;
          text-transform: uppercase;
          writing-mode: vertical-lr;
          text-orientation: mixed;
          transform: rotate(180deg);
        }

        .strength-track {
          flex: 1;
          width: 10px;
          background: #0a0a14;
          border: 1px solid #1a1a2e;
          border-radius: 2px;
          position: relative;
          overflow: hidden;
          min-height: 100px;
        }

        .strength-fill {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 0%;
          background: linear-gradient(0deg, #234, #48f);
          border-radius: 0 0 1px 1px;
          transition: height 0.15s ease;
        }

        /* --- Idle state --- */
        .idle-state {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 80px;
          color: #445;
          font-size: 0.75rem;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          border: 1px dashed #1a1a2e;
          border-radius: 3px;
        }

        .idle-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #334;
          margin-right: 8px;
        }
      </style>

      <div class="hail-game-root">
        <!-- Idle state: no contacts available -->
        <div class="idle-state" style="display: none;">
          <span class="idle-dot"></span>
          NO CONTACTS IN RANGE
        </div>

        <!-- Active game -->
        <div class="game-active">
          <!-- Header: target selection -->
          <div class="header-row">
            <span class="target-label">HAIL:</span>
            <select class="contact-select">
              <option value="">No contacts</option>
            </select>
          </div>

          <!-- Lock status -->
          <div class="lock-status-row">
            <span class="lock-dot scanning"></span>
            <span class="lock-status">SCANNING</span>
          </div>

          <!-- Lock progress bar -->
          <div class="lock-progress-track">
            <div class="lock-progress"></div>
          </div>

          <!-- Main game area -->
          <div class="game-area">
            <div class="dial-column">
              <!-- Static noise visualization -->
              <canvas class="noise-canvas" width="300" height="60"></canvas>

              <!-- Frequency dial -->
              <div class="dial-area">
                <div class="dial-circle">
                  <div class="dial-ticks"></div>
                  <div class="dial-pointer"></div>
                  <div class="dial-center-dot"></div>
                </div>
              </div>

              <!-- Frequency readout -->
              <div class="freq-readout">500 MHz</div>
              <div class="freq-hint">drag to tune</div>

              <!-- Waveform: noise to clean signal -->
              <canvas class="waveform-canvas" width="300" height="48"></canvas>
            </div>

            <!-- Signal strength meter -->
            <div class="strength-meter">
              <div class="strength-track">
                <div class="strength-fill"></div>
              </div>
              <span class="strength-label">SIG</span>
            </div>
          </div>
        </div>
      </div>
    `;

    // Generate tick marks on the dial
    const ticks = this.shadowRoot.querySelector(".dial-ticks");
    if (ticks) {
      for (let i = 0; i < 20; i++) {
        const deg = (i / 20) * 300 - 150;
        const tick = document.createElement("div");
        tick.className = i % 5 === 0 ? "dial-tick major" : "dial-tick";
        // Position tick at the edge of the circle using transform
        tick.style.transform = `rotate(${deg}deg) translateY(0px)`;
        tick.style.transformOrigin = "50% 40px";
        ticks.appendChild(tick);
      }
    }
  }
}

customElements.define("hail-frequency-game", HailFrequencyGame);
