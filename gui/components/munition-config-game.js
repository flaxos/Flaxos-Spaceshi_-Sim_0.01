/**
 * Munition Configuration Game (ARCADE tier)
 *
 * Visual loadout panel for configuring torpedo/missile parameters before
 * firing. Three selection rows: warhead type, guidance mode, flight profile.
 * Replaces the MANUAL tier's text-based program_munition interface with
 * large clickable icons and clear descriptions.
 *
 * State reads:
 *   weapons.munition_program  -- current server-side program (if any)
 *   weapons.launcher_type     -- "torpedo" or "missile" (from weapon-controls)
 *
 * On selection change: sends program_munition command to server AND stores
 * config on window._munitionConfig for weapon-controls fire handlers to read.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";
import { getDegradation } from "../js/minigame-difficulty.js";

// Default configuration
const DEFAULTS = {
  warhead_type: "fragmentation",
  guidance_mode: "guided",
  flight_profile: "direct",
};

// Warhead options with SVG icons (inline path data for shadow DOM)
const WARHEADS = [
  {
    id: "fragmentation",
    label: "FRAG",
    desc: "Area blast, 100m radius",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <circle cx="16" cy="16" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/>
      <line x1="16" y1="4" x2="16" y2="10" stroke="currentColor" stroke-width="1.5"/>
      <line x1="16" y1="22" x2="16" y2="28" stroke="currentColor" stroke-width="1.5"/>
      <line x1="4" y1="16" x2="10" y2="16" stroke="currentColor" stroke-width="1.5"/>
      <line x1="22" y1="16" x2="28" y2="16" stroke="currentColor" stroke-width="1.5"/>
      <line x1="7.5" y1="7.5" x2="11.8" y2="11.8" stroke="currentColor" stroke-width="1.2"/>
      <line x1="20.2" y1="20.2" x2="24.5" y2="24.5" stroke="currentColor" stroke-width="1.2"/>
      <line x1="24.5" y1="7.5" x2="20.2" y2="11.8" stroke="currentColor" stroke-width="1.2"/>
      <line x1="11.8" y1="20.2" x2="7.5" y2="24.5" stroke="currentColor" stroke-width="1.2"/>
    </svg>`,
  },
  {
    id: "shaped_charge",
    label: "SHAPED",
    desc: "Focused penetrator, needs direct hit",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <polygon points="16,3 22,28 16,22 10,28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
      <line x1="16" y1="10" x2="16" y2="18" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,
  },
  {
    id: "emp",
    label: "EMP",
    desc: "Electronics kill, disables systems",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <polyline points="14,4 18,14 12,14 18,28" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="16" cy="16" r="12" fill="none" stroke="currentColor" stroke-width="0.8" stroke-dasharray="3 3" opacity="0.5"/>
    </svg>`,
  },
];

const GUIDANCE_MODES = [
  {
    id: "dumb",
    label: "DUMB",
    desc: "Unguided, fire-and-forget",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <line x1="4" y1="16" x2="28" y2="16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <polygon points="28,16 22,12 22,20" fill="currentColor"/>
    </svg>`,
  },
  {
    id: "guided",
    label: "GUIDED",
    desc: "Terminal correction",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <path d="M4,20 Q12,20 16,16 Q20,12 28,12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <polygon points="28,12 22,8 22,16" fill="currentColor"/>
    </svg>`,
  },
  {
    id: "smart",
    label: "SMART",
    desc: "Full autonomous guidance",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <path d="M4,22 C8,22 10,10 16,16 C22,22 24,10 28,10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <polygon points="28,10 22,6 22,14" fill="currentColor"/>
      <circle cx="16" cy="16" r="2" fill="currentColor"/>
    </svg>`,
  },
];

const FLIGHT_PROFILES = [
  {
    id: "direct",
    label: "DIRECT",
    desc: "Shortest path",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <line x1="4" y1="24" x2="28" y2="8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <polygon points="28,8 22,8 26,14" fill="currentColor"/>
    </svg>`,
  },
  {
    id: "evasive",
    label: "EVASIVE",
    desc: "PDC evasion weave",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <path d="M4,24 C8,18 10,28 14,20 C18,12 20,22 24,14 L28,8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <polygon points="28,8 22,8 26,14" fill="currentColor"/>
    </svg>`,
  },
  {
    id: "terminal_pop",
    label: "POP-UP",
    desc: "Low approach, terminal dive",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <path d="M4,24 L18,24 Q22,24 24,18 L28,8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <polygon points="28,8 22,8 26,14" fill="currentColor"/>
    </svg>`,
  },
  {
    id: "bracket",
    label: "BRACKET",
    desc: "Split trajectory, multiple vectors",
    icon: `<svg viewBox="0 0 32 32" width="32" height="32">
      <line x1="4" y1="16" x2="12" y2="16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <line x1="12" y1="16" x2="28" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="12" y1="16" x2="28" y2="16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-dasharray="3 2"/>
      <line x1="12" y1="16" x2="28" y2="26" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <polygon points="28,6 24,4 24,10" fill="currentColor" opacity="0.7"/>
      <polygon points="28,26 24,24 24,28" fill="currentColor" opacity="0.7"/>
    </svg>`,
  },
];

class MunitionConfigGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";

    // Current selections
    this._warhead = DEFAULTS.warhead_type;
    this._guidance = DEFAULTS.guidance_mode;
    this._profile = DEFAULTS.flight_profile;

    // Launcher type from weapon-controls state
    this._launcherType = "torpedo";

    // Publish initial config to window for weapon-controls to read
    this._publishConfig();
  }

  connectedCallback() {
    this._render();
    this._subscribe();
    this._bindEvents();

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

  _readState() {
    const weapons = stateManager.getWeapons();

    // Detect launcher type from weapon-controls' toggle state.
    // weapon-controls stores this on the element, but we can also
    // infer from which ammo type is loaded. Check the global config.
    const program = weapons?.munition_program;
    if (program) {
      // Sync selections from server state if a program exists
      if (program.warhead_type && program.warhead_type !== this._warhead) {
        this._warhead = program.warhead_type;
        this._updateSelections();
      }
      if (program.guidance_mode && program.guidance_mode !== this._guidance) {
        this._guidance = program.guidance_mode;
        this._updateSelections();
      }
      if (program.flight_profile && program.flight_profile !== this._profile) {
        this._profile = program.flight_profile;
        this._updateSelections();
      }
    }

    // Detect launcher type: read from weapon-controls component or
    // fall back to checking missile/torpedo ammo availability
    const wcEl = document.querySelector("weapon-controls");
    if (wcEl && wcEl._launcherType) {
      const newType = wcEl._launcherType;
      if (newType !== this._launcherType) {
        this._launcherType = newType;
        this._updateProfileVisibility();
      }
    }
  }

  _publishConfig() {
    window._munitionConfig = {
      warhead_type: this._warhead,
      guidance_mode: this._guidance,
      flight_profile: this._profile,
    };
  }

  _sendProgram() {
    this._publishConfig();

    // Determine munition_type from launcher type
    const munitionType = this._launcherType === "missile" ? "missile" : "torpedo";

    const params = {
      munition_type: munitionType,
      warhead_type: this._warhead,
      guidance_mode: this._guidance,
    };

    // Only include flight_profile for missiles (torpedoes use direct/evasive
    // which is set differently, but the server accepts it regardless)
    if (this._launcherType === "missile") {
      params.flight_profile = this._profile;
    } else {
      params.flight_profile = "direct";
    }

    wsClient.sendShipCommand("program_munition", params);
  }

  _bindEvents() {
    const root = this.shadowRoot;

    root.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-option]");
      if (!btn) return;

      const group = btn.dataset.group;
      const value = btn.dataset.option;

      // Don't allow selecting disabled options
      if (btn.disabled) return;

      if (group === "warhead") {
        this._warhead = value;
      } else if (group === "guidance") {
        this._guidance = value;
      } else if (group === "profile") {
        this._profile = value;
      }

      this._updateSelections();
      this._sendProgram();
    });
  }

  _updateSelections() {
    const root = this.shadowRoot;
    if (!root) return;

    // Weapon damage restricts available options
    const dmg = getDegradation("weapons");

    // Update active states for all option buttons
    root.querySelectorAll("[data-option]").forEach((btn) => {
      const group = btn.dataset.group;
      const value = btn.dataset.option;
      let isActive = false;
      let isDisabled = false;

      if (group === "warhead") isActive = value === this._warhead;
      else if (group === "guidance") {
        isActive = value === this._guidance;
        // >50% damage: disable "smart" guidance
        if (dmg > 0.5 && value === "smart") isDisabled = true;
        // >75% damage: only "dumb" guidance available
        if (dmg > 0.75 && value !== "dumb") isDisabled = true;
      } else if (group === "profile") {
        isActive = value === this._profile;
        // >75% damage: only "direct" flight profile available
        if (dmg > 0.75 && value !== "direct") isDisabled = true;
      }

      btn.classList.toggle("active", isActive && !isDisabled);
      btn.disabled = isDisabled;
      btn.style.opacity = isDisabled ? "0.3" : "";
      btn.title = isDisabled ? "Weapons too damaged" : "";
    });
  }

  _updateProfileVisibility() {
    const root = this.shadowRoot;
    if (!root) return;
    const profileRow = root.getElementById("profile-row");
    if (profileRow) {
      profileRow.style.display = this._launcherType === "missile" ? "" : "none";
    }
  }

  _render() {
    const ACCENT = "#4488ff";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: 'Share Tech Mono', 'Fira Code', monospace;
          color: #dde;
        }

        .config-panel {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 8px;
        }

        .row-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 1.5px;
          color: #889;
          margin-bottom: 2px;
        }

        .option-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .option-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          padding: 8px 10px;
          min-width: 72px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s ease;
          color: #99a;
          flex: 1;
          max-width: 120px;
        }

        .option-btn:hover {
          background: rgba(68, 136, 255, 0.08);
          border-color: rgba(68, 136, 255, 0.3);
          color: #cce;
        }

        .option-btn.active {
          background: rgba(68, 136, 255, 0.15);
          border-color: ${ACCENT};
          color: #fff;
          box-shadow: 0 0 12px rgba(68, 136, 255, 0.25),
                      inset 0 0 8px rgba(68, 136, 255, 0.1);
        }

        .option-btn .icon {
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .option-btn .icon svg {
          width: 28px;
          height: 28px;
        }

        .option-btn .name {
          font-size: 11px;
          font-weight: bold;
          letter-spacing: 0.5px;
        }

        .option-btn .desc {
          font-size: 9px;
          color: #778;
          text-align: center;
          line-height: 1.3;
        }

        .option-btn.active .desc {
          color: #99b;
        }

        /* Responsive: stack vertically on narrow screens */
        @media (max-width: 480px) {
          .option-btn {
            min-width: 60px;
            padding: 6px 4px;
          }
          .option-btn .desc {
            display: none;
          }
        }
      </style>

      <div class="config-panel">
        <div>
          <div class="row-label">Warhead Type</div>
          <div class="option-row">
            ${WARHEADS.map(
              (w) => `
              <button class="option-btn ${w.id === this._warhead ? "active" : ""}"
                      data-group="warhead" data-option="${w.id}"
                      title="${w.desc}">
                <div class="icon">${w.icon}</div>
                <div class="name">${w.label}</div>
                <div class="desc">${w.desc}</div>
              </button>
            `
            ).join("")}
          </div>
        </div>

        <div>
          <div class="row-label">Guidance Mode</div>
          <div class="option-row">
            ${GUIDANCE_MODES.map(
              (g) => `
              <button class="option-btn ${g.id === this._guidance ? "active" : ""}"
                      data-group="guidance" data-option="${g.id}"
                      title="${g.desc}">
                <div class="icon">${g.icon}</div>
                <div class="name">${g.label}</div>
                <div class="desc">${g.desc}</div>
              </button>
            `
            ).join("")}
          </div>
        </div>

        <div id="profile-row" style="${this._launcherType === "missile" ? "" : "display:none"}">
          <div class="row-label">Flight Profile <span style="color:#556">(missiles only)</span></div>
          <div class="option-row">
            ${FLIGHT_PROFILES.map(
              (p) => `
              <button class="option-btn ${p.id === this._profile ? "active" : ""}"
                      data-group="profile" data-option="${p.id}"
                      title="${p.desc}">
                <div class="icon">${p.icon}</div>
                <div class="name">${p.label}</div>
                <div class="desc">${p.desc}</div>
              </button>
            `
            ).join("")}
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define("munition-config-game", MunitionConfigGame);
