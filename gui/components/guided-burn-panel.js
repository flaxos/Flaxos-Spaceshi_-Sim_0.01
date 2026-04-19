/**
 * guided-burn-panel — ARCADE tier guided execution panel.
 *
 * Shows upcoming phase transitions for an active intercept/rendezvous
 * autopilot and prompts the player to confirm each one at the right
 * moment.  The AP still handles all physics; this layer teaches
 * timing and makes execution feel active rather than spectator.
 *
 * Gameplay loop:
 *   1. AP burns toward target; panel shows "FLIP IN Xs" countdown.
 *   2. When flip_in_s < WINDOW_OPEN_S, a flashing [EXECUTE FLIP] button
 *      appears.  The countdown bar drains to zero.
 *   3. Player presses the button.  Panel records press timing vs the
 *      computed optimal moment and shows PERFECT / PRECISE / GOOD /
 *      EARLY / LATE / MISSED feedback.
 *   4. As AP progresses through brake → approach → stationkeep the
 *      panel updates with the current phase status.
 *
 * The AP proceeds regardless of whether the player acts — timing skill
 * is rewarded with positive feedback, not failure.  The path to RAW
 * tier is knowing this sequence well enough to execute without prompts.
 *
 * Hidden automatically in CPU-ASSIST and RAW tiers.
 */

import { stateManager } from "../js/state-manager.js";
import { extractAutopilotState, formatDistance, formatEta } from "../js/autopilot-utils.js";

// Programs that have a flip phase this panel should guide
const GUIDED_PROGRAMS = new Set(["intercept", "rendezvous", "dock_approach", "approach"]);

// Action window: show execute button within this many seconds of flip
const WINDOW_OPEN_S  = 20;
const WINDOW_URGENT_S = 7;  // goes red + fast-pulse below this

// Timing precision bands (seconds BEFORE the computed flip moment)
// Negative = pressed AFTER flip (late)
const TIMING = [
  { max:  1, label: "PERFECT",  cls: "t-perfect" },
  { max:  4, label: "PRECISE",  cls: "t-precise" },
  { max: 10, label: "GOOD",     cls: "t-good"    },
  { max: 20, label: "EARLY",    cls: "t-early"   },
  { max: -0.1, label: "LATE — AP compensated", cls: "t-late" },
];

class GuidedBurnPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub      = null;
    this._tier       = window.controlTier || "arcade";
    this._prevPhase  = null;
    this._windowOpen = false;
    this._pressed    = false;
    this._feedback   = null;   // { label, cls }
    this._fbTimer    = null;
    this._onTier     = (e) => { this._tier = e.detail?.tier || "arcade"; this._update(); };
  }

  connectedCallback() {
    this._render();
    this._unsub = stateManager.subscribe("*", () => this._update());
    document.addEventListener("tier-change", this._onTier);
  }

  disconnectedCallback() {
    if (this._unsub)  { this._unsub();  this._unsub = null; }
    if (this._fbTimer){ clearTimeout(this._fbTimer); this._fbTimer = null; }
    document.removeEventListener("tier-change", this._onTier);
  }

  _render() {
    this.shadowRoot.innerHTML = `<style>
:host { display: block; }
.panel {
  font-family: var(--font-sans, "Inter", sans-serif);
  padding: 14px;
}
.phase-label {
  font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1px; color: var(--text-secondary, #888899);
  margin-bottom: 4px;
}
.phase-desc {
  font-size: 0.8rem; color: var(--text-primary, #e0e0e0);
  margin-bottom: 12px; min-height: 1.2em;
}

/* Countdown section */
.countdown-wrap { margin-bottom: 14px; }
.countdown-header {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 6px;
}
.countdown-title {
  font-size: 0.6rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 1px; color: var(--text-dim, #555566);
}
.countdown-val {
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 1.1rem; font-weight: 700; color: var(--status-info, #00aaff);
  transition: color 0.3s;
}
.countdown-val.soon  { color: var(--status-warning, #ffaa00); }
.countdown-val.urgent{ color: var(--status-critical, #ff4444);
                        animation: cd-pulse 0.5s ease-in-out infinite; }
@keyframes cd-pulse { 0%,100%{opacity:1} 50%{opacity:.55} }

/* Progress bar */
.cd-bar-track {
  height: 8px; background: var(--bg-input, #1a1a24);
  border-radius: 4px; overflow: hidden; margin-bottom: 12px;
}
.cd-bar-fill {
  height: 100%; border-radius: 4px;
  transition: width 0.15s linear, background 0.3s;
  background: var(--status-info, #00aaff);
}
.cd-bar-fill.soon   { background: var(--status-warning, #ffaa00); }
.cd-bar-fill.urgent { background: var(--status-critical, #ff4444); }

/* Execute button */
.exec-btn {
  width: 100%; padding: 16px; border-radius: 8px;
  font-family: var(--font-sans, "Inter", sans-serif);
  font-size: 1rem; font-weight: 800; letter-spacing: 2px;
  text-transform: uppercase; cursor: pointer;
  border: 2px solid var(--status-warning, #ffaa00);
  color: var(--status-warning, #ffaa00);
  background: rgba(255,170,0, 0.08);
  transition: all 0.1s ease;
}
.exec-btn:hover { background: rgba(255,170,0, 0.18); }
.exec-btn:active { transform: scale(0.97); }
.exec-btn.urgent {
  border-color: var(--status-critical, #ff4444);
  color: var(--status-critical, #ff4444);
  background: rgba(255,68,68, 0.1);
  animation: btn-flash 0.45s ease-in-out infinite;
}
@keyframes btn-flash { 0%,100%{opacity:1} 50%{opacity:.6} }
.exec-btn.pressed {
  border-color: var(--status-nominal, #00ff88);
  color: var(--status-nominal, #00ff88);
  background: rgba(0,255,136, 0.08);
  animation: none;
}

/* Feedback bubble */
.feedback {
  margin-top: 10px; padding: 8px 12px; border-radius: 6px;
  font-size: 0.75rem; font-weight: 700; text-align: center;
  letter-spacing: 1px; text-transform: uppercase;
  animation: fb-in 0.2s ease-out;
}
@keyframes fb-in { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:none} }
.t-perfect { background: rgba(0,255,136,.15); color: #00ff88; border: 1px solid #00ff8855; }
.t-precise { background: rgba(0,255,136,.10); color: #00dd77; border: 1px solid #00dd7744; }
.t-good    { background: rgba(0,170,255,.12); color: #00aaff; border: 1px solid #00aaff44; }
.t-early   { background: rgba(255,170,0,.12); color: #ffaa00; border: 1px solid #ffaa0044; }
.t-late    { background: rgba(255,68,68,.12);  color: #ff6666; border: 1px solid #ff444433; }
.t-missed  { background: rgba(85,85,102,.12);  color: #888899; border: 1px solid #33333344; }

/* Status-only view (non-burn phases) */
.status-view { padding: 0; }
.sv-phase {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}
.sv-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.sv-dot.burn   { background: var(--status-warning, #ffaa00); }
.sv-dot.flip   { background: #cc66ff; }
.sv-dot.brake  { background: var(--status-critical, #ff4444); }
.sv-dot.approach { background: var(--status-info, #00aaff); }
.sv-dot.station{ background: var(--status-nominal, #00ff88); }
.sv-text {
  font-size: 0.78rem; color: var(--text-primary, #e0e0e0);
}
.sv-meta {
  font-size: 0.68rem; color: var(--text-secondary, #888899);
  font-family: var(--font-mono, "JetBrains Mono", monospace);
}
.hidden { display: none !important; }
</style>
<div id="root" class="hidden">
  <div class="panel">
    <!-- Phase header (always visible when AP active) -->
    <div class="phase-label" id="ph-label">NAV GUIDANCE</div>
    <div class="phase-desc" id="ph-desc">--</div>

    <!-- Burn-phase countdown + execute button -->
    <div id="burn-section" class="hidden">
      <div class="countdown-wrap">
        <div class="countdown-header">
          <span class="countdown-title">Next: Flip to retrograde</span>
          <span class="countdown-val" id="cd-val">--</span>
        </div>
        <div class="cd-bar-track">
          <div class="cd-bar-fill" id="cd-bar" style="width:0%"></div>
        </div>
      </div>
      <button class="exec-btn" id="exec-btn">EXECUTE FLIP</button>
      <div id="feedback-area"></div>
    </div>

    <!-- Non-burn phases: compact status -->
    <div id="status-section" class="hidden status-view">
      <div class="sv-phase">
        <div class="sv-dot" id="sv-dot"></div>
        <div>
          <div class="sv-text" id="sv-text">--</div>
          <div class="sv-meta" id="sv-meta"></div>
        </div>
      </div>
    </div>
  </div>
</div>`;

    this.shadowRoot.getElementById("exec-btn")
      .addEventListener("click", () => this._onExecute());
  }

  _onExecute() {
    const ap = extractAutopilotState();
    if (!ap || this._pressed) return;

    const flipInS = ap.flipInS;
    this._pressed = true;

    // Determine timing precision
    let fb;
    if (flipInS == null) {
      // Phase already transitioned — player was late
      fb = { label: "LATE — AP compensated", cls: "t-late" };
    } else {
      // flipInS > 0 means we're early by that many seconds
      const earlyBy = flipInS;
      fb = TIMING.find(t => earlyBy >= 0 ? earlyBy <= t.max : t.max < 0)
        || { label: "EARLY", cls: "t-early" };
    }

    this._showFeedback(fb);

    const btn = this.shadowRoot.getElementById("exec-btn");
    btn.classList.remove("urgent");
    btn.classList.add("pressed");
    btn.textContent = "✓ FLIP CONFIRMED";
  }

  _showFeedback({ label, cls }) {
    const area = this.shadowRoot.getElementById("feedback-area");
    area.innerHTML = `<div class="feedback ${cls}">${label}</div>`;
    if (this._fbTimer) clearTimeout(this._fbTimer);
    this._fbTimer = setTimeout(() => {
      area.innerHTML = "";
      this._fbTimer = null;
    }, 3000);
  }

  _update() {
    // Only show in arcade tier
    if (this._tier !== "arcade") {
      this.shadowRoot.getElementById("root").classList.add("hidden");
      return;
    }

    const ap = extractAutopilotState();
    const root = this.shadowRoot.getElementById("root");

    if (!ap || !GUIDED_PROGRAMS.has((ap.program || "").toLowerCase())) {
      root.classList.add("hidden");
      this._reset();
      return;
    }

    root.classList.remove("hidden");

    const phase = (ap.phase || "").toLowerCase();

    // Detect phase transition away from burn — check for missed window
    if (this._prevPhase === "burn" && phase !== "burn" && !this._pressed && this._windowOpen) {
      this._showFeedback({ label: "MISSED — AP compensated", cls: "t-missed" });
    }
    if (phase !== this._prevPhase) {
      if (phase === "burn") this._resetWindow();
      this._prevPhase = phase;
    }

    if (phase === "burn") {
      this._renderBurn(ap);
    } else {
      this._renderStatus(ap, phase);
    }
  }

  _renderBurn(ap) {
    const burnSec = this.shadowRoot.getElementById("burn-section");
    const statusSec = this.shadowRoot.getElementById("status-section");
    burnSec.classList.remove("hidden");
    statusSec.classList.add("hidden");

    this.shadowRoot.getElementById("ph-label").textContent = "NAV GUIDANCE — BURN";
    this.shadowRoot.getElementById("ph-desc").textContent =
      ap.statusText || "Accelerating toward target.";

    const flipInS = ap.flipInS;
    const cdVal  = this.shadowRoot.getElementById("cd-val");
    const cdBar  = this.shadowRoot.getElementById("cd-bar");
    const btn    = this.shadowRoot.getElementById("exec-btn");

    if (flipInS == null || flipInS < 0) {
      // Flip point passed or in-flight — hide countdown
      cdVal.textContent = "—";
      cdBar.style.width = "0%";
      cdVal.className = "countdown-val";
      cdBar.className = "cd-bar-fill";
      if (!this._pressed) btn.classList.add("hidden");
      return;
    }

    // Countdown display
    cdVal.textContent = `${Math.ceil(flipInS)}s`;
    const urgent = flipInS < WINDOW_URGENT_S;
    const soon   = flipInS < WINDOW_OPEN_S;
    cdVal.className = `countdown-val${urgent ? " urgent" : soon ? " soon" : ""}`;

    // Progress bar: fills from 0→100% as flip approaches over WINDOW_OPEN_S window
    const pct = soon ? Math.max(0, Math.min(100,
      (1 - flipInS / WINDOW_OPEN_S) * 100)) : 0;
    cdBar.style.width = `${pct.toFixed(1)}%`;
    cdBar.className = `cd-bar-fill${urgent ? " urgent" : soon ? " soon" : ""}`;

    // Execute button
    if (flipInS < WINDOW_OPEN_S && !this._pressed) {
      this._windowOpen = true;
      btn.classList.remove("hidden", "pressed");
      btn.textContent = "EXECUTE FLIP";
      btn.className = `exec-btn${urgent ? " urgent" : ""}`;
    } else if (!soon) {
      btn.classList.add("hidden");
    }
  }

  _renderStatus(ap, phase) {
    const burnSec   = this.shadowRoot.getElementById("burn-section");
    const statusSec = this.shadowRoot.getElementById("status-section");
    burnSec.classList.add("hidden");
    statusSec.classList.remove("hidden");

    const labels = {
      flip: ["FLIP", "Rotating to retrograde heading"],
      brake: ["BRAKE", "Decelerating — bleeding closing speed"],
      approach_decel: ["APPROACH DECEL", "Final retrograde braking"],
      approach_rotate: ["APPROACH ROTATE", "Turning prograde toward target"],
      approach_coast: ["APPROACH COAST", "Closing at reduced speed"],
      stationkeep: ["ON STATION", "Holding position alongside target"],
    };
    const [phLabel, phDesc] = labels[phase] || [phase.toUpperCase().replace(/_/g, " "), ap.statusText || ""];

    const dotClass = ["burn","flip","brake"].includes(phase) ? phase
      : phase.startsWith("approach") ? "approach"
      : phase === "stationkeep" ? "station" : "";

    this.shadowRoot.getElementById("ph-label").textContent = "NAV GUIDANCE";
    this.shadowRoot.getElementById("ph-desc").textContent = "";
    this.shadowRoot.getElementById("sv-dot").className = `sv-dot ${dotClass}`;
    this.shadowRoot.getElementById("sv-text").textContent = phLabel;

    const meta = [];
    if (ap.range != null)        meta.push(formatDistance(ap.range));
    if (ap.closingSpeed != null && ap.closingSpeed > 0.5)
                                  meta.push(`${ap.closingSpeed.toFixed(0)} m/s`);
    if (ap.eta != null)          meta.push(`ETA ${formatEta(ap.eta)}`);
    this.shadowRoot.getElementById("sv-meta").textContent = meta.join("  ·  ");
  }

  _resetWindow() {
    this._windowOpen = false;
    this._pressed    = false;
    const btn = this.shadowRoot.getElementById("exec-btn");
    btn.classList.add("hidden");
    btn.classList.remove("pressed", "urgent");
    btn.textContent = "EXECUTE FLIP";
  }

  _reset() {
    this._prevPhase = null;
    this._resetWindow();
  }
}

customElements.define("guided-burn-panel", GuidedBurnPanel);
export { GuidedBurnPanel };
