/**
 * Helm Workflow Strip
 * Breadcrumb bar showing the current workflow step for the active tier.
 * Sits above the helm view grid.
 *
 * Steps vary by tier:
 *   RAW:        PLAN -> ORIENT -> BURN -> CHECK
 *   ARCADE:     DETECT -> TARGET -> COMMAND -> MONITOR
 *   CPU-ASSIST: ASSESS -> ORDER -> QUEUE -> MONITOR
 *
 * Auto-detects current step from game state via stateManager.
 */

import { stateManager } from "../js/state-manager.js";

const TIER_STEPS = {
  raw:        ["PLAN", "ORIENT", "BURN", "CHECK"],
  arcade:     ["DETECT", "TARGET", "COMMAND", "MONITOR"],
  "cpu-assist": ["ASSESS", "ORDER", "QUEUE", "MONITOR"],
};

const ARROW = "\u2500\u2500\u25B6";

class HelmWorkflowStrip extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tier = window.controlTier || "arcade";
    this._currentStep = 0;
    this._pollId = null;
    this._onTierChange = null;
  }

  connectedCallback() {
    this._onTierChange = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._currentStep = 0;
      this._render();
    };
    document.addEventListener("tier-change", this._onTierChange);

    this._pollId = setInterval(() => this._detectStep(), 2000);
    this._detectStep();
    this._render();
  }

  disconnectedCallback() {
    if (this._onTierChange) {
      document.removeEventListener("tier-change", this._onTierChange);
      this._onTierChange = null;
    }
    if (this._pollId) {
      clearInterval(this._pollId);
      this._pollId = null;
    }
  }

  /** Determine how many steps are completed based on game state. */
  _detectStep() {
    let step = 0;
    const contacts = stateManager.getContacts();
    if (contacts && Object.keys(contacts).length > 0) step = 1;

    const targeting = stateManager.getTargeting();
    if (targeting?.target_id) step = 2;

    const nav = stateManager.getNavigation();
    if (nav?.autopilot?.active) step = 3;

    if (step !== this._currentStep) {
      this._currentStep = step;
      this._render();
    }
  }

  _render() {
    const steps = TIER_STEPS[this._tier] || TIER_STEPS.arcade;
    const accent = "var(--strip-accent, #4488ff)";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 32px;
          user-select: none;
        }
        .strip {
          display: flex;
          align-items: center;
          gap: 4px;
          height: 100%;
          font-family: "Courier New", monospace;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: #556;
        }
        .step {
          cursor: pointer;
          padding: 2px 6px;
          border-radius: 2px;
          transition: color 0.2s, text-shadow 0.2s;
          white-space: nowrap;
        }
        .step:hover { color: #99aacc; }
        .step.done { color: #6a8; }
        .step.current {
          color: ${accent};
          text-shadow: 0 0 6px ${accent};
        }
        .arrow { color: #334; padding: 0 2px; }
      </style>
      <div class="strip">
        ${steps.map((name, i) => {
          let cls = "step";
          let label = `${i + 1}. ${name}`;
          if (i < this._currentStep) { cls += " done"; label = `\u2713 ${name}`; }
          else if (i === this._currentStep) { cls += " current"; }
          const arrow = i < steps.length - 1
            ? `<span class="arrow">${ARROW}</span>` : "";
          return `<span class="${cls}" data-step="${i}">${label}</span>${arrow}`;
        }).join("")}
      </div>
    `;

    this.shadowRoot.querySelector(".strip").addEventListener("click", (e) => {
      const stepEl = e.target.closest(".step");
      if (!stepEl) return;
      const idx = parseInt(stepEl.dataset.step, 10);
      const stepId = steps[idx]?.toLowerCase();
      if (stepId) {
        this.dispatchEvent(new CustomEvent("workflow-step-click", {
          bubbles: true, composed: true,
          detail: { step: stepId },
        }));
      }
    });
  }
}

customElements.define("helm-workflow-strip", HelmWorkflowStrip);
export { HelmWorkflowStrip };
