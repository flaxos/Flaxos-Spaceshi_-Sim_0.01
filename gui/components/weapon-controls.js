/**
 * Weapon Fire Controls
 * Fire torpedo, PDC control, cease fire
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class WeaponControls extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._pdcEnabled = false;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .weapon-group {
          margin-bottom: 16px;
        }

        .weapon-group:last-child {
          margin-bottom: 0;
        }

        .group-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .fire-btn {
          width: 100%;
          padding: 14px 16px;
          border-radius: 8px;
          font-size: 0.9rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 50px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: all 0.1s ease;
        }

        .torpedo-btn {
          background: linear-gradient(135deg, #ff4444 0%, #cc3333 100%);
          border: none;
          color: white;
          box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3);
        }

        .torpedo-btn:hover:not(:disabled) {
          filter: brightness(1.1);
          transform: translateY(-1px);
        }

        .torpedo-btn:active:not(:disabled) {
          transform: translateY(0);
        }

        .torpedo-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          filter: grayscale(0.5);
        }

        .torpedo-count {
          font-size: 0.75rem;
          opacity: 0.9;
        }

        .pdc-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
        }

        .pdc-label {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .pdc-indicator {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: var(--status-offline, #555566);
          transition: all 0.2s ease;
        }

        .pdc-indicator.active {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 8px var(--status-nominal, #00ff88);
        }

        .pdc-status {
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
        }

        .toggle-switch {
          position: relative;
          width: 48px;
          height: 28px;
          background: var(--bg-primary, #0a0a0f);
          border-radius: 14px;
          cursor: pointer;
          transition: background 0.2s ease;
        }

        .toggle-switch.active {
          background: var(--status-nominal, #00ff88);
        }

        .toggle-switch::before {
          content: '';
          position: absolute;
          top: 4px;
          left: 4px;
          width: 20px;
          height: 20px;
          background: var(--text-primary, #e0e0e0);
          border-radius: 50%;
          transition: transform 0.2s ease;
        }

        .toggle-switch.active::before {
          transform: translateX(20px);
          background: var(--bg-primary, #0a0a0f);
        }

        .cease-fire-btn {
          width: 100%;
          padding: 12px 16px;
          background: transparent;
          border: 2px solid var(--status-warning, #ffaa00);
          border-radius: 8px;
          color: var(--status-warning, #ffaa00);
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 44px;
          transition: all 0.1s ease;
        }

        .cease-fire-btn:hover {
          background: rgba(255, 170, 0, 0.1);
        }

        .warning-box {
          margin-top: 12px;
          padding: 10px 12px;
          background: rgba(255, 170, 0, 0.1);
          border: 1px solid var(--status-warning, #ffaa00);
          border-radius: 6px;
          font-size: 0.75rem;
          color: var(--status-warning, #ffaa00);
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .warning-box.hidden {
          display: none;
        }

        .target-lock-row {
          margin-bottom: 12px;
        }

        .lock-btn {
          width: 100%;
          padding: 12px 16px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.85rem;
          cursor: pointer;
          min-height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }

        .lock-btn:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .lock-btn.locked {
          background: rgba(0, 170, 255, 0.1);
          border-color: var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
        }

        .unlock-btn {
          background: transparent;
          border: 1px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }

        .unlock-btn:hover {
          border-color: var(--text-secondary, #888899);
          color: var(--text-secondary, #888899);
        }
      </style>

      <div class="weapon-group target-lock-row">
        <div class="group-title">Target Lock</div>
        <button class="lock-btn" id="lock-btn">
          🎯 LOCK TARGET
        </button>
      </div>

      <div class="weapon-group">
        <div class="group-title">Torpedoes</div>
        <button class="fire-btn torpedo-btn" id="torpedo-btn">
          🚀 FIRE TORPEDO
          <span class="torpedo-count" id="torpedo-count">(10)</span>
        </button>
        <div class="warning-box hidden" id="no-lock-warning">
          ⚠ No target lock — torpedoes will fire dumb
        </div>
      </div>

      <div class="weapon-group">
        <div class="group-title">Point Defense</div>
        <div class="pdc-row">
          <div class="pdc-label">
            <span class="pdc-indicator" id="pdc-indicator"></span>
            <span class="pdc-status" id="pdc-status">PDC AUTO</span>
          </div>
          <div class="toggle-switch" id="pdc-toggle"></div>
        </div>
      </div>

      <div class="weapon-group">
        <button class="cease-fire-btn" id="cease-fire-btn">⛔ CEASE FIRE</button>
      </div>
    `;
  }

  _setupInteraction() {
    // Lock/Unlock target
    this.shadowRoot.getElementById("lock-btn").addEventListener("click", () => {
      this._toggleTargetLock();
    });

    // Fire torpedo
    this.shadowRoot.getElementById("torpedo-btn").addEventListener("click", () => {
      this._fireTorpedo();
    });

    // PDC toggle
    this.shadowRoot.getElementById("pdc-toggle").addEventListener("click", () => {
      this._togglePDC();
    });

    // Cease fire
    this.shadowRoot.getElementById("cease-fire-btn").addEventListener("click", () => {
      this._ceaseFire();
    });
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const weapons = stateManager.getWeapons();

    // Update target lock button
    const lockBtn = this.shadowRoot.getElementById("lock-btn");
    const hasLock = targeting && (targeting.locked || targeting.target_locked || targeting.target_id);

    if (hasLock) {
      lockBtn.classList.add("locked");
      lockBtn.innerHTML = `◉ LOCKED: ${targeting.target_id || "TARGET"}`;
    } else {
      lockBtn.classList.remove("locked");
      lockBtn.innerHTML = "🎯 LOCK TARGET";
    }

    // Update no-lock warning
    const noLockWarning = this.shadowRoot.getElementById("no-lock-warning");
    noLockWarning.classList.toggle("hidden", hasLock);

    // Update torpedo count
    const torpedoData = weapons.torpedoes || weapons.torpedo || {};
    const torpedoCount = torpedoData.loaded ?? torpedoData.count ?? 10;
    const torpedoBtn = this.shadowRoot.getElementById("torpedo-btn");
    const countSpan = this.shadowRoot.getElementById("torpedo-count");
    countSpan.textContent = `(${torpedoCount})`;
    torpedoBtn.disabled = torpedoCount <= 0;

    // Update PDC status
    const pdcData = weapons.pdc || weapons.point_defense || {};
    const pdcStatus = pdcData.status || "offline";
    const pdcIndicator = this.shadowRoot.getElementById("pdc-indicator");
    const pdcStatusText = this.shadowRoot.getElementById("pdc-status");
    const pdcToggle = this.shadowRoot.getElementById("pdc-toggle");

    this._pdcEnabled = pdcStatus === "tracking" || pdcStatus === "firing" || pdcStatus === "active" || pdcStatus === "ready";
    pdcIndicator.classList.toggle("active", this._pdcEnabled);
    pdcStatusText.textContent = this._pdcEnabled ? "PDC ACTIVE" : "PDC STANDBY";
    pdcToggle.classList.toggle("active", this._pdcEnabled);
  }

  async _toggleTargetLock() {
    const targeting = stateManager.getTargeting();
    const hasLock = targeting && (targeting.locked || targeting.target_locked || targeting.target_id);

    if (hasLock) {
      // Unlock target
      try {
        await wsClient.sendShipCommand("unlock_target", {});
      } catch (error) {
        console.error("Unlock target failed:", error);
      }
    } else {
      // Try to lock selected contact
      const sensorContacts = document.getElementById("sensor-contacts");
      const selectedContact = sensorContacts?.getSelectedContact?.();

      if (selectedContact) {
        try {
          await wsClient.sendShipCommand("lock_target", { target_id: selectedContact });
        } catch (error) {
          console.error("Target lock failed:", error);
        }
      }
    }
  }

  async _fireTorpedo() {
    try {
      await wsClient.sendShipCommand("fire_weapon", { weapon_type: "torpedo" });
    } catch (error) {
      console.error("Fire torpedo failed:", error);
    }
  }

  async _togglePDC() {
    try {
      if (this._pdcEnabled) {
        // Cease fire on PDC
        await wsClient.sendShipCommand("fire_weapon", { weapon_type: "pdc", cease: true });
      } else {
        // Enable PDC auto-fire
        await wsClient.sendShipCommand("fire_weapon", { weapon_type: "pdc", auto: true });
      }
    } catch (error) {
      console.error("PDC toggle failed:", error);
    }
  }

  async _ceaseFire() {
    try {
      await wsClient.sendShipCommand("fire_weapon", { cease_all: true });
    } catch (error) {
      console.error("Cease fire failed:", error);
    }
  }
}

customElements.define("weapon-controls", WeaponControls);
export { WeaponControls };
