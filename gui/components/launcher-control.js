/**
 * Launcher Controls (Torpedo + Missile)
 * Sub-component of weapon-controls: torpedo/missile type toggle,
 * salvo size selector, flight profile selector, fire button,
 * and MANUAL tier munition programming + unguided fire.
 *
 * Receives state via update() from parent weapon-controls orchestrator.
 * Does NOT subscribe to stateManager directly.
 */

import { wsClient } from "../js/ws-client.js";
import { getWeaponControlsCSS } from "./weapon-controls-styles.js";

class LauncherControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._launcherType = "torpedo";
    this._salvoSize = 1;
    this._missileProfile = "direct";
    this._salvoInProgress = false;
  }

  connectedCallback() {
    this.render();
    this._setupInteraction();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${getWeaponControlsCSS("shared")}
        ${getWeaponControlsCSS("launcher")}
        ${getWeaponControlsCSS("authorization")}
      </style>
      <div class="weapon-group">
        <div class="group-title">Launcher</div>
        <div class="launcher-type-group" id="launcher-type-group" data-testid="launcher-type-group">
          <button class="launcher-type-btn active" data-type="torpedo" data-testid="launcher-torpedo">
            <span class="launcher-type-label"><span class="launcher-type-indicator"></span>TORPEDO</span>
          </button>
          <button class="launcher-type-btn" data-type="missile" data-testid="launcher-missile">
            <span class="launcher-type-label"><span class="launcher-type-indicator"></span>MISSILE</span>
          </button>
        </div>

        <!-- Missile-only options: salvo size + flight profile -->
        <div class="missile-options" id="missile-options">
          <div class="salvo-row">
            <span class="salvo-label">Salvo</span>
            <div class="salvo-group" id="salvo-group" data-testid="salvo-group">
              <button class="salvo-btn active" data-salvo="1">1x</button>
              <button class="salvo-btn" data-salvo="2">2x</button>
              <button class="salvo-btn" data-salvo="4">4x</button>
              <button class="salvo-btn" data-salvo="6">6x</button>
              <button class="salvo-btn" data-salvo="8">8x</button>
              <button class="salvo-btn" data-salvo="all">ALL</button>
            </div>
          </div>
          <div class="profile-row">
            <span class="profile-label">Profile</span>
            <div class="profile-group" id="profile-group" data-testid="profile-group">
              <button class="profile-btn active" data-profile="direct">DIRECT</button>
              <button class="profile-btn" data-profile="evasive">EVASIVE</button>
              <button class="profile-btn" data-profile="terminal_pop">T-POP</button>
              <button class="profile-btn" data-profile="bracket">BRACKET</button>
            </div>
          </div>
        </div>

        <div class="fire-auth-row" id="launcher-fire-row" style="position: relative;">
          <button class="fire-btn torpedo-btn" id="launcher-fire-btn" data-testid="launcher-fire-btn">
            FIRE TORPEDO
            <span class="torpedo-count" id="launcher-count">(0)</span>
          </button>
          <button class="auth-btn" id="auth-torpedo" data-weapon="torpedo" data-testid="auth-torpedo"
                  title="Authorize auto-fire when conditions are met (single fire)">
            <span class="auth-icon">&#x1f512;</span>
          </button>
          <button class="auth-btn" id="auth-missile" data-weapon="missile" data-testid="auth-missile"
                  title="Authorize auto-fire salvo when conditions are met" style="display: none;">
            <span class="auth-icon">&#x1f512;</span>
          </button>
        </div>
        <div class="auth-conditions" id="auth-cond-torpedo"></div>
        <div class="auth-conditions" id="auth-cond-missile"></div>
        <div class="warning-box hidden" id="no-lock-warning">
          No target lock - ordnance will fire dumb
        </div>

        <!-- MANUAL tier: munition programming interface -->
        <div class="manual-only" id="munition-program-section">
          <div class="group-title" style="margin-top: 12px;">MUNITION PROGRAMMING</div>
          <div class="manual-solution-grid" style="display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; font-size: 0.72rem; padding: 8px;">
            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">GUIDANCE</span>
            <select id="prog-guidance" style="background: var(--bg-input, #1a1a24); color: var(--text-primary, #e0e0e0); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; font-size: 0.72rem; font-family: var(--font-mono);">
              <option value="dumb">DUMB (no corrections)</option>
              <option value="guided" selected>GUIDED (PN gain 4.0)</option>
              <option value="smart">SMART (PN gain 6.0)</option>
            </select>

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">PN GAIN</span>
            <input id="prog-pn-gain" type="number" min="1.0" max="8.0" step="0.5" value="4.0"
              style="background: var(--bg-input, #1a1a24); color: var(--text-primary); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; width: 60px; font-family: var(--font-mono); font-size: 0.72rem;">

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">WARHEAD</span>
            <select id="prog-warhead" style="background: var(--bg-input, #1a1a24); color: var(--text-primary); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; font-size: 0.72rem; font-family: var(--font-mono);">
              <option value="fragmentation" selected>FRAGMENTATION</option>
              <option value="shaped_charge">SHAPED CHARGE</option>
              <option value="emp">EMP</option>
            </select>

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">FUSE DIST</span>
            <span style="display:flex;align-items:center;gap:4px;">
              <input id="prog-fuse" type="number" min="5" max="200" step="5" value="50"
                style="background: var(--bg-input, #1a1a24); color: var(--text-primary); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; width: 50px; font-family: var(--font-mono); font-size: 0.72rem;">
              <span style="color: var(--text-dim); font-size: 0.65rem;">m</span>
            </span>

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">DATALINK</span>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;">
              <input id="prog-datalink" type="checkbox" checked style="accent-color: var(--tier-accent, #ff8800);">
              <span style="color: var(--text-primary); font-size: 0.72rem;">Active</span>
            </label>
          </div>
          <button id="prog-upload-btn" style="
            width: 100%; padding: 6px; margin-top: 6px;
            background: rgba(255, 136, 0, 0.1); border: 1px solid var(--tier-accent, #ff8800);
            color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
            font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
            letter-spacing: 1px; cursor: pointer; border-radius: 2px;
          ">UPLOAD PROGRAM</button>
          <div id="prog-status" style="font-size: 0.65rem; color: var(--text-dim); margin-top: 4px; text-align: center;"></div>
        </div>

        <!-- MANUAL tier: dumb-fire (no targeting lock required) -->
        <div class="manual-only" id="unguided-fire-section" style="margin-top: 12px;">
          <div class="group-title">UNGUIDED FIRE (BORE-SIGHT)</div>
          <div style="display: flex; gap: 6px; flex-wrap: wrap;">
            <button id="fire-unguided-railgun" style="
              flex: 1; min-width: 70px; padding: 8px; cursor: pointer;
              background: rgba(255, 136, 0, 0.08); border: 1px solid var(--tier-accent, #ff8800);
              color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
              font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.5px; border-radius: 2px;
            ">RAILGUN</button>
            <button id="fire-unguided-pdc" style="
              flex: 1; min-width: 70px; padding: 8px; cursor: pointer;
              background: rgba(255, 136, 0, 0.08); border: 1px solid var(--tier-accent, #ff8800);
              color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
              font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.5px; border-radius: 2px;
            ">PDC BURST</button>
            <button id="fire-unguided-torpedo" style="
              flex: 1; min-width: 70px; padding: 8px; cursor: pointer;
              background: rgba(255, 136, 0, 0.08); border: 1px solid var(--tier-accent, #ff8800);
              color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
              font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.5px; border-radius: 2px;
            ">TORPEDO</button>
            <button id="fire-unguided-missile" style="
              flex: 1; min-width: 70px; padding: 8px; cursor: pointer;
              background: rgba(255, 136, 0, 0.08); border: 1px solid var(--tier-accent, #ff8800);
              color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
              font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.5px; border-radius: 2px;
            ">MISSILE</button>
          </div>
          <div style="font-size: 0.6rem; color: var(--text-dim); margin-top: 4px; text-align: center; font-style: italic;">
            Fires along ship heading -- no lock required
          </div>
        </div>
      </div>
    `;
  }

  _setupInteraction() {
    // Launcher type toggle (torpedo / missile)
    this.shadowRoot.getElementById("launcher-type-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".launcher-type-btn");
      if (btn) {
        this._setLauncherType(btn.dataset.type);
      }
    });

    // Fire launcher (torpedo or missile based on selected type)
    this.shadowRoot.getElementById("launcher-fire-btn").addEventListener("click", () => {
      if (this._launcherType === "missile") {
        this._fireMissileSalvo();
      } else {
        this._fireLauncher();
      }
    });

    // Missile salvo size selector
    this.shadowRoot.getElementById("salvo-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".salvo-btn");
      if (btn) {
        this._setSalvoSize(btn.dataset.salvo);
      }
    });

    // Missile flight profile selector
    this.shadowRoot.getElementById("profile-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".profile-btn");
      if (btn) {
        this._setMissileProfile(btn.dataset.profile);
      }
    });

    // Authorization toggle buttons
    this.shadowRoot.querySelectorAll(".auth-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.dispatchEvent(new CustomEvent("toggle-auth", {
          detail: { weapon: btn.dataset.weapon },
          bubbles: true,
          composed: true,
        }));
      });
    });

    // MANUAL tier: munition programming upload
    const progUploadBtn = this.shadowRoot.getElementById("prog-upload-btn");
    if (progUploadBtn) {
      progUploadBtn.addEventListener("click", () => this._uploadMunitionProgram());
    }

    // MANUAL tier: guidance mode updates PN gain default
    const progGuidance = this.shadowRoot.getElementById("prog-guidance");
    if (progGuidance) {
      progGuidance.addEventListener("change", () => {
        const pnInput = this.shadowRoot.getElementById("prog-pn-gain");
        if (!pnInput) return;
        const defaults = { dumb: 0, guided: 4.0, smart: 6.0 };
        pnInput.value = defaults[progGuidance.value] ?? 4.0;
      });
    }

    // MANUAL tier: unguided fire buttons
    const unguidedHandlers = [
      ["fire-unguided-railgun", "railgun"],
      ["fire-unguided-pdc", "pdc"],
      ["fire-unguided-torpedo", "torpedo"],
      ["fire-unguided-missile", "missile"],
    ];
    for (const [elId, weaponType] of unguidedHandlers) {
      const el = this.shadowRoot.getElementById(elId);
      if (el) {
        el.addEventListener("click", () => {
          wsClient.sendShipCommand("fire_unguided", { weapon_type: weaponType });
        });
      }
    }
  }

  /**
   * Called by parent weapon-controls on each display tick.
   * @param {object} params
   * @param {object} params.weapons - Weapons telemetry slice
   * @param {object} params.targeting - Targeting telemetry slice
   * @param {boolean} params.hasLock - Whether a target lock is active
   * @param {object} params.authorized - { torpedo: bool, missile: bool }
   */
  update({ weapons, targeting, hasLock, authorized }) {
    const isMissile = this._launcherType === "missile";

    // Launcher type toggle visual state
    this.shadowRoot.querySelectorAll(".launcher-type-btn").forEach((btn) => {
      const isActive = btn.dataset.type === this._launcherType;
      btn.classList.toggle("active", isActive);
      btn.classList.toggle("missile", isActive && btn.dataset.type === "missile");
    });

    // Show/hide missile-specific options (salvo size, flight profile)
    const missileOpts = this.shadowRoot.getElementById("missile-options");
    missileOpts.classList.toggle("visible", isMissile);

    // Show correct auth button for current launcher type
    const authTorpedo = this.shadowRoot.getElementById("auth-torpedo");
    const authMissile = this.shadowRoot.getElementById("auth-missile");
    authTorpedo.style.display = isMissile ? "none" : "";
    authMissile.style.display = isMissile ? "" : "none";

    // Salvo selector visual state
    this.shadowRoot.querySelectorAll(".salvo-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.salvo === String(this._salvoSize));
    });

    // Flight profile selector visual state
    this.shadowRoot.querySelectorAll(".profile-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.profile === this._missileProfile);
    });

    // Launcher fire button -- adapts to selected type (torpedo or missile)
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const torpedoCount = torpedoData.loaded ?? torpedoData.count ?? 0;
    const missileData = weapons?.missiles || {};
    const missileCount = missileData.loaded ?? missileData.count ?? 0;

    const fireBtn = this.shadowRoot.getElementById("launcher-fire-btn");
    const activeCount = isMissile ? missileCount : torpedoCount;

    fireBtn.disabled = activeCount <= 0 || !hasLock;

    // Switch button style and label based on launcher type
    fireBtn.classList.toggle("torpedo-btn", !isMissile);
    fireBtn.classList.toggle("missile-btn", isMissile);
    fireBtn.textContent = "";

    if (isMissile) {
      const effectiveSalvo = this._getEffectiveSalvoSize(missileCount);
      fireBtn.append(document.createTextNode(`FIRE MISSILE x${effectiveSalvo} `));
    } else {
      fireBtn.append(document.createTextNode("FIRE TORPEDO "));
    }
    const newCountSpan = document.createElement("span");
    newCountSpan.className = "torpedo-count";
    newCountSpan.id = "launcher-count";
    newCountSpan.textContent = `(${activeCount} remaining)`;
    fireBtn.appendChild(newCountSpan);

    // Update authorization button visuals
    this._updateAuthButtons(weapons, hasLock, authorized || {});

    // No-lock warning
    const noLockWarning = this.shadowRoot.getElementById("no-lock-warning");
    noLockWarning.classList.toggle("hidden", hasLock);
  }

  /**
   * Update authorization button visuals and conditions checklists
   * for torpedo and missile auth buttons.
   */
  _updateAuthButtons(weapons, hasLock, authorized) {
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const missileData = weapons?.missiles || {};

    // -- Torpedo auth --
    const authTorpedoBtn = this.shadowRoot.getElementById("auth-torpedo");
    const condTorpedo = this.shadowRoot.getElementById("auth-cond-torpedo");
    authTorpedoBtn.classList.toggle("authorized", authorized.torpedo);
    authTorpedoBtn.querySelector(".auth-icon").textContent = authorized.torpedo ? "\u{1f513}" : "\u{1f512}";

    const torpedoCount = torpedoData.loaded ?? torpedoData.count ?? 0;

    if (authorized.torpedo) {
      condTorpedo.classList.add("visible");
      condTorpedo.innerHTML = this._buildConditionsHtml([
        { label: "LOCK", met: hasLock },
        { label: "AMMO", met: torpedoCount > 0 },
        { label: "COOLDOWN", met: (torpedoData.cooldown ?? 0) <= 0, pending: (torpedoData.cooldown ?? 0) > 0 },
      ]);
    } else {
      condTorpedo.classList.remove("visible");
    }

    // -- Missile auth --
    const authMissileBtn = this.shadowRoot.getElementById("auth-missile");
    const condMissile = this.shadowRoot.getElementById("auth-cond-missile");
    authMissileBtn.classList.toggle("authorized", authorized.missile);
    authMissileBtn.querySelector(".auth-icon").textContent = authorized.missile ? "\u{1f513}" : "\u{1f512}";

    const missileCount = missileData.loaded ?? missileData.count ?? 0;

    if (authorized.missile) {
      condMissile.classList.add("visible");
      condMissile.innerHTML = this._buildConditionsHtml([
        { label: "LOCK", met: hasLock },
        { label: "AMMO", met: missileCount > 0 },
        { label: "COOLDOWN", met: (missileData.cooldown ?? 0) <= 0, pending: (missileData.cooldown ?? 0) > 0 },
      ]);
    } else {
      condMissile.classList.remove("visible");
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

  // --- Launcher type and fire logic ---

  _setLauncherType(type) {
    if (type !== "torpedo" && type !== "missile") return;
    this._launcherType = type;
    // Dispatch event so parent and munition-config-game can react
    this.dispatchEvent(new CustomEvent("launcher-type-change", {
      detail: { type },
      bubbles: true,
      composed: true,
    }));
  }

  /** @returns {string} Current launcher type ("torpedo" or "missile") */
  get launcherType() {
    return this._launcherType;
  }

  /** @returns {number|string} Current salvo size */
  get salvoSize() {
    return this._salvoSize;
  }

  /** @returns {string} Current missile flight profile */
  get missileProfile() {
    return this._missileProfile;
  }

  async _fireLauncher() {
    // Torpedo: always single fire, with profile param.
    // Read ARCADE munition config if available (set by munition-config-game).
    const cfg = window._munitionConfig || {};
    const params = { profile: "direct" };
    if (cfg.warhead_type) params.warhead_type = cfg.warhead_type;
    if (cfg.guidance_mode) params.guidance_mode = cfg.guidance_mode;
    try {
      await wsClient.sendShipCommand("launch_torpedo", params);
    } catch (error) {
      console.error("launch_torpedo failed:", error);
    }
  }

  /**
   * Fire a missile salvo via the server-side launch_salvo command.
   * Server handles staggered timing authoritatively -- no client setTimeout.
   */
  async _fireMissileSalvo() {
    const weapons = this._lastWeapons || {};
    const missileData = weapons?.missiles || {};
    const remaining = missileData.loaded ?? missileData.count ?? 0;
    if (remaining <= 0) return;

    const salvoSize = this._getEffectiveSalvoSize(remaining);
    if (salvoSize <= 0) return;

    this._salvoInProgress = true;

    // Show fire flash
    this._showFireFlash("missile");

    // Read ARCADE munition config if available (set by munition-config-game).
    const cfg = window._munitionConfig || {};
    const salvoParams = {
      count: salvoSize,
      munition_type: this._launcherType || "missile",
      profile: this._missileProfile || "direct",
      stagger_ms: 100,
    };
    if (cfg.warhead_type) salvoParams.warhead_type = cfg.warhead_type;
    if (cfg.guidance_mode) salvoParams.guidance_mode = cfg.guidance_mode;
    if (cfg.flight_profile) salvoParams.profile = cfg.flight_profile;

    try {
      await wsClient.sendShipCommand("launch_salvo", salvoParams);
    } catch (err) {
      console.error("Salvo launch failed:", err);
    } finally {
      this._salvoInProgress = false;
    }
  }

  /**
   * Resolve the effective salvo size based on the selector value and
   * the number of missiles remaining. "all" fires everything.
   * @param {number} remaining
   * @returns {number}
   */
  _getEffectiveSalvoSize(remaining) {
    if (this._salvoSize === "all") return Math.max(remaining, 0);
    const requested = parseInt(this._salvoSize, 10);
    if (isNaN(requested) || requested < 1) return 1;
    return Math.min(requested, remaining);
  }

  _setSalvoSize(value) {
    this._salvoSize = value === "all" ? "all" : parseInt(value, 10) || 1;
  }

  _setMissileProfile(profile) {
    const valid = ["direct", "evasive", "terminal_pop", "bracket"];
    if (!valid.includes(profile)) return;
    this._missileProfile = profile;
  }

  _uploadMunitionProgram() {
    const guidance = this.shadowRoot.getElementById("prog-guidance")?.value || "guided";
    const pnGain = parseFloat(this.shadowRoot.getElementById("prog-pn-gain")?.value) || 4.0;
    const warhead = this.shadowRoot.getElementById("prog-warhead")?.value || "fragmentation";
    const fuse = parseFloat(this.shadowRoot.getElementById("prog-fuse")?.value) || 50;
    const datalink = this.shadowRoot.getElementById("prog-datalink")?.checked ?? true;

    const program = {
      munition_type: this._launcherType || "torpedo",
      guidance_mode: guidance,
      pn_gain: Math.max(1.0, Math.min(8.0, pnGain)),
      warhead_type: warhead,
      fuse_distance: Math.max(5, Math.min(200, fuse)),
      datalink: datalink,
    };

    wsClient.sendShipCommand("program_munition", program);

    const statusEl = this.shadowRoot.getElementById("prog-status");
    if (statusEl) {
      statusEl.textContent = `${program.munition_type.toUpperCase()} programmed: ${guidance.toUpperCase()}, PN=${program.pn_gain}, ${warhead.toUpperCase()}, fuse=${program.fuse_distance}m`;
      statusEl.style.color = "var(--tier-accent, #ff8800)";
    }
  }

  /**
   * Brief red/orange flash on the fire area to indicate auto-fire triggered.
   * @param {string} type - "torpedo" or "missile"
   */
  _showFireFlash(type) {
    const target = this.shadowRoot.getElementById("launcher-fire-row");
    if (!target) return;

    const prevPosition = target.style.position;
    if (!prevPosition || prevPosition === "static") {
      target.style.position = "relative";
    }

    const flash = document.createElement("div");
    flash.className = "fire-flash-overlay" + (type === "missile" ? " missile" : "");
    target.appendChild(flash);

    flash.addEventListener("animationend", () => {
      flash.remove();
      if (!prevPosition || prevPosition === "static") {
        target.style.position = prevPosition || "";
      }
    });
  }

  /**
   * Cache weapons data for salvo fire (called from update).
   * @param {object} weapons
   */
  setWeaponsData(weapons) {
    this._lastWeapons = weapons;
  }
}

customElements.define("launcher-control", LauncherControl);
export { LauncherControl };
