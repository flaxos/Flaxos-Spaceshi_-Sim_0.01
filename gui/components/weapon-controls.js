/**
 * Weapon Fire Controls — Orchestrator
 * Tactical station fire control: coordinates railgun, PDC, launcher (torpedo/
 * missile), and fire authorization sub-components.
 *
 * Uses commands: designate_target, request_solution, fire_railgun,
 * set_pdc_mode, launch_torpedo, launch_missile, assess_damage
 *
 * Sub-components (rendered inside this Shadow DOM):
 *   <fire-authorization>  — ammo HUD, arcade buttons, CPU-ASSIST auth cards
 *   <railgun-control>     — per-mount railgun fire buttons
 *   <pdc-control>         — PDC mode selector + threat list
 *   <launcher-control>    — torpedo/missile toggle, salvo, profile, fire
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getWeaponControlsCSS } from "./weapon-controls-styles.js";
// Sub-components — imported for side-effect registration
import "./railgun-control.js";
import "./pdc-control.js";
import "./launcher-control.js";
import "./fire-authorization.js";

class WeaponControls extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._assessmentData = null;
    this._tier = window.controlTier || "arcade";
  }

  /**
   * Expose launcher type for external consumers (e.g. munition-config-game.js).
   * Delegates to the launcher-control sub-component.
   * @returns {string} "torpedo" or "missile"
   */
  get _launcherType() {
    const launcher = this.shadowRoot?.querySelector("launcher-control");
    return launcher?.launcherType || "torpedo";
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

    // Tier-change listener: re-render weapon controls per tier
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._applyTier();
    };
    document.addEventListener("tier-change", this._tierHandler);
    // Apply tier on first connect
    this._applyTier();
  }

  disconnectedCallback() {
    if (this._unsubWeapons) {
      this._unsubWeapons();
      this._unsubWeapons = null;
    }
    if (this._unsubTargeting) {
      this._unsubTargeting();
      this._unsubTargeting = null;
    }
    if (this._contactSelectedHandler) {
      document.removeEventListener("contact-selected", this._contactSelectedHandler);
      this._contactSelectedHandler = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    const update = () => { this._updateDisplay(); };
    this._unsubWeapons = stateManager.subscribe("weapons", update);
    this._unsubTargeting = stateManager.subscribe("targeting", update);
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${getWeaponControlsCSS("all")}
      </style>

      <!-- Fire authorization: ammo HUD, arcade buttons, CPU-ASSIST cards -->
      <fire-authorization></fire-authorization>

      <!-- Target lock -->
      <div class="weapon-group target-lock-row">
        <div class="group-title">Target Lock</div>
        <button class="lock-btn" id="lock-btn" data-testid="lock-btn">
          LOCK TARGET
        </button>
      </div>

      <!-- Railgun controls -->
      <div class="weapon-group" id="railgun-group">
        <railgun-control></railgun-control>
        <div class="auth-row">
          <button class="auth-btn" id="auth-railgun" data-weapon="railgun" data-testid="auth-railgun"
                  title="Authorize continuous railgun fire when conditions are met">
            <span class="auth-icon">&#x1f512;</span> AUTH
          </button>
        </div>
        <div class="auth-conditions" id="auth-cond-railgun"></div>
      </div>

      <!-- PDC controls -->
      <pdc-control></pdc-control>

      <!-- Launcher controls (torpedo + missile) -->
      <launcher-control></launcher-control>

      <!-- Damage assessment -->
      <div class="weapon-group">
        <div class="group-title">Damage Assessment</div>
        <button class="assess-btn" id="assess-btn" data-testid="assess-btn">
          ASSESS TARGET DAMAGE
        </button>
        <div id="assessment-results"></div>
      </div>

      <!-- Cease fire -->
      <div class="weapon-group">
        <button class="cease-fire-btn" id="cease-fire-btn" data-testid="cease-fire-btn">CEASE FIRE</button>
      </div>
    `;
  }

  /**
   * Apply tier class to :host and toggle tier-specific element visibility.
   * MANUAL: individual mount fire buttons only, raw ammo count, no solution preview.
   * RAW: per-mount status with solution data, ammo, heat, charge state. (default, all controls visible)
   * ARCADE: grouped fire buttons (RAILGUN/TORPEDO/MISSILE), confidence gate, ammo as percentage.
   * CPU-ASSIST: authorize toggles per weapon type, auto-fires when conditions met.
   */
  _applyTier() {
    this.classList.remove("tier-manual", "tier-raw", "tier-arcade", "tier-cpu-assist");
    this.classList.add(`tier-${this._tier}`);
    this._updateDisplay();
  }

  _setupInteraction() {
    // Lock/Unlock target
    this.shadowRoot.getElementById("lock-btn").addEventListener("click", () => {
      this._toggleTargetLock();
    });

    // Railgun authorization toggle
    this.shadowRoot.getElementById("auth-railgun").addEventListener("click", () => {
      const fireAuth = this.shadowRoot.querySelector("fire-authorization");
      if (fireAuth) {
        const launcher = this.shadowRoot.querySelector("launcher-control");
        fireAuth.toggleAuth(
          "railgun",
          launcher?.salvoSize || 1,
          launcher?.missileProfile || "direct"
        );
      }
    });

    // Listen for toggle-auth events from launcher-control
    this.shadowRoot.addEventListener("toggle-auth", (e) => {
      const fireAuth = this.shadowRoot.querySelector("fire-authorization");
      if (fireAuth) {
        const launcher = this.shadowRoot.querySelector("launcher-control");
        fireAuth.toggleAuth(
          e.detail.weapon,
          launcher?.salvoSize || 1,
          launcher?.missileProfile || "direct"
        );
      }
    });

    // Listen for arcade-fire events from fire-authorization
    this.shadowRoot.addEventListener("arcade-fire", (e) => {
      const { weapon } = e.detail;
      if (weapon === "railgun") {
        // Fire first ready railgun mount
        const weapons = stateManager.getWeapons();
        const truthWeapons = weapons?.truth_weapons || {};
        const railgun = Object.entries(truthWeapons).find(
          ([id, w]) => id.startsWith("railgun") && w.solution?.ready_to_fire && !w.reloading && (w.ammo ?? 0) > 0
        );
        if (railgun) {
          wsClient.sendShipCommand("fire_railgun", { mount_id: railgun[0] });
        }
      } else if (weapon === "torpedo") {
        const cfg = window._munitionConfig || {};
        const params = { profile: "direct" };
        if (cfg.warhead_type) params.warhead_type = cfg.warhead_type;
        if (cfg.guidance_mode) params.guidance_mode = cfg.guidance_mode;
        wsClient.sendShipCommand("launch_torpedo", params);
      } else if (weapon === "missile") {
        wsClient.sendShipCommand("launch_salvo", {
          count: 1,
          munition_type: "missile",
          profile: "direct",
          stagger_ms: 100,
        });
      }
    });

    // Assess damage
    this.shadowRoot.getElementById("assess-btn").addEventListener("click", () => {
      this._assessDamage();
    });

    // Cease fire -- also de-authorizes all weapons
    this.shadowRoot.getElementById("cease-fire-btn").addEventListener("click", () => {
      this._ceaseFire();
    });
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const weapons = stateManager.getWeapons();
    const combat = stateManager.getCombat();
    const ship = stateManager.getShipState();

    // Determine lock state
    const lockState = targeting?.lock_state || "none";
    const lockedTarget = targeting?.locked_target || null;
    const hasLock = lockedTarget != null && lockState !== "none";

    // Update target lock button
    const lockBtn = this.shadowRoot.getElementById("lock-btn");
    if (hasLock) {
      lockBtn.classList.add("locked");
      const stateLabel = lockState === "locked" ? "LOCKED" : lockState.toUpperCase();
      lockBtn.textContent = `${stateLabel}: ${lockedTarget}`;
    } else {
      lockBtn.classList.remove("locked");
      lockBtn.textContent = "LOCK TARGET";
    }

    // Delegate to sub-components
    const fireAuth = this.shadowRoot.querySelector("fire-authorization");
    const railgun = this.shadowRoot.querySelector("railgun-control");
    const pdc = this.shadowRoot.querySelector("pdc-control");
    const launcher = this.shadowRoot.querySelector("launcher-control");

    if (fireAuth) {
      fireAuth.update({ weapons, targeting, hasLock, ship });
    }

    if (railgun) {
      railgun.update({ weapons, targeting, hasLock });
    }

    if (pdc) {
      pdc.update({ weapons, combat, ship });
    }

    if (launcher) {
      launcher.setWeaponsData(weapons);
      launcher.update({
        weapons,
        targeting,
        hasLock,
        authorized: fireAuth?.authorized || {},
      });
    }

    // Update railgun authorization button visuals (lives in this shadow DOM)
    this._updateRailgunAuth(weapons, hasLock, fireAuth?.authorized || {});

    // Auto-execute queue (server-authoritative, kept as no-op)
    // _processAutoExecute is now handled server-side.

    // Assess button - needs a lock
    const assessBtn = this.shadowRoot.getElementById("assess-btn");
    assessBtn.disabled = !hasLock;

    // Render assessment data if available
    this._renderAssessment();
  }

  /**
   * Update railgun auth button visuals and conditions checklist.
   * This button lives in the orchestrator's shadow DOM (not in railgun-control)
   * because it shares the auth-row pattern with launcher auth buttons.
   */
  _updateRailgunAuth(weapons, hasLock, authorized) {
    const truthWeapons = weapons?.truth_weapons || {};
    const authRailgun = this.shadowRoot.getElementById("auth-railgun");
    const condRailgun = this.shadowRoot.getElementById("auth-cond-railgun");
    if (!authRailgun || !condRailgun) return;

    const isAuthorized = authorized.railgun || false;
    authRailgun.classList.toggle("authorized", isAuthorized);
    authRailgun.querySelector(".auth-icon").textContent = isAuthorized ? "\u{1f513}" : "\u{1f512}";
    authRailgun.title = isAuthorized
      ? "Click to de-authorize railgun auto-fire"
      : "Authorize continuous railgun fire when conditions are met";

    // Railgun conditions
    const railguns = Object.entries(truthWeapons).filter(([id]) => id.startsWith("railgun"));
    const anyRailgunReady = railguns.some(([, w]) => w.solution?.ready_to_fire && !w.reloading);
    const anyRailgunAmmo = railguns.some(([, w]) => (w.ammo ?? 0) > 0);

    if (isAuthorized) {
      condRailgun.classList.add("visible");
      condRailgun.innerHTML = this._buildConditionsHtml([
        { label: "LOCK", met: hasLock },
        { label: "SOLUTION", met: anyRailgunReady },
        { label: "AMMO", met: anyRailgunAmmo },
      ]);
    } else {
      condRailgun.classList.remove("visible");
    }
  }

  /**
   * Build the HTML for a conditions checklist.
   * @param {Array<{label: string, met: boolean, pending?: boolean}>} conditions
   * @returns {string}
   */
  _buildConditionsHtml(conditions) {
    return conditions.map((c) => {
      let cls = c.met ? "met" : (c.pending ? "pending" : "unmet");
      let icon = c.met ? "\u2713" : (c.pending ? "\u23F3" : "\u2717");
      return `<span class="auth-cond ${cls}">${c.label} ${icon}</span>`;
    }).join("");
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
      await Promise.all([
        wsClient.sendShipCommand("cease_fire", {}),
        wsClient.sendShipCommand("set_pdc_mode", { mode: "hold_fire" }),
      ]);
    } catch (error) {
      console.error("Cease fire failed:", error);
    }
  }
}

customElements.define("weapon-controls", WeaponControls);
export { WeaponControls };
