/**
 * Fire Authorization Controls
 * Sub-component of weapon-controls: auto-fire authorization state management,
 * CPU-ASSIST auth cards, auto-tactical engagement panel, arcade grouped fire
 * buttons, and ammo/heat HUD.
 *
 * Receives state via update() from parent weapon-controls orchestrator.
 * Does NOT subscribe to stateManager directly.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getWeaponControlsCSS } from "./weapon-controls-styles.js";
import { getProposalCSS } from "../js/proposal-styles.js";

class FireAuthorization extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._authorized = { railgun: false, torpedo: false, missile: false };
    this._tier = window.controlTier || "arcade";
  }

  connectedCallback() {
    this.render();
    this._setupInteraction();

    // Tier-change listener
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
    };
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${getWeaponControlsCSS("shared")}
        ${getWeaponControlsCSS("authorization")}
        ${getWeaponControlsCSS("tier")}
        ${getWeaponControlsCSS("engagement")}
        ${getWeaponControlsCSS("ammo")}
        /* Proposal cards -- shared styles from proposal-styles.js */
        ${getProposalCSS()}
      </style>

      <!-- Auto-Tactical Engagement Panel (CPU-ASSIST tier) -->
      <div class="engagement-panel" id="engagement-panel">
        <div class="engagement-header">
          <span class="engagement-title">Auto-Tactical</span>
          <button class="engagement-toggle" id="engagement-toggle">ENABLE</button>
        </div>
        <div class="engagement-mode-group" id="engagement-mode-group">
          <button class="engagement-mode-btn weapons-free" data-mode="weapons_free">WEAPONS FREE</button>
          <button class="engagement-mode-btn" data-mode="weapons_hold">WEAPONS HOLD</button>
          <button class="engagement-mode-btn defensive" data-mode="defensive_only">DEFENSIVE</button>
        </div>
        <div id="tactical-proposals"></div>
      </div>

      <!-- ARCADE tier: grouped fire buttons (RAILGUN / TORPEDO / MISSILE) -->
      <div class="arcade-grouped-btns" id="arcade-grouped-btns">
        <button class="arcade-fire-btn railgun" id="arcade-fire-railgun" disabled>
          RAILGUN
          <span class="arcade-ammo-pct" id="arcade-rg-ammo">0%</span>
        </button>
        <button class="arcade-fire-btn torpedo" id="arcade-fire-torpedo" disabled>
          TORPEDO
          <span class="arcade-ammo-pct" id="arcade-trp-ammo">0%</span>
        </button>
        <button class="arcade-fire-btn missile" id="arcade-fire-missile" disabled>
          MISSILE
          <span class="arcade-ammo-pct" id="arcade-msl-ammo">0%</span>
        </button>
      </div>

      <!-- CPU-ASSIST tier: per-weapon-type authorize toggles -->
      <div class="cpuassist-auth-grid" id="cpuassist-auth-grid">
        <div class="cpuassist-auth-card" id="cpuassist-auth-railgun" data-weapon="railgun">
          <div class="auth-weapon-name">Railgun</div>
          <div class="auth-toggle-label">AUTHORIZE</div>
        </div>
        <div class="cpuassist-auth-card" id="cpuassist-auth-torpedo" data-weapon="torpedo">
          <div class="auth-weapon-name">Torpedo</div>
          <div class="auth-toggle-label">AUTHORIZE</div>
        </div>
        <div class="cpuassist-auth-card" id="cpuassist-auth-missile" data-weapon="missile">
          <div class="auth-weapon-name">Missile</div>
          <div class="auth-toggle-label">AUTHORIZE</div>
        </div>
      </div>

      <div class="ammo-heat-hud" id="ammo-heat-hud"></div>
    `;
  }

  _setupInteraction() {
    // ARCADE: grouped fire buttons
    this.shadowRoot.getElementById("arcade-fire-railgun").addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("arcade-fire", {
        detail: { weapon: "railgun" },
        bubbles: true,
        composed: true,
      }));
    });

    this.shadowRoot.getElementById("arcade-fire-torpedo").addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("arcade-fire", {
        detail: { weapon: "torpedo" },
        bubbles: true,
        composed: true,
      }));
    });

    this.shadowRoot.getElementById("arcade-fire-missile").addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("arcade-fire", {
        detail: { weapon: "missile" },
        bubbles: true,
        composed: true,
      }));
    });

    // CPU-ASSIST: auth card toggles
    this.shadowRoot.querySelectorAll(".cpuassist-auth-card").forEach((card) => {
      card.addEventListener("click", () => {
        this._toggleAuth(card.dataset.weapon);
      });
    });

    // Auto-tactical engagement toggle
    this.shadowRoot.getElementById("engagement-toggle").addEventListener("click", () => {
      this._toggleAutoTactical();
    });

    // Engagement mode selector
    this.shadowRoot.getElementById("engagement-mode-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".engagement-mode-btn");
      if (btn) {
        wsClient.sendShipCommand("set_engagement_rules", { mode: btn.dataset.mode });
      }
    });

    // Tactical proposal approve/deny (delegated)
    this.shadowRoot.getElementById("tactical-proposals").addEventListener("click", (e) => {
      const approveBtn = e.target.closest(".proposal-approve");
      const denyBtn = e.target.closest(".proposal-deny");
      if (approveBtn) {
        wsClient.sendShipCommand("approve_tactical", { proposal_id: approveBtn.dataset.id });
      } else if (denyBtn) {
        wsClient.sendShipCommand("deny_tactical", { proposal_id: denyBtn.dataset.id });
      }
    });
  }

  /**
   * Called by parent weapon-controls on each display tick.
   * @param {object} params
   * @param {object} params.weapons - Weapons telemetry slice
   * @param {object} params.targeting - Targeting telemetry slice
   * @param {boolean} params.hasLock - Whether a target lock is active
   * @param {object} params.ship - Ship state slice
   */
  update({ weapons, targeting, hasLock, ship }) {
    // Sync auto-fire authorization state from server telemetry
    this._syncAutoFireState(weapons);

    // Update ammo/heat HUD
    this._updateAmmoHeatHud(weapons);

    // Update railgun auth button (embedded in parent, mirrored here for cpu-assist)
    this._updateRailgunAuth(weapons, hasLock);

    // Update auto-tactical engagement panel (CPU-ASSIST tier)
    this._updateEngagementPanel(ship);

    // Tier-specific updates
    this._updateArcadeButtons(weapons, targeting, hasLock);
    this._updateCpuAssistAuthCards();
  }

  /** @returns {{ railgun: boolean, torpedo: boolean, missile: boolean }} */
  get authorized() {
    return { ...this._authorized };
  }

  /**
   * Toggle authorization for a weapon type.
   * @param {string} weapon - "railgun", "torpedo", or "missile"
   * @param {number|string} [salvoSize=1] - salvo size for missile auth
   * @param {string} [profile="direct"] - flight profile for missile auth
   */
  toggleAuth(weapon, salvoSize = 1, profile = "direct") {
    if (!this._authorized.hasOwnProperty(weapon)) return;
    if (this._authorized[weapon]) {
      wsClient.sendShipCommand("deauthorize_weapon", { weapon_type: weapon });
    } else {
      wsClient.sendShipCommand("authorize_weapon", {
        weapon_type: weapon,
        count: salvoSize,
        profile: profile,
      });
    }
  }

  // Internal toggle used by CPU-ASSIST cards
  _toggleAuth(weapon) {
    this.toggleAuth(weapon);
  }

  /**
   * Sync local _authorized state from server telemetry.
   */
  _syncAutoFireState(weapons) {
    const autoFire = weapons?.auto_fire;
    if (!autoFire || !autoFire.authorized) return;
    this._authorized.railgun = !!autoFire.authorized.railgun;
    this._authorized.torpedo = !!autoFire.authorized.torpedo;
    this._authorized.missile = !!autoFire.authorized.missile;
  }

  /**
   * Update railgun authorization visual (used from parent's railgun group).
   */
  _updateRailgunAuth(weapons, hasLock) {
    // This data is consumed by the parent to update the railgun auth button
    // in its own shadow DOM. We just keep the state synced.
  }

  /**
   * Render the compact ammo/heat summary HUD.
   */
  _updateAmmoHeatHud(weapons) {
    const hud = this.shadowRoot.getElementById("ammo-heat-hud");
    if (!hud) return;

    const truthWeapons = weapons?.truth_weapons || {};
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const missileData = weapons?.missiles || {};

    // Aggregate ammo by weapon type (railgun, pdc) from truth_weapons
    const ammoByType = {};
    let totalHeat = 0;
    let totalMaxHeat = 0;
    const reloading = [];

    for (const [mountId, w] of Object.entries(truthWeapons)) {
      const wtype = w.weapon_type || (mountId.startsWith("pdc") ? "pdc" : "railgun");
      if (!ammoByType[wtype]) {
        ammoByType[wtype] = { current: 0, capacity: 0 };
      }
      ammoByType[wtype].current += w.ammo ?? 0;
      ammoByType[wtype].capacity += w.ammo_capacity ?? 0;

      totalHeat += w.heat ?? 0;
      totalMaxHeat += w.max_heat ?? 0;

      if (w.reloading) {
        const pct = Math.round((w.reload_progress ?? 0) * 100);
        const displayName = mountId.replace(/_/g, " ").toUpperCase();
        reloading.push({ name: displayName, pct });
      }
    }

    // Torpedo/missile ammo
    const trpLoaded = torpedoData.loaded ?? torpedoData.count ?? 0;
    const trpCapacity = torpedoData.capacity ?? trpLoaded;
    const mslLoaded = missileData.loaded ?? missileData.count ?? 0;
    const mslCapacity = missileData.capacity ?? mslLoaded;

    // Torpedo/missile cooldowns count as reloading
    if ((torpedoData.cooldown ?? 0) > 0) {
      reloading.push({ name: "TORPEDO TUBE", pct: null, cooldown: torpedoData.cooldown });
    }
    if ((missileData.cooldown ?? 0) > 0) {
      reloading.push({ name: "MISSILE BAY", pct: null, cooldown: missileData.cooldown });
    }

    // If no weapons data at all, show minimal state
    const hasAnyData = Object.keys(truthWeapons).length > 0 || trpCapacity > 0 || mslCapacity > 0;
    if (!hasAnyData) {
      hud.innerHTML = `
        <div class="ammo-summary">
          <span class="ammo-item">
            <span class="ammo-label">WEAPONS</span>
            <span class="ammo-value empty">NO DATA</span>
          </span>
        </div>
      `;
      return;
    }

    // Build ammo summary items
    const ammoItems = [];
    const typeLabels = { railgun: "RG", pdc: "PDC" };

    for (const [wtype, data] of Object.entries(ammoByType)) {
      const label = typeLabels[wtype] || wtype.toUpperCase();
      const ratio = data.capacity > 0 ? data.current / data.capacity : 1;
      const colorClass = ratio <= 0 ? "empty" : ratio <= 0.15 ? "critical" : ratio <= 0.35 ? "low" : "";
      ammoItems.push(
        `<span class="ammo-item">` +
        `<span class="ammo-label">${label}:</span>` +
        `<span class="ammo-value ${colorClass}">${data.current}/${data.capacity}</span>` +
        `</span>`
      );
    }

    // Torpedoes (only show if ship has tubes)
    if (trpCapacity > 0) {
      const ratio = trpCapacity > 0 ? trpLoaded / trpCapacity : 1;
      const colorClass = ratio <= 0 ? "empty" : ratio <= 0.15 ? "critical" : ratio <= 0.35 ? "low" : "";
      ammoItems.push(
        `<span class="ammo-item">` +
        `<span class="ammo-label">TRP:</span>` +
        `<span class="ammo-value ${colorClass}">${trpLoaded}/${trpCapacity}</span>` +
        `</span>`
      );
    }

    // Missiles (only show if ship has launchers)
    if (mslCapacity > 0) {
      const ratio = mslCapacity > 0 ? mslLoaded / mslCapacity : 1;
      const colorClass = ratio <= 0 ? "empty" : ratio <= 0.15 ? "critical" : ratio <= 0.35 ? "low" : "";
      ammoItems.push(
        `<span class="ammo-item">` +
        `<span class="ammo-label">MSL:</span>` +
        `<span class="ammo-value ${colorClass}">${mslLoaded}/${mslCapacity}</span>` +
        `</span>`
      );
    }

    // Ammo line with separators
    const ammoHtml = ammoItems.join(`<span class="ammo-separator">|</span>`);

    // Heat bar (aggregate across all truth_weapons)
    let heatHtml = "";
    if (totalMaxHeat > 0) {
      const heatPct = Math.round((totalHeat / totalMaxHeat) * 100);
      const heatClass = heatPct >= 80 ? "hot" : heatPct >= 50 ? "warm" : "cool";
      heatHtml = `
        <div class="heat-bar-section">
          <div class="heat-bar-header">
            <span class="heat-bar-label">WEAPONS HEAT</span>
            <span class="heat-bar-value ${heatClass}">${Math.round(totalHeat)}/${Math.round(totalMaxHeat)}</span>
          </div>
          <div class="heat-bar-container">
            <div class="heat-bar-fill ${heatClass}" style="width: ${Math.min(heatPct, 100)}%"></div>
          </div>
        </div>
      `;
    }

    // Reload status
    let reloadHtml = "";
    if (reloading.length > 0) {
      const items = reloading.map((r) => {
        const statusText = r.pct != null
          ? `${r.name} ${r.pct}%`
          : `${r.name} ${r.cooldown.toFixed(1)}s`;
        return `<span class="reload-item"><span class="reload-indicator"></span>${statusText}</span>`;
      }).join("");
      reloadHtml = `<div class="reload-status">${items}</div>`;
    }

    hud.innerHTML = `
      <div class="ammo-summary">${ammoHtml}</div>
      ${heatHtml}
      ${reloadHtml}
    `;
  }

  /**
   * ARCADE: update grouped fire buttons with confidence gate and ammo as percentage.
   */
  _updateArcadeButtons(weapons, targeting, hasLock) {
    if (this._tier !== "arcade") return;

    const truthWeapons = weapons?.truth_weapons || {};
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const missileData = weapons?.missiles || {};
    const solutions = targeting?.solutions || {};

    // Best confidence across any weapon solution
    let bestConf = 0;
    for (const [, sol] of Object.entries(solutions)) {
      if ((sol.confidence ?? 0) > bestConf) bestConf = sol.confidence;
    }
    const confGate = hasLock && bestConf > 0.5;

    // Railgun: ammo as percentage
    const railguns = Object.entries(truthWeapons).filter(([id]) => id.startsWith("railgun"));
    let rgCurrent = 0, rgCapacity = 0;
    for (const [, w] of railguns) {
      rgCurrent += w.ammo ?? 0;
      rgCapacity += w.ammo_capacity ?? 0;
    }
    const rgPct = rgCapacity > 0 ? Math.round((rgCurrent / rgCapacity) * 100) : 0;
    const rgReady = railguns.some(([, w]) => w.solution?.ready_to_fire && !w.reloading && (w.ammo ?? 0) > 0);

    const rgBtn = this.shadowRoot.getElementById("arcade-fire-railgun");
    const rgAmmo = this.shadowRoot.getElementById("arcade-rg-ammo");
    if (rgBtn) rgBtn.disabled = !confGate || !rgReady;
    if (rgAmmo) rgAmmo.textContent = `${rgPct}%`;

    // Torpedo: ammo as percentage
    const trpLoaded = torpedoData.loaded ?? torpedoData.count ?? 0;
    const trpCapacity = torpedoData.capacity ?? trpLoaded;
    const trpPct = trpCapacity > 0 ? Math.round((trpLoaded / trpCapacity) * 100) : 0;
    const trpReady = trpLoaded > 0 && (torpedoData.cooldown ?? 0) <= 0;

    const trpBtn = this.shadowRoot.getElementById("arcade-fire-torpedo");
    const trpAmmo = this.shadowRoot.getElementById("arcade-trp-ammo");
    if (trpBtn) trpBtn.disabled = !confGate || !trpReady;
    if (trpAmmo) trpAmmo.textContent = `${trpPct}%`;

    // Missile: ammo as percentage
    const mslLoaded = missileData.loaded ?? missileData.count ?? 0;
    const mslCapacity = missileData.capacity ?? mslLoaded;
    const mslPct = mslCapacity > 0 ? Math.round((mslLoaded / mslCapacity) * 100) : 0;
    const mslReady = mslLoaded > 0 && (missileData.cooldown ?? 0) <= 0;

    const mslBtn = this.shadowRoot.getElementById("arcade-fire-missile");
    const mslAmmo = this.shadowRoot.getElementById("arcade-msl-ammo");
    if (mslBtn) mslBtn.disabled = !confGate || !mslReady;
    if (mslAmmo) mslAmmo.textContent = `${mslPct}%`;
  }

  /**
   * CPU-ASSIST: update per-weapon-type authorize card visuals.
   */
  _updateCpuAssistAuthCards() {
    if (this._tier !== "cpu-assist") return;

    for (const weapon of ["railgun", "torpedo", "missile"]) {
      const card = this.shadowRoot.getElementById(`cpuassist-auth-${weapon}`);
      if (!card) continue;
      const isAuth = this._authorized[weapon];
      card.classList.toggle("authorized", isAuth);
      const label = card.querySelector(".auth-toggle-label");
      if (label) label.textContent = isAuth ? "AUTHORIZED" : "AUTHORIZE";
    }
  }

  // --- Auto-Tactical (CPU-ASSIST tier) ---

  async _toggleAutoTactical() {
    const ship = stateManager.getShipState();
    const atState = ship?.auto_tactical;
    const enabled = atState?.enabled;

    try {
      if (enabled) {
        await wsClient.sendShipCommand("disable_auto_tactical", {});
      } else {
        await wsClient.sendShipCommand("enable_auto_tactical", {});
      }
    } catch (error) {
      console.error("Toggle auto-tactical failed:", error);
    }
  }

  _updateEngagementPanel(ship) {
    const panel = this.shadowRoot.getElementById("engagement-panel");
    if (!panel) return;

    // Show only in CPU-ASSIST tier
    const tier = window.controlTier || "raw";
    panel.classList.toggle("visible", tier === "cpu-assist");

    if (tier !== "cpu-assist") return;

    const atState = ship?.auto_tactical;
    const enabled = atState?.enabled || false;
    const mode = atState?.engagement_mode || "weapons_free";
    const proposals = atState?.proposals || [];

    // Toggle button
    const toggle = this.shadowRoot.getElementById("engagement-toggle");
    toggle.textContent = enabled ? "DISABLE" : "ENABLE";
    toggle.classList.toggle("active", enabled);

    // Mode buttons
    this.shadowRoot.querySelectorAll(".engagement-mode-btn").forEach((btn) => {
      const isActive = btn.dataset.mode === mode;
      btn.classList.toggle("active", isActive);
      btn.classList.toggle("weapons-free", isActive && btn.dataset.mode === "weapons_free");
      btn.classList.toggle("defensive", isActive && btn.dataset.mode === "defensive_only");
    });

    // Proposals
    const container = this.shadowRoot.getElementById("tactical-proposals");
    if (!enabled || proposals.length === 0) {
      container.innerHTML = enabled
        ? '<div class="no-proposals">Auto-tactical standing by — no targets in solution</div>'
        : '';
      return;
    }

    let html = '';
    for (const p of proposals) {
      const remaining = Math.max(0, p.time_remaining || 0);
      const total = p.total_time || 30;
      const timerPct = Math.min(100, (remaining / total) * 100);
      const actionLabel = p.action.replace(/_/g, " ").toUpperCase();
      const confidence = p.confidence ?? 0;
      const isUrgent = confidence > 0.8 || remaining < 5;
      const urgentClass = isUrgent ? " urgent" : "";
      const countdownClass = remaining < 5 ? " expiring" : "";
      html += `
        <div class="proposal-card${urgentClass}">
          <div class="proposal-header">
            <span class="proposal-action">${actionLabel} -- ${p.target_id || ""}</span>
            ${confidence > 0 ? `<span class="proposal-confidence">${(confidence * 100).toFixed(0)}%</span>` : ""}
            ${p.crew_efficiency != null ? `<span class="proposal-crew">Crew: ${(p.crew_efficiency * 100).toFixed(0)}%</span>` : ""}
            <span class="proposal-countdown${countdownClass}">${remaining.toFixed(1)}s</span>
          </div>
          <div class="proposal-reason">${p.reason}</div>
          <div class="proposal-timer"><div class="proposal-timer-fill" style="width:${timerPct}%"></div></div>
          <div class="proposal-actions">
            <button class="proposal-approve" data-id="${p.proposal_id}">EXECUTE</button>
            <button class="proposal-deny" data-id="${p.proposal_id}">STAND DOWN</button>
          </div>
        </div>`;
    }
    container.innerHTML = html;
  }
}

customElements.define("fire-authorization", FireAuthorization);
export { FireAuthorization };
