/**
 * Tier Selector Component
 * Lets the player switch between three control tiers: Raw, Arcade, CPU Assist.
 * Persists selection in localStorage and exposes it via window.controlTier,
 * a body CSS class (tier-raw, tier-arcade, tier-cpu-assist), and a
 * bubbling "tier-change" CustomEvent.
 */

const STORAGE_KEY = "flaxos-control-tier";
const TIERS = [
  { id: "manual",    label: "MANUAL" },
  { id: "raw",       label: "RAW" },
  { id: "arcade",    label: "ARCADE" },
  { id: "cpu-assist", label: "CPU ASSIST" },
];
const DEFAULT_TIER = "arcade";

class TierSelector extends HTMLElement {
  static get observedAttributes() {
    return ["tier"];
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    // Restore persisted tier or fall back to default
    const stored = localStorage.getItem(STORAGE_KEY);
    this._tier = TIERS.some(t => t.id === stored) ? stored : DEFAULT_TIER;
  }

  connectedCallback() {
    this._render();
    this._applyTier();
    // Listen for tutorial track changes to auto-switch tier
    this._onTutorialTier = (e) => {
      const tier = e.detail?.tier;
      if (tier) this.tier = tier;
    };
    document.addEventListener("tutorial-tier-request", this._onTutorialTier);
  }

  disconnectedCallback() {
    if (this._onTutorialTier) {
      document.removeEventListener("tutorial-tier-request", this._onTutorialTier);
      this._onTutorialTier = null;
    }
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (name === "tier" && newValue && newValue !== oldValue) {
      this.tier = newValue;
    }
  }

  get tier() {
    return this._tier;
  }

  set tier(value) {
    if (!TIERS.some(t => t.id === value)) return;
    if (this._tier === value) return;
    this._tier = value;
    this._applyTier();
    this._updateButtons();
    this._persist();
    this._emitChange();
  }

  // ---- internal ----

  /** Write the tier into localStorage, window.controlTier, and the body class. */
  _applyTier() {
    window.controlTier = this._tier;
    // Remove any previous tier class from body, then add the current one
    TIERS.forEach(t => document.body.classList.remove(`tier-${t.id}`));
    document.body.classList.add(`tier-${this._tier}`);
  }

  _persist() {
    localStorage.setItem(STORAGE_KEY, this._tier);
  }

  _emitChange() {
    this.dispatchEvent(new CustomEvent("tier-change", {
      detail: { tier: this._tier },
      bubbles: true,
      composed: true,
    }));
  }

  _updateButtons() {
    const buttons = this.shadowRoot.querySelectorAll(".tier-btn");
    buttons.forEach(btn => {
      const isActive = btn.dataset.tier === this._tier;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-pressed", isActive);
    });
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: inline-block;
          user-select: none;
        }

        .tier-group {
          display: flex;
          gap: 1px;
          background: var(--border-default, #2a2a3a);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          overflow: hidden;
        }

        .tier-btn {
          padding: 5px 12px;
          background: var(--bg-panel, #12121a);
          border: none;
          color: var(--text-dim, #555566);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 600;
          letter-spacing: 1px;
          text-transform: uppercase;
          cursor: pointer;
          transition: background 0.12s ease, color 0.12s ease, box-shadow 0.12s ease;
          position: relative;
        }

        .tier-btn:hover:not(.active) {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }

        /* --- MANUAL: amber flight-sim aesthetic --- */
        .tier-btn[data-tier="manual"].active {
          background: rgba(255, 136, 0, 0.08);
          color: #ff8800;
          box-shadow: inset 0 0 12px rgba(255, 136, 0, 0.1);
        }

        /* --- RAW: green terminal aesthetic --- */
        .tier-btn[data-tier="raw"].active {
          background: rgba(0, 255, 136, 0.08);
          color: var(--status-nominal, #00ff88);
          box-shadow: inset 0 0 12px rgba(0, 255, 136, 0.1);
        }

        /* --- ARCADE: blue HUD aesthetic --- */
        .tier-btn[data-tier="arcade"].active {
          background: rgba(74, 158, 255, 0.1);
          color: var(--hud-primary, #4a9eff);
          box-shadow: inset 0 0 12px rgba(74, 158, 255, 0.12);
        }

        /* --- CPU ASSIST: clean minimal aesthetic --- */
        .tier-btn[data-tier="cpu-assist"].active {
          background: rgba(224, 224, 224, 0.06);
          color: var(--text-primary, #e0e0e0);
        }

        /* Active indicator bar along the bottom */
        .tier-btn.active::after {
          content: "";
          position: absolute;
          bottom: 0;
          left: 20%;
          right: 20%;
          height: 2px;
          border-radius: 1px;
        }

        .tier-btn[data-tier="manual"].active::after {
          background: #ff8800;
          box-shadow: 0 0 4px #ff8800;
        }

        .tier-btn[data-tier="raw"].active::after {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 4px var(--status-nominal, #00ff88);
        }

        .tier-btn[data-tier="arcade"].active::after {
          background: var(--hud-primary, #4a9eff);
          box-shadow: 0 0 4px var(--hud-primary, #4a9eff);
        }

        .tier-btn[data-tier="cpu-assist"].active::after {
          background: var(--text-primary, #e0e0e0);
        }

        @media (max-width: 480px) {
          .tier-btn {
            padding: 4px 8px;
            font-size: 0.6rem;
            letter-spacing: 0.5px;
          }
        }
      </style>

      <div class="tier-group" role="group" aria-label="Control tier">
        ${TIERS.map(t => `
          <button
            class="tier-btn ${t.id === this._tier ? "active" : ""}"
            data-tier="${t.id}"
            aria-pressed="${t.id === this._tier}"
            title="${t.label} control tier"
          >${t.label}</button>
        `).join("")}
      </div>
    `;

    // Bind click handlers
    this.shadowRoot.querySelectorAll(".tier-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this.tier = btn.dataset.tier;
      });
    });

    // Also persist initial tier on first render
    this._persist();
  }
}

customElements.define("tier-selector", TierSelector);
export { TierSelector };
