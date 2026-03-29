/**
 * Weapon Fire Controls
 * Tactical station fire control: railgun fire, PDC mode, torpedo launch,
 * target designation, and damage assessment.
 *
 * Uses commands: designate_target, request_solution, fire_railgun,
 * set_pdc_mode, launch_torpedo, assess_damage
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class WeaponControls extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._pdcMode = "auto";
    this._assessmentData = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();

    this._contactSelectedHandler = (e) => {
      this._selectedContact = e.detail.contactId;
      this._updateDisplay();
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    if (this._contactSelectedHandler) {
      document.removeEventListener("contact-selected", this._contactSelectedHandler);
      this._contactSelectedHandler = null;
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

        /* Pulse animation for fire-ready buttons */
        @keyframes fire-ready-pulse {
          0%, 100% { box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3); }
          50% { box-shadow: 0 4px 20px rgba(255, 68, 68, 0.55), 0 0 8px rgba(255, 68, 68, 0.2); }
        }

        .fire-btn {
          width: 100%;
          padding: 14px 16px;
          border-radius: 8px;
          font-size: 1.1rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          cursor: pointer;
          min-height: 60px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: all 0.1s ease;
          font-family: inherit;
        }

        /* Disabled / not-ready state for all fire buttons */
        .fire-btn:disabled {
          background: var(--bg-input, #1a1a24);
          color: var(--text-dim, #555566);
          border: 2px solid var(--border-default, #2a2a3a);
          cursor: not-allowed;
          box-shadow: none;
          animation: none;
        }

        .railgun-btn {
          background: var(--status-critical, #ff4444);
          border: 2px solid var(--status-critical, #ff4444);
          color: white;
          box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3);
        }

        .railgun-btn:not(:disabled) {
          animation: fire-ready-pulse 2s ease-in-out infinite;
        }

        .railgun-btn:hover:not(:disabled) {
          filter: brightness(1.15);
          transform: translateY(-1px);
        }

        .railgun-btn:active:not(:disabled) {
          transform: translateY(0);
        }

        .torpedo-btn {
          background: var(--status-critical, #ff4444);
          border: 2px solid var(--status-critical, #ff4444);
          color: white;
          box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3);
        }

        .torpedo-btn:not(:disabled) {
          animation: fire-ready-pulse 2s ease-in-out infinite;
        }

        .torpedo-btn:hover:not(:disabled) {
          filter: brightness(1.15);
          transform: translateY(-1px);
        }

        .torpedo-btn:active:not(:disabled) {
          transform: translateY(0);
        }

        .torpedo-count {
          font-size: 0.75rem;
          opacity: 0.9;
        }

        /* PDC Mode Selector */
        .pdc-mode-group {
          display: flex;
          gap: 4px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          padding: 4px;
        }

        .pdc-mode-btn {
          flex: 1;
          padding: 8px 6px;
          border: 1px solid transparent;
          border-radius: 6px;
          background: transparent;
          color: var(--text-dim, #555566);
          font-family: inherit;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          cursor: pointer;
          transition: all 0.15s ease;
          min-height: 36px;
        }

        .pdc-mode-btn:hover {
          color: var(--text-primary, #e0e0e0);
          background: rgba(255, 255, 255, 0.05);
        }

        .pdc-mode-btn.active {
          color: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.1);
        }

        .pdc-mode-btn.active.hold-fire {
          color: var(--status-warning, #ffaa00);
          border-color: var(--status-warning, #ffaa00);
          background: rgba(255, 170, 0, 0.1);
        }

        .pdc-mode-label {
          display: flex;
          align-items: center;
          gap: 6px;
          justify-content: center;
        }

        .pdc-indicator {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: currentColor;
          flex-shrink: 0;
        }

        /* Assess damage button */
        .assess-btn {
          width: 100%;
          padding: 10px 16px;
          background: rgba(0, 170, 255, 0.08);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 6px;
          color: var(--status-info, #00aaff);
          font-family: inherit;
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          min-height: 40px;
          transition: background 0.15s ease;
        }

        .assess-btn:hover:not(:disabled) {
          background: rgba(0, 170, 255, 0.15);
        }

        .assess-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        /* Assessment results */
        .assessment-results {
          margin-top: 8px;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .assessment-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 3px 0;
          font-size: 0.75rem;
        }

        .assessment-label {
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          font-size: 0.65rem;
          letter-spacing: 0.3px;
        }

        .assessment-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
        }

        .assessment-value.nominal { color: var(--status-nominal, #00ff88); }
        .assessment-value.impaired { color: var(--status-warning, #ffaa00); }
        .assessment-value.critical { color: var(--status-critical, #ff4444); }
        .assessment-value.destroyed { color: var(--text-dim, #555566); text-decoration: line-through; }
        .assessment-value.unknown { color: var(--text-dim, #555566); }

        .assessment-confidence {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          margin-top: 6px;
          padding-top: 6px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .cease-fire-btn {
          width: 100%;
          padding: 12px 16px;
          background: transparent;
          border: 2px solid var(--status-warning, #ffaa00);
          border-radius: 8px;
          color: var(--status-warning, #ffaa00);
          font-family: inherit;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 44px;
          transition: all 0.1s ease;
        }

        .cease-fire-btn:hover {
          background: rgba(255, 170, 0, 0.1);
        }

        .fire-hint {
          margin-top: 6px;
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-align: center;
          font-style: italic;
          min-height: 1.2em;
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
          font-family: inherit;
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

        .warning-box {
          margin-top: 8px;
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

        .railgun-mount-row {
          display: flex;
          gap: 6px;
          margin-bottom: 6px;
        }

        .railgun-mount-row .fire-btn {
          flex: 1;
          padding: 12px 8px;
          font-size: 0.85rem;
          min-height: 52px;
        }
      </style>

      <div class="weapon-group target-lock-row">
        <div class="group-title">Target Lock</div>
        <button class="lock-btn" id="lock-btn" data-testid="lock-btn">
          LOCK TARGET
        </button>
      </div>

      <div class="weapon-group" id="railgun-group">
        <div class="group-title">Railgun</div>
        <div id="railgun-mounts"></div>
        <div class="fire-hint" id="railgun-hint"></div>
      </div>

      <div class="weapon-group">
        <div class="group-title">Point Defense</div>
        <div class="pdc-mode-group" id="pdc-mode-group" data-testid="pdc-mode-group">
          <button class="pdc-mode-btn active" data-mode="auto" data-testid="pdc-auto">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>AUTO</span>
          </button>
          <button class="pdc-mode-btn" data-mode="manual" data-testid="pdc-manual">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>MANUAL</span>
          </button>
          <button class="pdc-mode-btn" data-mode="hold_fire" data-testid="pdc-hold">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>HOLD</span>
          </button>
        </div>
      </div>

      <div class="weapon-group">
        <div class="group-title">Torpedoes</div>
        <button class="fire-btn torpedo-btn" id="torpedo-btn" data-testid="torpedo-btn">
          FIRE TORPEDO
          <span class="torpedo-count" id="torpedo-count">(0)</span>
        </button>
        <div class="warning-box hidden" id="no-lock-warning">
          No target lock - torpedoes will fire dumb
        </div>
      </div>

      <div class="weapon-group">
        <div class="group-title">Damage Assessment</div>
        <button class="assess-btn" id="assess-btn" data-testid="assess-btn">
          ASSESS TARGET DAMAGE
        </button>
        <div id="assessment-results"></div>
      </div>

      <div class="weapon-group">
        <button class="cease-fire-btn" id="cease-fire-btn" data-testid="cease-fire-btn">CEASE FIRE</button>
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
      this._launchTorpedo();
    });

    // PDC mode buttons
    this.shadowRoot.getElementById("pdc-mode-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".pdc-mode-btn");
      if (btn) {
        this._setPdcMode(btn.dataset.mode);
      }
    });

    // Assess damage
    this.shadowRoot.getElementById("assess-btn").addEventListener("click", () => {
      this._assessDamage();
    });

    // Cease fire
    this.shadowRoot.getElementById("cease-fire-btn").addEventListener("click", () => {
      this._ceaseFire();
    });
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const weapons = stateManager.getWeapons();
    const combat = stateManager.getCombat();
    const ship = stateManager.getShipState();

    // Update target lock button
    const lockBtn = this.shadowRoot.getElementById("lock-btn");
    const lockState = targeting?.lock_state || "none";
    const lockedTarget = targeting?.locked_target || null;
    const hasLock = lockedTarget != null && lockState !== "none";

    if (hasLock) {
      lockBtn.classList.add("locked");
      const stateLabel = lockState === "locked" ? "LOCKED" : lockState.toUpperCase();
      lockBtn.textContent = `${stateLabel}: ${lockedTarget}`;
    } else {
      lockBtn.classList.remove("locked");
      lockBtn.textContent = "LOCK TARGET";
    }

    // No-lock warning
    const noLockWarning = this.shadowRoot.getElementById("no-lock-warning");
    noLockWarning.classList.toggle("hidden", hasLock);

    // Railgun mounts
    this._updateRailgunMounts(combat, targeting, hasLock);

    // PDC mode from combat state
    const currentPdcMode = combat?.pdc_mode || "auto";
    this._pdcMode = currentPdcMode;
    this.shadowRoot.querySelectorAll(".pdc-mode-btn").forEach((btn) => {
      const isActive = btn.dataset.mode === currentPdcMode;
      btn.classList.toggle("active", isActive);
      if (btn.dataset.mode === "hold_fire") {
        btn.classList.toggle("hold-fire", isActive);
      }
    });

    // Torpedo count
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const torpedoCount = torpedoData.loaded ?? torpedoData.count ?? 0;
    const torpedoBtn = this.shadowRoot.getElementById("torpedo-btn");
    const countSpan = this.shadowRoot.getElementById("torpedo-count");
    countSpan.textContent = `(${torpedoCount})`;
    torpedoBtn.disabled = torpedoCount <= 0 || !hasLock;

    // Assess button - needs a lock
    const assessBtn = this.shadowRoot.getElementById("assess-btn");
    assessBtn.disabled = !hasLock;

    // Render assessment data if available
    this._renderAssessment();
  }

  _updateRailgunMounts(combat, targeting, hasLock) {
    const mountsContainer = this.shadowRoot.getElementById("railgun-mounts");
    const hintEl = this.shadowRoot.getElementById("railgun-hint");
    const truthWeapons = combat?.truth_weapons || {};

    const railguns = Object.entries(truthWeapons).filter(([id]) => id.startsWith("railgun"));

    if (railguns.length === 0) {
      mountsContainer.innerHTML = "";
      hintEl.textContent = "No railgun mounts";
      return;
    }

    let html = '<div class="railgun-mount-row">';
    for (const [mountId, w] of railguns) {
      const ammo = w.ammo ?? 0;
      const ready = w.solution?.ready_to_fire && ammo > 0 && !w.reloading;
      const disabled = !ready || !hasLock ? "disabled" : "";
      const displayName = mountId.replace(/_/g, " ").toUpperCase();

      html += `
        <button class="fire-btn railgun-btn" data-mount="${mountId}" ${disabled}
                data-testid="fire-${mountId}">
          ${displayName} (${ammo})
        </button>
      `;
    }
    html += "</div>";

    mountsContainer.innerHTML = html;

    // Bind fire handlers
    mountsContainer.querySelectorAll(".railgun-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._fireRailgun(btn.dataset.mount);
      });
    });

    // Hint
    if (!hasLock) {
      hintEl.textContent = "Lock target to fire";
    } else {
      const anyReady = railguns.some(([, w]) => w.solution?.ready_to_fire);
      hintEl.textContent = anyReady ? "" : "Waiting for firing solution";
    }
  }

  _renderAssessment() {
    const container = this.shadowRoot.getElementById("assessment-results");
    if (!this._assessmentData || !this._assessmentData.ok) {
      container.innerHTML = "";
      return;
    }

    const data = this._assessmentData;
    const subsystems = data.subsystems || {};
    const quality = data.assessment_quality ?? 0;

    let html = '<div class="assessment-results">';
    for (const [name, info] of Object.entries(subsystems)) {
      const healthPct = info.health != null ? `${Math.round(info.health * 100)}%` : "???";
      const status = info.status || "unknown";
      html += `
        <div class="assessment-row">
          <span class="assessment-label">${name}</span>
          <span class="assessment-value ${status}">${healthPct} ${status.toUpperCase()}</span>
        </div>
      `;
    }
    html += `
      <div class="assessment-confidence">
        Sensor confidence: ${Math.round(quality * 100)}%
      </div>
    </div>`;

    container.innerHTML = html;
  }

  async _toggleTargetLock() {
    const targeting = stateManager.getTargeting();
    const lockState = targeting?.lock_state || "none";
    const lockedTarget = targeting?.locked_target || null;
    const hasLock = lockedTarget != null && lockState !== "none";

    if (hasLock) {
      try {
        await wsClient.sendShipCommand("unlock_target", {});
        this._assessmentData = null;
      } catch (error) {
        console.error("Unlock target failed:", error);
      }
    } else {
      // Use the selected contact from sensor panel
      const contactId = this._selectedContact;
      if (contactId) {
        try {
          await wsClient.sendShipCommand("designate_target", { contact_id: contactId });
        } catch (error) {
          console.error("Designate target failed:", error);
        }
      }
    }
  }

  async _fireRailgun(mountId) {
    try {
      await wsClient.sendShipCommand("fire_railgun", { mount_id: mountId });
    } catch (error) {
      console.error("Fire railgun failed:", error);
    }
  }

  async _setPdcMode(mode) {
    try {
      await wsClient.sendShipCommand("set_pdc_mode", { mode });
    } catch (error) {
      console.error("Set PDC mode failed:", error);
    }
  }

  async _launchTorpedo() {
    try {
      await wsClient.sendShipCommand("launch_torpedo", {});
    } catch (error) {
      console.error("Launch torpedo failed:", error);
    }
  }

  async _assessDamage() {
    try {
      const response = await wsClient.sendShipCommand("assess_damage", {});
      if (response && response.ok) {
        this._assessmentData = response;
        this._renderAssessment();
      }
    } catch (error) {
      console.error("Assess damage failed:", error);
    }
  }

  async _ceaseFire() {
    try {
      await wsClient.sendShipCommand("set_pdc_mode", { mode: "hold_fire" });
    } catch (error) {
      console.error("Cease fire failed:", error);
    }
  }
}

customElements.define("weapon-controls", WeaponControls);
export { WeaponControls };
