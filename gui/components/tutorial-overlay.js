/**
 * Tutorial Overlay Component
 * Step-by-step guide for Mission 1 across three control tiers.
 * Each step can have a `check` function that auto-advances when true.
 * Checks polled every 1.5s. Progress dots are clickable to jump to any step.
 */
import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

const STORAGE_KEY = "flaxos-tutorial-dismissed";
const CHECK_POLL_MS = 1500;
const AUTO_ADVANCE_MS = 1000;

// -- Check helpers --------------------------------------------------------
// Mission state: poll via wsClient since stateManager doesn't track mission
let _missionCache = null;
let _missionPollTime = 0;
const _pollMission = async () => {
  const now = Date.now();
  if (now - _missionPollTime < 2000 && _missionCache) return _missionCache;
  try {
    _missionCache = await wsClient.send("get_mission", {});
    _missionPollTime = now;
  } catch { /* ignore */ }
  return _missionCache;
};
// Sync checks (use cached mission data)
const missionActive = () => {
  if (!_missionCache) { _pollMission(); return false; }
  const s = _missionCache.mission_status || _missionCache.status;
  return s === "active" || s === "in_progress" || s === "loaded" || !!_missionCache.name;
};
const missionComplete = () => {
  if (!_missionCache) return false;
  const s = _missionCache.mission_status || _missionCache.status;
  return s === "success" || s === "complete" || s === "completed";
};
const helmActive = () => document.querySelector("#view-helm")?.classList.contains("active") ?? false;
const hasTarget = () => !!stateManager.getTargeting()?.target_id;
const autopilotActive = () => {
  const ship = stateManager.getShipState();
  const nav = ship?.systems?.navigation || {};
  const ap = nav.autopilot_state || nav.autopilot || {};
  return ap.enabled === true || ap.active === true || (ap.mode && ap.mode !== "off" && ap.mode !== "manual");
};
const targetDist = () => {
  const ship = stateManager.getShipState();
  const nav = ship?.systems?.navigation || {};
  const ap = nav.autopilot_state || nav.autopilot || {};
  return ap.distance ?? ap.range ?? Infinity;
};
const shipSpeed = () => {
  const nav = stateManager.getNavigation();
  const v = nav?.velocity || [0, 0, 0];
  return Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
};
const courseActive = () => {
  const ship = stateManager.getShipState();
  const nav = ship?.systems?.navigation || {};
  const ap = nav.autopilot_state || nav.autopilot || {};
  return ap.mode === "course" || ap.mode === "goto_position" || ap.enabled === true;
};

const TRACKS = {
  autopilot: {
    label: "CPU ASSIST",
    steps: [
      { text: "Welcome! Load Mission 1 by clicking the MISSION tab (key: 6), then select 'Tutorial: Intercept and Approach' and click LOAD.", highlight: "view-tabs", check: missionActive },
      { text: "Good! You can see the mission briefing. Switch to the HELM tab (key: 1) to access flight controls.", highlight: "view-tabs", check: helmActive },
      { text: "Look at the Autopilot Control panel. Select 'INTERCEPT' mode from the mode grid.", highlight: "autopilot-control", check: null },
      { text: "In the Target dropdown, select 'Tycho Station' (or the station contact).", highlight: "autopilot-control", check: hasTarget },
      { text: "Click ENGAGE. The autopilot will now fly your ship toward the station.", highlight: "autopilot-control", check: autopilotActive },
      { text: "Watch the Autopilot Status panel -- it shows the current phase (ACCELERATE > COAST > BRAKE > HOLD) and distance countdown.", highlight: "autopilot-status", check: () => targetDist() < 10000 },
      { text: "When you reach 1km, the mission completes! Check the MISSION tab to see your success.", highlight: "mission-objectives", check: missionComplete },
    ],
  },
  arcade: {
    label: "ARCADE",
    steps: [
      { text: "Load Mission 1 from the MISSION tab (key: 6).", highlight: "view-tabs", check: missionActive },
      { text: "Switch to HELM tab (key: 1). First, let's find our target.", highlight: "view-tabs", check: helmActive },
      { text: "Look at the Sensor Contacts panel. You should see Tycho Station listed. Click on it to select it as your target.", highlight: "sensor-contacts", check: hasTarget },
      { text: "Now use the Set Course panel. The target's coordinates are pre-filled if you have it targeted. Click SET COURSE.", highlight: "set-course-control", check: courseActive },
      { text: "Alternatively, use the Autopilot Control -- select INTERCEPT, choose your target, and ENGAGE.", highlight: "autopilot-control", check: null },
      { text: "You can monitor progress in the Navigation Display -- watch your velocity, distance to target, and closing speed.", highlight: "navigation-display", check: () => targetDist() < 20000 },
      { text: "You can also use the Throttle slider to manually adjust speed, and the Heading Control to point your ship.", highlight: "throttle-control", check: null },
      { text: "Reach 1km from the station to complete the mission!", highlight: "mission-objectives", check: missionComplete },
    ],
  },
  raw: {
    label: "RAW",
    steps: [
      { text: "Load Mission 1 from the MISSION tab (key: 6). Switch to HELM (key: 1).", highlight: "view-tabs", check: () => missionActive() && helmActive() },
      { text: "In Raw mode, you have direct thruster control. No autopilot is available.", highlight: "manual-thrust", check: null },
      { text: "Check the Navigation Display -- note your position (X, Y, Z) and the target's position.", highlight: "navigation-display", check: null },
      { text: "Use the Heading Control to point your ship toward the station. Match the heading to the bearing shown in Sensor Contacts.", highlight: "heading-control", check: null },
      { text: "Use the Throttle (showing m/s^2) to apply forward thrust. Start with ~50% to build speed.", highlight: "throttle-control", check: () => shipSpeed() > 5 },
      { text: "Watch your closing speed in the Navigation Display. You need to manage your approach -- too fast and you'll overshoot.", highlight: "navigation-display", check: () => targetDist() < 30000 },
      { text: "At about halfway (27km), cut thrust and flip your heading 180 degrees to begin braking.", highlight: "heading-control", check: null },
      { text: "Apply reverse thrust to slow down. Your goal: arrive at 1km with near-zero relative velocity.", highlight: "throttle-control", check: () => targetDist() < 5000 },
      { text: "This is real Newtonian physics -- there's no friction to stop you! Plan your burn carefully.", highlight: null, check: missionComplete },
    ],
  },
};

class TutorialOverlay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._visible = false;
    this._track = "autopilot";
    this._step = 0;
    this._checkInterval = null;
    this._autoAdvanceTimer = null;
    this._completedSteps = new Set();
  }

  connectedCallback() { this._render(); this._bind(); if (!localStorage.getItem(STORAGE_KEY)) this.show(); }
  disconnectedCallback() { document.removeEventListener("tutorial-toggle", this._toggleHandler); this._stopChecks(); }

  toggle() { this._visible ? this.hide() : this.show(); }
  show() { this._visible = true; this._panel().classList.add("visible"); this._startChecks(); }
  hide() { this._visible = false; this._panel().classList.remove("visible"); this._stopChecks(); }
  dismiss() { localStorage.setItem(STORAGE_KEY, "1"); this.hide(); }

  setTrack(trackId) {
    if (!TRACKS[trackId]) return;
    this._track = trackId; this._step = 0;
    this._completedSteps.clear(); this._clearAuto();
    this._updateContent(); this._dispatchTierRequest(trackId);
  }

  goToStep(i) {
    const len = TRACKS[this._track].steps.length;
    if (i < 0 || i >= len) return;
    this._step = i; this._clearAuto(); this._updateContent();
  }

  _panel() { return this.shadowRoot.getElementById("panel"); }

  _bind() {
    this.shadowRoot.querySelectorAll(".track-btn").forEach(b => b.addEventListener("click", () => this.setTrack(b.dataset.track)));
    this.shadowRoot.getElementById("prev").addEventListener("click", () => this._prev());
    this.shadowRoot.getElementById("next").addEventListener("click", () => this._next());
    this.shadowRoot.getElementById("skip").addEventListener("click", () => this.dismiss());
    this.shadowRoot.getElementById("close").addEventListener("click", () => this.hide());
    this.shadowRoot.getElementById("reset").addEventListener("click", () => wsClient.send("load_scenario", { scenario: "tutorial_intercept" }));
    this._toggleHandler = () => this.toggle();
    document.addEventListener("tutorial-toggle", this._toggleHandler);
  }

  _prev() { if (this._step > 0) { this._step--; this._clearAuto(); this._updateContent(); } }
  _next() { const s = TRACKS[this._track].steps; if (this._step < s.length - 1) { this._step++; this._clearAuto(); this._updateContent(); } }

  _startChecks() { this._stopChecks(); this._checkInterval = setInterval(() => this._runCheck(), CHECK_POLL_MS); }
  _stopChecks() { if (this._checkInterval) { clearInterval(this._checkInterval); this._checkInterval = null; } this._clearAuto(); }
  _clearAuto() { if (this._autoAdvanceTimer) { clearTimeout(this._autoAdvanceTimer); this._autoAdvanceTimer = null; } }

  /** Poll current step check. On pass: mark completed, flash green, auto-advance after delay. */
  _runCheck() {
    if (!this._visible || this._autoAdvanceTimer) return;
    const track = TRACKS[this._track];
    const step = track.steps[this._step];
    if (!step?.check) return;
    let ok = false;
    try { ok = step.check(); } catch (_) { return; }
    if (!ok) return;

    this._completedSteps.add(this._step);
    this._renderDots(track.steps.length);
    const el = this.shadowRoot.getElementById("step-text");
    el.classList.add("step-complete");

    if (this._step < track.steps.length - 1) {
      this._autoAdvanceTimer = setTimeout(() => {
        this._autoAdvanceTimer = null; el.classList.remove("step-complete"); this._next();
      }, AUTO_ADVANCE_MS);
    } else {
      setTimeout(() => el.classList.remove("step-complete"), AUTO_ADVANCE_MS);
    }
  }

  _updateContent() {
    const track = TRACKS[this._track];
    const steps = track.steps;
    const step = steps[this._step];
    this.shadowRoot.getElementById("step-text").textContent = step.text;
    this.shadowRoot.getElementById("counter").textContent = `Step ${this._step + 1}/${steps.length}`;
    this.shadowRoot.getElementById("track-label").textContent = track.label;
    this.shadowRoot.getElementById("prev").disabled = this._step === 0;
    this.shadowRoot.getElementById("next").disabled = this._step === steps.length - 1;
    this.shadowRoot.getElementById("reset").style.display = this._step === steps.length - 1 ? "inline-block" : "none";
    this.shadowRoot.querySelectorAll(".track-btn").forEach(b => b.classList.toggle("active", b.dataset.track === this._track));
    this._renderDots(steps.length);
    if (step.highlight) {
      document.dispatchEvent(new CustomEvent("tutorial-highlight", { detail: { selector: step.highlight }, bubbles: true }));
    }
  }

  _renderDots(count) {
    const c = this.shadowRoot.getElementById("dots");
    c.innerHTML = "";
    for (let i = 0; i < count; i++) {
      const d = document.createElement("span");
      let cls = "dot clickable";
      if (i === this._step) cls += " active";
      if (this._completedSteps.has(i)) cls += " completed";
      d.className = cls; d.title = `Step ${i + 1}`;
      d.addEventListener("click", () => this.goToStep(i));
      c.appendChild(d);
    }
  }

  _dispatchTierRequest(trackId) {
    document.dispatchEvent(new CustomEvent("tutorial-tier-request", { detail: { tier: trackId }, bubbles: true }));
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        .title, #track-label, #counter, .track-btn, .nav-btn, #reset { font-family: var(--font-mono, 'JetBrains Mono', monospace); }
        :host { display: block; position: fixed; bottom: 16px; right: 16px; z-index: 1000; pointer-events: none; }
        #panel {
          pointer-events: none; width: 380px; max-width: 380px;
          background: rgba(10, 10, 15, 0.95); border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px; font-family: var(--font-sans, Inter, sans-serif);
          color: var(--text-primary, #e0e0e0); opacity: 0; transform: translateY(12px);
          transition: opacity 0.2s ease, transform 0.2s ease; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6);
        }
        #panel.visible { opacity: 1; transform: translateY(0); pointer-events: auto; }
        .header {
          display: flex; align-items: center; justify-content: space-between; padding: 10px 14px;
          border-bottom: 1px solid var(--border-default, #2a2a3a); background: var(--bg-input, #1a1a2e); border-radius: 6px 6px 0 0;
        }
        .header-left { display: flex; align-items: center; gap: 8px; }
        .title { font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: var(--status-info, #4488ff); }
        #track-label { font-size: 10px; color: var(--text-secondary, #a0a0b0); background: var(--bg-panel, #12121a); padding: 2px 6px; border-radius: 3px; }
        #counter { font-size: 10px; color: var(--status-nominal, #00ff88); animation: pulse-step 2s ease-in-out infinite; }
        @keyframes pulse-step { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        #close { background: none; border: none; color: var(--text-dim, #666680); cursor: pointer; font-size: 16px; padding: 0 2px; line-height: 1; }
        #close:hover { color: var(--text-primary, #e0e0e0); }
        .tracks { display: flex; gap: 4px; padding: 8px 14px; border-bottom: 1px solid var(--border-default, #2a2a3a); }
        .track-btn {
          flex: 1; padding: 4px 0; font-size: 10px; letter-spacing: 1px; background: var(--bg-panel, #12121a);
          border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px; color: var(--text-dim, #666680); cursor: pointer; transition: all 0.15s ease;
        }
        .track-btn:hover { color: var(--text-secondary, #a0a0b0); border-color: var(--text-dim, #666680); }
        .track-btn.active { color: var(--status-info, #4488ff); border-color: var(--status-info, #4488ff); background: rgba(68, 136, 255, 0.08); }
        .body { padding: 14px; }
        #step-text { font-size: 13px; line-height: 1.6; min-height: 60px; transition: color 0.3s ease; }
        #step-text.step-complete { color: var(--status-nominal, #00ff88); }
        .nav {
          display: flex; align-items: center; justify-content: space-between; padding: 10px 14px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }
        .nav-btn {
          padding: 5px 14px; font-size: 11px; background: var(--bg-input, #1a1a2e);
          border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px;
          color: var(--text-secondary, #a0a0b0); cursor: pointer; transition: all 0.15s ease;
        }
        .nav-btn:hover:not(:disabled) { color: var(--text-primary, #e0e0e0); border-color: var(--text-dim, #666680); }
        .nav-btn:disabled { opacity: 0.3; cursor: default; }
        #skip {
          background: none; border: none; color: var(--text-dim, #666680); font-size: 10px; cursor: pointer;
          font-family: var(--font-sans, Inter, sans-serif); text-decoration: underline; text-underline-offset: 2px;
        }
        #skip:hover { color: var(--text-secondary, #a0a0b0); }
        #reset {
          display: none; margin-top: 10px; padding: 5px 12px; font-size: 10px; letter-spacing: 1px;
          background: rgba(255, 170, 0, 0.1); border: 1px solid var(--status-warning, #ffaa00);
          border-radius: 3px; color: var(--status-warning, #ffaa00); cursor: pointer;
        }
        #reset:hover { background: rgba(255, 170, 0, 0.2); }
        .dots { display: flex; justify-content: center; gap: 5px; padding: 0 14px 10px; }
        .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--border-default, #2a2a3a); transition: background 0.2s ease; }
        .dot.active { background: var(--status-info, #4488ff); }
        .dot.completed { background: var(--status-nominal, #00ff88); }
        .dot.clickable { cursor: pointer; }
        .dot.clickable:hover { opacity: 0.7; }
      </style>
      <div id="panel">
        <div class="header">
          <div class="header-left">
            <span class="title">TUTORIAL</span>
            <span id="track-label">CPU ASSIST</span>
            <span id="counter">Step 1/7</span>
          </div>
          <button id="close" title="Close">X</button>
        </div>
        <div class="tracks">
          <button class="track-btn active" data-track="autopilot">CPU ASSIST</button>
          <button class="track-btn" data-track="arcade">ARCADE</button>
          <button class="track-btn" data-track="raw">RAW</button>
        </div>
        <div class="body">
          <div id="step-text"></div>
          <button id="reset">RESET SCENARIO</button>
        </div>
        <div id="dots" class="dots"></div>
        <div class="nav">
          <button id="prev" class="nav-btn" disabled>PREV</button>
          <button id="skip">SKIP TUTORIAL</button>
          <button id="next" class="nav-btn">NEXT</button>
        </div>
      </div>
    `;
    this._updateContent();
  }
}

customElements.define("tutorial-overlay", TutorialOverlay);
export { TutorialOverlay };
