/**
 * Subsystem Selector
 * Lets the player select which subsystem to target on a locked contact.
 * Sends set_target_subsystem command to the server on selection.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

/** Targetable subsystems with display metadata */
const SUBSYSTEMS = [
  { id: "drive",   label: "DRIVE",   icon: ">>", description: "Propulsion / Engines" },
  { id: "rcs",     label: "RCS",     icon: "<>", description: "Attitude Control" },
  { id: "sensors", label: "SENSORS", icon: "()", description: "Detection Systems" },
  { id: "weapons", label: "WEAPONS", icon: "/\\", description: "Weapon Hardpoints" },
  { id: "reactor", label: "REACTOR", icon: "**", description: "Power Generation" },
];

class SubsystemSelector extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  /**
   * Send subsystem selection command to the server.
   * @param {string} subsystem - Subsystem id (e.g. "drive")
   */
  _selectSubsystem(subsystem) {
    wsClient.sendShipCommand("set_target_subsystem", { subsystem }).catch((err) => {
      console.error("Failed to set target subsystem:", err);
    });
  }

  /**
   * Return a CSS color class name based on health fraction.
   * Green >75%, amber 25-75%, red <25%, grey if unknown.
   */
  _healthClass(health) {
    if (health === null || health === undefined) return "unknown";
    if (health > 0.75) return "nominal";
    if (health > 0.25) return "impaired";
    return "critical";
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 16px;
        }

        .no-lock {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px;
          color: var(--text-dim, #555566);
        }

        .no-lock-icon {
          font-size: 2rem;
          margin-bottom: 8px;
          opacity: 0.5;
        }

        .no-lock-text {
          font-size: 0.9rem;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 10px;
        }

        .subsystem-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .subsystem-btn {
          display: flex;
          align-items: center;
          gap: 10px;
          width: 100%;
          padding: 8px 10px;
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          background: rgba(0, 0, 0, 0.2);
          color: var(--text-primary, #e0e0e0);
          cursor: pointer;
          font-family: inherit;
          font-size: 0.8rem;
          transition: border-color 0.15s, background 0.15s;
        }

        .subsystem-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          border-color: var(--text-secondary, #888899);
        }

        .subsystem-btn.selected {
          border-color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.1);
          box-shadow: 0 0 8px rgba(255, 68, 68, 0.15);
        }

        .subsystem-icon {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          width: 24px;
          text-align: center;
          color: var(--text-secondary, #888899);
          flex-shrink: 0;
        }

        .subsystem-btn.selected .subsystem-icon {
          color: var(--status-critical, #ff4444);
        }

        .subsystem-info {
          flex: 1;
          min-width: 0;
        }

        .subsystem-name {
          font-weight: 600;
          font-size: 0.78rem;
          letter-spacing: 0.3px;
        }

        .subsystem-desc {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          margin-top: 1px;
        }

        .health-bar-container {
          width: 48px;
          flex-shrink: 0;
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 2px;
        }

        .health-pct {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
        }

        .health-bar {
          width: 100%;
          height: 4px;
          background: var(--bg-input, #1a1a24);
          border-radius: 2px;
          overflow: hidden;
        }

        .health-fill {
          height: 100%;
          border-radius: 2px;
          transition: width 0.3s ease;
        }

        /* Health color states */
        .health-pct.nominal,
        .health-fill.nominal {
          color: var(--status-nominal, #00ff88);
          background: var(--status-nominal, #00ff88);
        }

        .health-pct.impaired,
        .health-fill.impaired {
          color: var(--status-warning, #ffaa00);
          background: var(--status-warning, #ffaa00);
        }

        .health-pct.critical,
        .health-fill.critical {
          color: var(--status-critical, #ff4444);
          background: var(--status-critical, #ff4444);
        }

        .health-pct.unknown,
        .health-fill.unknown {
          color: var(--text-dim, #555566);
          background: var(--text-dim, #555566);
        }
      </style>

      <div id="content">
        <div class="no-lock">
          <div class="no-lock-icon">+</div>
          <div class="no-lock-text">Lock a target to select subsystem</div>
        </div>
      </div>
    `;
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const content = this.shadowRoot.getElementById("content");

    const hasLock =
      targeting && (targeting.locked || targeting.target_locked || targeting.target_id);

    if (!hasLock) {
      content.innerHTML = `
        <div class="no-lock">
          <div class="no-lock-icon">+</div>
          <div class="no-lock-text">Lock a target to select subsystem</div>
        </div>
      `;
      return;
    }

    const selectedSubsystem = targeting.target_subsystem || null;
    const targetSubsystems = targeting.target_subsystems || {};

    content.innerHTML = `
      <div class="section-title">Target Subsystem</div>
      <div class="subsystem-list">
        ${SUBSYSTEMS.map((sys) => {
          const isSelected = selectedSubsystem === sys.id;
          const healthData = targetSubsystems[sys.id];
          const health = healthData?.health ?? null;
          const hClass = this._healthClass(health);
          const healthPct =
            health !== null ? `${Math.round(health * 100)}%` : "---";
          const healthWidth = health !== null ? `${health * 100}%` : "0%";

          return `
            <button
              class="subsystem-btn${isSelected ? " selected" : ""}"
              data-subsystem="${sys.id}"
              title="${sys.description}"
            >
              <span class="subsystem-icon">${sys.icon}</span>
              <span class="subsystem-info">
                <span class="subsystem-name">${sys.label}</span>
                <span class="subsystem-desc">${sys.description}</span>
              </span>
              <span class="health-bar-container">
                <span class="health-pct ${hClass}">${healthPct}</span>
                <span class="health-bar">
                  <span
                    class="health-fill ${hClass}"
                    style="width: ${healthWidth}"
                  ></span>
                </span>
              </span>
            </button>
          `;
        }).join("")}
      </div>
    `;

    // Bind click handlers via event delegation on the list container
    const list = content.querySelector(".subsystem-list");
    if (list) {
      list.addEventListener("click", (e) => {
        const btn = e.target.closest(".subsystem-btn");
        if (btn) {
          this._selectSubsystem(btn.dataset.subsystem);
        }
      });
    }
  }
}

customElements.define("subsystem-selector", SubsystemSelector);
export { SubsystemSelector };
