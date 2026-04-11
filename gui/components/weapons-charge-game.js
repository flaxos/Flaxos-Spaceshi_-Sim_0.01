/**
 * Weapons Charge Game (ARCADE tier)
 *
 * Timing mini-game for railgun firing. The capacitor charges on a curve —
 * hit FIRE at peak charge for maximum muzzle velocity. Fire too early = weak
 * shot. Wait too long = capacitor overheats and resets without firing.
 *
 * Reads from stateManager weapon telemetry (charge_state, charge_progress).
 * Fire command is server-authoritative — this panel is UX feedback only.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getDegradation } from "../js/minigame-difficulty.js";

const SWEET_SPOT_MIN = 0.75;
const SWEET_SPOT_MAX = 0.90;
const GOOD_ZONE_MIN = 0.50;
const FEEDBACK_DURATION_MS = 1500;

class WeaponsChargeGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._lastFeedback = null; // "PERFECT" | "GOOD" | "WEAK" | "OVERHEAT"
    this._feedbackTimer = null;
    this._chargeProgress = 0;
    this._chargeState = "idle";
    this._railgunMountId = null;
    this._hasSolution = false;
  }

  connectedCallback() {
    this._render();
    this._setupListeners();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._feedbackTimer) {
      clearTimeout(this._feedbackTimer);
      this._feedbackTimer = null;
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

        .charge-container {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 12px;
        }

        .charge-label {
          font-size: 0.7rem;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          color: #667;
          font-weight: 600;
        }

        .charge-label .mount-id {
          color: #99a;
          font-weight: 400;
          margin-left: 6px;
        }

        /* --- Charge bar --- */
        .charge-bar-wrapper {
          position: relative;
          height: 32px;
          border-radius: 3px;
          overflow: hidden;
        }

        .charge-bar-bg {
          position: absolute;
          inset: 0;
          background: #0a0a14;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
        }

        /* Sweet spot highlight zone (75%-90%) */
        .sweet-spot {
          position: absolute;
          top: 0;
          bottom: 0;
          left: ${SWEET_SPOT_MIN * 100}%;
          width: ${(SWEET_SPOT_MAX - SWEET_SPOT_MIN) * 100}%;
          background: rgba(0, 255, 100, 0.06);
          border-left: 1px dashed rgba(0, 255, 100, 0.3);
          border-right: 1px dashed rgba(0, 255, 100, 0.3);
          z-index: 1;
          pointer-events: none;
        }

        .sweet-spot-label {
          position: absolute;
          top: 2px;
          left: 50%;
          transform: translateX(-50%);
          font-size: 0.55rem;
          color: rgba(0, 255, 100, 0.4);
          letter-spacing: 0.1em;
          text-transform: uppercase;
          white-space: nowrap;
        }

        /* Overheat zone (90%-100%) */
        .overheat-zone {
          position: absolute;
          top: 0;
          bottom: 0;
          left: 90%;
          width: 10%;
          z-index: 1;
          pointer-events: none;
        }

        .overheat-zone.active {
          background: rgba(255, 50, 30, 0.08);
          animation: overheat-pulse 0.3s ease-in-out infinite alternate;
        }

        @keyframes overheat-pulse {
          from { background: rgba(255, 50, 30, 0.05); }
          to { background: rgba(255, 50, 30, 0.18); }
        }

        /* Charge fill bar */
        .charge-fill {
          position: absolute;
          top: 0;
          left: 0;
          bottom: 0;
          width: 0%;
          z-index: 2;
          border-radius: 2px 0 0 2px;
          transition: width 0.15s ease-out, background 0.15s ease-out;
          pointer-events: none;
        }

        /* Color stages via data attribute */
        .charge-fill[data-zone="low"] {
          background: linear-gradient(90deg, #1144aa, #2266cc);
          box-shadow: 0 0 6px rgba(34, 102, 204, 0.3);
        }
        .charge-fill[data-zone="good"] {
          background: linear-gradient(90deg, #2266cc, #44aa44);
          box-shadow: 0 0 8px rgba(68, 170, 68, 0.3);
        }
        .charge-fill[data-zone="sweet"] {
          background: linear-gradient(90deg, #44aa44, #66ee66);
          box-shadow: 0 0 12px rgba(102, 238, 102, 0.5);
        }
        .charge-fill[data-zone="overheat"] {
          background: linear-gradient(90deg, #cc6600, #ee3322);
          box-shadow: 0 0 10px rgba(238, 51, 34, 0.4);
          animation: fill-flicker 0.15s ease-in-out infinite alternate;
        }

        @keyframes fill-flicker {
          from { opacity: 0.85; }
          to { opacity: 1; }
        }

        /* Current position marker */
        .charge-marker {
          position: absolute;
          top: 0;
          bottom: 0;
          width: 2px;
          background: #fff;
          z-index: 3;
          left: 0%;
          transition: left 0.15s ease-out;
          box-shadow: 0 0 4px rgba(255, 255, 255, 0.6);
          pointer-events: none;
        }

        /* --- Charge percentage readout --- */
        .charge-pct {
          position: absolute;
          right: 6px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 0.75rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: #aab;
          z-index: 4;
          pointer-events: none;
          text-shadow: 0 0 4px rgba(0, 0, 0, 0.8);
        }

        /* --- FIRE button --- */
        .fire-btn {
          width: 100%;
          padding: 10px 0;
          font-size: 1rem;
          font-weight: 700;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          border: 2px solid #334;
          border-radius: 4px;
          background: #1a1a2e;
          color: #556;
          cursor: not-allowed;
          transition: all 0.2s ease;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .fire-btn.ready {
          background: #112244;
          border-color: #4488ff;
          color: #4488ff;
          cursor: pointer;
          box-shadow: 0 0 8px rgba(68, 136, 255, 0.2);
        }

        .fire-btn.ready:hover {
          background: #1a3366;
          box-shadow: 0 0 14px rgba(68, 136, 255, 0.4);
        }

        .fire-btn.ready:active {
          background: #224488;
          transform: scale(0.98);
        }

        .fire-btn.sweet-spot {
          background: #0a2a0a;
          border-color: #44ee44;
          color: #44ee44;
          cursor: pointer;
          box-shadow: 0 0 12px rgba(68, 238, 68, 0.3);
          animation: btn-pulse 0.8s ease-in-out infinite alternate;
        }

        .fire-btn.sweet-spot:hover {
          background: #143a14;
          box-shadow: 0 0 20px rgba(68, 238, 68, 0.5);
        }

        @keyframes btn-pulse {
          from { box-shadow: 0 0 8px rgba(68, 238, 68, 0.2); }
          to { box-shadow: 0 0 18px rgba(68, 238, 68, 0.5); }
        }

        /* --- Feedback overlay --- */
        .feedback {
          text-align: center;
          font-weight: 800;
          font-size: 1.4rem;
          letter-spacing: 0.2em;
          min-height: 1.8em;
          line-height: 1.8em;
          opacity: 0;
          transition: opacity 0.15s ease;
          text-transform: uppercase;
        }

        .feedback.visible {
          opacity: 1;
        }

        .feedback.perfect {
          color: #44ee44;
          text-shadow: 0 0 16px rgba(68, 238, 68, 0.6), 0 0 30px rgba(68, 238, 68, 0.3);
          font-size: 1.6rem;
          animation: feedback-pop 0.3s ease-out;
        }

        .feedback.good {
          color: #eecc44;
          text-shadow: 0 0 12px rgba(238, 204, 68, 0.5);
          animation: feedback-pop 0.25s ease-out;
        }

        .feedback.weak {
          color: #cc4444;
          text-shadow: 0 0 8px rgba(204, 68, 68, 0.4);
          font-size: 1.1rem;
        }

        .feedback.overheat {
          color: #ee3322;
          text-shadow: 0 0 14px rgba(238, 51, 34, 0.6);
          animation: feedback-flash 0.2s ease-in-out 3;
        }

        @keyframes feedback-pop {
          0% { transform: scale(0.7); opacity: 0; }
          60% { transform: scale(1.15); }
          100% { transform: scale(1); opacity: 1; }
        }

        @keyframes feedback-flash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        /* --- Idle / no-solution state --- */
        .idle-msg {
          text-align: center;
          color: #445;
          font-size: 0.75rem;
          padding: 20px 0;
          letter-spacing: 0.05em;
        }
      </style>

      <div class="charge-container">
        <div class="charge-label">
          RAILGUN CHARGE<span class="mount-id"></span>
        </div>

        <div class="charge-bar-wrapper">
          <div class="charge-bar-bg"></div>
          <div class="sweet-spot">
            <span class="sweet-spot-label">sweet spot</span>
          </div>
          <div class="overheat-zone"></div>
          <div class="charge-fill" data-zone="low"></div>
          <div class="charge-marker"></div>
          <span class="charge-pct">0%</span>
        </div>

        <button class="fire-btn" disabled>FIRE</button>

        <div class="feedback"></div>

        <div class="idle-msg">Waiting for railgun solution...</div>
      </div>
    `;
  }

  _setupListeners() {
    this.shadowRoot.querySelector(".fire-btn").addEventListener("click", () => {
      this._onFire();
    });
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  /**
   * Read weapon telemetry and update the charge bar UI.
   */
  _updateDisplay() {
    if (!this.offsetParent) return;
    const weapons = stateManager.getWeapons();
    const truthWeapons = weapons?.truth_weapons || {};

    // Find first railgun with a valid solution
    let railgun = null;
    let railgunId = null;
    for (const [id, w] of Object.entries(truthWeapons)) {
      if (id.startsWith("railgun")) {
        railgunId = id;
        railgun = w;
        // Prefer one with a valid solution
        if (w.solution?.valid) break;
      }
    }

    const container = this.shadowRoot.querySelector(".charge-container");
    const idleMsg = this.shadowRoot.querySelector(".idle-msg");
    const barWrapper = this.shadowRoot.querySelector(".charge-bar-wrapper");
    const fireBtn = this.shadowRoot.querySelector(".fire-btn");

    if (!railgun || !railgun.solution?.valid) {
      // No railgun or no valid solution — show idle state
      idleMsg.style.display = "";
      barWrapper.style.display = "none";
      fireBtn.style.display = "none";
      this._chargeState = "idle";
      this._chargeProgress = 0;
      this._railgunMountId = null;
      this._hasSolution = false;
      return;
    }

    // We have a railgun with a valid solution
    idleMsg.style.display = "none";
    barWrapper.style.display = "";
    fireBtn.style.display = "";

    this._railgunMountId = railgunId;
    this._hasSolution = true;

    // Read charge state from telemetry
    const chargeState = railgun.charge_state || "idle";
    const chargeProgress = Math.max(0, Math.min(1, railgun.charge_progress || 0));
    const prevState = this._chargeState;

    this._chargeState = chargeState;
    this._chargeProgress = chargeProgress;

    // Detect overheat: charge was active and now discharging/idle at max
    if (prevState === "charging" && (chargeState === "discharging" || chargeState === "idle") && chargeProgress > 0.9) {
      this._showFeedback("OVERHEAT");
    }

    // Update mount ID label
    const mountLabel = this.shadowRoot.querySelector(".mount-id");
    mountLabel.textContent = railgunId ? ` [${railgunId}]` : "";

    // Update charge fill bar
    const fill = this.shadowRoot.querySelector(".charge-fill");
    const marker = this.shadowRoot.querySelector(".charge-marker");
    const pct = this.shadowRoot.querySelector(".charge-pct");
    const overheatZone = this.shadowRoot.querySelector(".overheat-zone");

    const widthPct = (chargeProgress * 100).toFixed(1);
    fill.style.width = `${widthPct}%`;
    marker.style.left = `${widthPct}%`;
    pct.textContent = `${Math.round(chargeProgress * 100)}%`;

    // Subsystem damage narrows the sweet spot
    const dmg = getDegradation("weapons");
    const sweetMin = SWEET_SPOT_MIN + dmg * 0.1;
    const sweetMax = SWEET_SPOT_MAX - dmg * 0.05;

    // Determine color zone
    let zone = "low";
    if (chargeProgress >= sweetMax) {
      zone = "overheat";
    } else if (chargeProgress >= sweetMin) {
      zone = "sweet";
    } else if (chargeProgress >= GOOD_ZONE_MIN) {
      zone = "good";
    }
    fill.dataset.zone = zone;

    // Overheat zone visual activation
    overheatZone.classList.toggle("active", chargeProgress >= SWEET_SPOT_MAX);

    // Update fire button state
    const isCharging = chargeState === "charging" || chargeState === "ready";
    const canFire = isCharging && chargeProgress > 0.1;

    fireBtn.disabled = !canFire;
    fireBtn.classList.remove("ready", "sweet-spot");
    if (canFire) {
      if (zone === "sweet") {
        fireBtn.classList.add("sweet-spot");
      } else {
        fireBtn.classList.add("ready");
      }
    }

    // Ammo/reload info on button
    const ammo = railgun.ammo ?? 0;
    const reloading = railgun.reloading || false;
    if (reloading) {
      fireBtn.textContent = "RELOADING...";
      fireBtn.disabled = true;
      fireBtn.classList.remove("ready", "sweet-spot");
    } else if (ammo === 0) {
      fireBtn.textContent = "NO AMMO";
      fireBtn.disabled = true;
      fireBtn.classList.remove("ready", "sweet-spot");
    } else {
      fireBtn.textContent = canFire ? "FIRE" : "CHARGING...";
    }
  }

  /**
   * Player pressed FIRE — evaluate timing and send command.
   */
  _onFire() {
    const progress = this._chargeProgress;

    // Subsystem damage narrows the sweet spot for feedback too
    const dmg = getDegradation("weapons");
    const sweetMin = SWEET_SPOT_MIN + dmg * 0.1;
    const sweetMax = SWEET_SPOT_MAX - dmg * 0.05;

    // Determine feedback based on charge timing
    if (progress >= sweetMin && progress <= sweetMax) {
      this._showFeedback("PERFECT");
    } else if (progress >= GOOD_ZONE_MIN && progress < sweetMin) {
      this._showFeedback("GOOD");
    } else if (progress < GOOD_ZONE_MIN) {
      this._showFeedback("WEAK");
    }
    // progress > SWEET_SPOT_MAX but not yet reset = still fires, no extra feedback

    // Always send the fire command — server decides actual hit/miss
    if (this._railgunMountId) {
      wsClient.sendShipCommand("fire_railgun", { mount_id: this._railgunMountId });
    }
  }

  /**
   * Show timed feedback text after firing or overheating.
   */
  _showFeedback(type) {
    const el = this.shadowRoot.querySelector(".feedback");
    if (!el) return;

    // Clear previous
    if (this._feedbackTimer) {
      clearTimeout(this._feedbackTimer);
      this._feedbackTimer = null;
    }

    const labels = {
      PERFECT: "PERFECT!",
      GOOD: "GOOD",
      WEAK: "WEAK",
      OVERHEAT: "OVERHEAT",
    };

    el.textContent = labels[type] || type;
    el.className = "feedback visible " + type.toLowerCase();
    this._lastFeedback = type;

    this._feedbackTimer = setTimeout(() => {
      el.classList.remove("visible");
      this._feedbackTimer = null;
    }, FEEDBACK_DURATION_MS);
  }
}

customElements.define("weapons-charge-game", WeaponsChargeGame);
