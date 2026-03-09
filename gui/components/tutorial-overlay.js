/**
 * Tutorial Overlay Component
 * Step-by-step guide for Mission 1 across three control tiers.
 * Floating panel in the bottom-right corner, toggled via method or event.
 */

import { wsClient } from "../js/ws-client.js";

const STORAGE_KEY = "flaxos-tutorial-dismissed";

const TRACKS = {
  autopilot: {
    label: "AUTOPILOT",
    steps: [
      { text: "Welcome! Load Mission 1 by clicking the MISSION tab (key: 6), then select 'Tutorial: Intercept and Approach' and click LOAD.", highlight: "view-tabs" },
      { text: "Good! You can see the mission briefing. Switch to the HELM tab (key: 1) to access flight controls.", highlight: "view-tabs" },
      { text: "Look at the Autopilot Control panel. Select 'INTERCEPT' mode from the mode grid.", highlight: "autopilot-control" },
      { text: "In the Target dropdown, select 'Tycho Station' (or the station contact).", highlight: "autopilot-control" },
      { text: "Click ENGAGE. The autopilot will now fly your ship toward the station.", highlight: "autopilot-control" },
      { text: "Watch the Autopilot Status panel -- it shows the current phase (ACCELERATE > COAST > BRAKE > HOLD) and distance countdown.", highlight: "autopilot-status" },
      { text: "When you reach 1km, the mission completes! Check the MISSION tab to see your success.", highlight: "mission-objectives" },
    ],
  },
  arcade: {
    label: "ARCADE",
    steps: [
      { text: "Load Mission 1 from the MISSION tab (key: 6).", highlight: "view-tabs" },
      { text: "Switch to HELM tab (key: 1). First, let's find our target.", highlight: "view-tabs" },
      { text: "Look at the Sensor Contacts panel. You should see Tycho Station listed. Click on it to select it as your target.", highlight: "sensor-contacts" },
      { text: "Now use the Set Course panel. The target's coordinates are pre-filled if you have it targeted. Click SET COURSE.", highlight: "set-course-control" },
      { text: "Alternatively, use the Autopilot Control -- select INTERCEPT, choose your target, and ENGAGE.", highlight: "autopilot-control" },
      { text: "You can monitor progress in the Navigation Display -- watch your velocity, distance to target, and closing speed.", highlight: "navigation-display" },
      { text: "You can also use the Throttle slider to manually adjust speed, and the Heading Control to point your ship.", highlight: "throttle-control" },
      { text: "Reach 1km from the station to complete the mission!", highlight: "mission-objectives" },
    ],
  },
  raw: {
    label: "RAW",
    steps: [
      { text: "Load Mission 1 from the MISSION tab (key: 6). Switch to HELM (key: 1).", highlight: "view-tabs" },
      { text: "In Raw mode, you have direct thruster control. No autopilot is available.", highlight: "manual-thrust" },
      { text: "Check the Navigation Display -- note your position (X, Y, Z) and the target's position.", highlight: "navigation-display" },
      { text: "Use the Heading Control to point your ship toward the station. Match the heading to the bearing shown in Sensor Contacts.", highlight: "heading-control" },
      { text: "Use the Throttle (showing m/s^2) to apply forward thrust. Start with ~50% to build speed.", highlight: "throttle-control" },
      { text: "Watch your closing speed in the Navigation Display. You need to manage your approach -- too fast and you'll overshoot.", highlight: "navigation-display" },
      { text: "At about halfway (27km), cut thrust and flip your heading 180 degrees to begin braking.", highlight: "heading-control" },
      { text: "Apply reverse thrust to slow down. Your goal: arrive at 1km with near-zero relative velocity.", highlight: "throttle-control" },
      { text: "This is real Newtonian physics -- there's no friction to stop you! Plan your burn carefully.", highlight: null },
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
  }

  connectedCallback() {
    this._render();
    this._bind();
    // Auto-show on first visit
    if (!localStorage.getItem(STORAGE_KEY)) {
      this.show();
    }
  }

  disconnectedCallback() {
    document.removeEventListener("tutorial-toggle", this._toggleHandler);
  }

  /** Public API */

  toggle() {
    this._visible ? this.hide() : this.show();
  }

  show() {
    this._visible = true;
    this._panel().classList.add("visible");
  }

  hide() {
    this._visible = false;
    this._panel().classList.remove("visible");
  }

  dismiss() {
    localStorage.setItem(STORAGE_KEY, "1");
    this.hide();
  }

  /** Switch to a specific track and reset to step 0 */
  setTrack(trackId) {
    if (!TRACKS[trackId]) return;
    this._track = trackId;
    this._step = 0;
    this._updateContent();
    this._dispatchTierRequest(trackId);
  }

  /** Internal */

  _panel() {
    return this.shadowRoot.getElementById("panel");
  }

  _bind() {
    // Track selector buttons
    this.shadowRoot.querySelectorAll(".track-btn").forEach((btn) => {
      btn.addEventListener("click", () => this.setTrack(btn.dataset.track));
    });

    // Nav buttons
    this.shadowRoot.getElementById("prev").addEventListener("click", () => this._prev());
    this.shadowRoot.getElementById("next").addEventListener("click", () => this._next());
    this.shadowRoot.getElementById("skip").addEventListener("click", () => this.dismiss());
    this.shadowRoot.getElementById("close").addEventListener("click", () => this.hide());

    // Reset scenario button (hidden until last step)
    this.shadowRoot.getElementById("reset").addEventListener("click", () => {
      wsClient.send("load_scenario", { scenario: "tutorial_intercept" });
    });

    // Listen for external toggle event
    this._toggleHandler = () => this.toggle();
    document.addEventListener("tutorial-toggle", this._toggleHandler);
  }

  _prev() {
    if (this._step > 0) {
      this._step--;
      this._updateContent();
    }
  }

  _next() {
    const steps = TRACKS[this._track].steps;
    if (this._step < steps.length - 1) {
      this._step++;
      this._updateContent();
    }
  }

  _updateContent() {
    const track = TRACKS[this._track];
    const steps = track.steps;
    const step = steps[this._step];

    // Step text
    this.shadowRoot.getElementById("step-text").textContent = step.text;

    // Counter
    this.shadowRoot.getElementById("counter").textContent =
      `Step ${this._step + 1}/${steps.length}`;

    // Track label
    this.shadowRoot.getElementById("track-label").textContent = track.label;

    // Button states
    this.shadowRoot.getElementById("prev").disabled = this._step === 0;
    this.shadowRoot.getElementById("next").disabled = this._step === steps.length - 1;

    // Show reset button only on last step
    const resetBtn = this.shadowRoot.getElementById("reset");
    resetBtn.style.display = this._step === steps.length - 1 ? "inline-block" : "none";

    // Active track button
    this.shadowRoot.querySelectorAll(".track-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.track === this._track);
    });

    // Progress dots
    this._renderDots(steps.length);

    // Dispatch highlight event so external code can glow the relevant panel
    if (step.highlight) {
      document.dispatchEvent(
        new CustomEvent("tutorial-highlight", {
          detail: { selector: step.highlight },
          bubbles: true,
        })
      );
    }
  }

  _renderDots(count) {
    const container = this.shadowRoot.getElementById("dots");
    container.innerHTML = "";
    for (let i = 0; i < count; i++) {
      const dot = document.createElement("span");
      dot.className = "dot" + (i === this._step ? " active" : "");
      container.appendChild(dot);
    }
  }

  /** Dispatch event so tier-selector can pick up the requested tier */
  _dispatchTierRequest(trackId) {
    document.dispatchEvent(
      new CustomEvent("tutorial-tier-request", {
        detail: { tier: trackId },
        bubbles: true,
      })
    );
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        /* Shared mono font shorthand */
        .title, #track-label, #counter, .track-btn, .nav-btn, #reset {
          font-family: var(--font-mono, 'JetBrains Mono', monospace);
        }
        :host {
          display: block; position: fixed;
          bottom: 16px; right: 16px; z-index: 1000;
          pointer-events: none;
        }
        #panel {
          pointer-events: none; width: 380px; max-width: 380px;
          background: rgba(10, 10, 15, 0.95);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          font-family: var(--font-sans, Inter, sans-serif);
          color: var(--text-primary, #e0e0e0);
          opacity: 0; transform: translateY(12px);
          transition: opacity 0.2s ease, transform 0.2s ease;
          box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6);
        }
        #panel.visible { opacity: 1; transform: translateY(0); pointer-events: auto; }
        .header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 14px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          background: var(--bg-input, #1a1a2e);
          border-radius: 6px 6px 0 0;
        }
        .header-left { display: flex; align-items: center; gap: 8px; }
        .title { font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: var(--status-info, #4488ff); }
        #track-label {
          font-size: 10px; color: var(--text-secondary, #a0a0b0);
          background: var(--bg-panel, #12121a); padding: 2px 6px; border-radius: 3px;
        }
        #counter {
          font-size: 10px; color: var(--status-nominal, #00ff88);
          animation: pulse-step 2s ease-in-out infinite;
        }
        @keyframes pulse-step { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        #close {
          background: none; border: none; color: var(--text-dim, #666680);
          cursor: pointer; font-size: 16px; padding: 0 2px; line-height: 1;
        }
        #close:hover { color: var(--text-primary, #e0e0e0); }
        .tracks {
          display: flex; gap: 4px; padding: 8px 14px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }
        .track-btn {
          flex: 1; padding: 4px 0; font-size: 10px; letter-spacing: 1px;
          background: var(--bg-panel, #12121a);
          border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px;
          color: var(--text-dim, #666680); cursor: pointer; transition: all 0.15s ease;
        }
        .track-btn:hover { color: var(--text-secondary, #a0a0b0); border-color: var(--text-dim, #666680); }
        .track-btn.active { color: var(--status-info, #4488ff); border-color: var(--status-info, #4488ff); background: rgba(68, 136, 255, 0.08); }
        .body { padding: 14px; }
        #step-text { font-size: 13px; line-height: 1.6; min-height: 60px; }
        .nav {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 14px; border-top: 1px solid var(--border-default, #2a2a3a);
        }
        .nav-btn {
          padding: 5px 14px; font-size: 11px;
          background: var(--bg-input, #1a1a2e);
          border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px;
          color: var(--text-secondary, #a0a0b0); cursor: pointer; transition: all 0.15s ease;
        }
        .nav-btn:hover:not(:disabled) { color: var(--text-primary, #e0e0e0); border-color: var(--text-dim, #666680); }
        .nav-btn:disabled { opacity: 0.3; cursor: default; }
        #skip {
          background: none; border: none; color: var(--text-dim, #666680);
          font-size: 10px; cursor: pointer;
          font-family: var(--font-sans, Inter, sans-serif);
          text-decoration: underline; text-underline-offset: 2px;
        }
        #skip:hover { color: var(--text-secondary, #a0a0b0); }
        #reset {
          display: none; margin-top: 10px; padding: 5px 12px;
          font-size: 10px; letter-spacing: 1px;
          background: rgba(255, 170, 0, 0.1);
          border: 1px solid var(--status-warning, #ffaa00); border-radius: 3px;
          color: var(--status-warning, #ffaa00); cursor: pointer;
        }
        #reset:hover { background: rgba(255, 170, 0, 0.2); }
        .dots { display: flex; justify-content: center; gap: 5px; padding: 0 14px 10px; }
        .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--border-default, #2a2a3a); transition: background 0.2s ease; }
        .dot.active { background: var(--status-info, #4488ff); }
      </style>

      <div id="panel">
        <div class="header">
          <div class="header-left">
            <span class="title">TUTORIAL</span>
            <span id="track-label">AUTOPILOT</span>
            <span id="counter">Step 1/7</span>
          </div>
          <button id="close" title="Close">X</button>
        </div>

        <div class="tracks">
          <button class="track-btn active" data-track="autopilot">AUTOPILOT</button>
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

    // Set initial content
    this._updateContent();
  }
}

customElements.define("tutorial-overlay", TutorialOverlay);

export { TutorialOverlay };
