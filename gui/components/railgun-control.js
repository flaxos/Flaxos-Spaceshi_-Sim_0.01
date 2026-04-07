/**
 * Railgun Fire Controls
 * Sub-component of weapon-controls: per-mount railgun fire buttons,
 * charge state display, and firing solution hints.
 *
 * Receives state via update() from parent weapon-controls orchestrator.
 * Does NOT subscribe to stateManager directly.
 */

import { wsClient } from "../js/ws-client.js";
import { getWeaponControlsCSS } from "./weapon-controls-styles.js";

class RailgunControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    this.render();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${getWeaponControlsCSS("shared")}
        ${getWeaponControlsCSS("railgun")}
      </style>
      <div class="weapon-group" id="railgun-group">
        <div class="group-title">Railgun</div>
        <div id="railgun-mounts"></div>
        <div class="fire-hint" id="railgun-hint"></div>
      </div>
    `;
  }

  /**
   * Called by parent weapon-controls on each display tick.
   * @param {object} params
   * @param {object} params.weapons - Weapons telemetry slice
   * @param {object} params.targeting - Targeting telemetry slice
   * @param {boolean} params.hasLock - Whether a target lock is active
   */
  update({ weapons, targeting, hasLock }) {
    this._updateRailgunMounts(weapons, targeting, hasLock);
  }

  /**
   * Render per-mount railgun fire buttons with charge state and solution hints.
   */
  _updateRailgunMounts(weapons, targeting, hasLock) {
    const mountsContainer = this.shadowRoot.getElementById("railgun-mounts");
    const hintEl = this.shadowRoot.getElementById("railgun-hint");
    if (!mountsContainer || !hintEl) return;

    const truthWeapons = weapons?.truth_weapons || {};
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
      // Surface the firing solution reason as a tooltip so the player
      // knows WHY the fire button is disabled (arc, range, cycling, etc.)
      const reason = w.solution?.reason || "";
      const tooltip = disabled && reason ? ` title="${reason}"` : "";

      // Charge state indicator for railgun capacitor
      const chargeTime = w.charge_time ?? 0;
      const chargeState = w.charge_state ?? "idle";
      const chargePct = Math.round((w.charge_progress ?? 0) * 100);
      let chargeLabel = "";
      if (chargeTime > 0 && chargeState === "charging") {
        chargeLabel = ` [${chargePct}%]`;
      }

      html += `
        <button class="fire-btn railgun-btn" data-mount="${mountId}" ${disabled}${tooltip}
                data-testid="fire-${mountId}">
          ${displayName} (${ammo})${chargeLabel}
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

    // Hint -- show specific reason when solution exists but isn't ready
    if (!hasLock) {
      hintEl.textContent = "Lock target to fire";
    } else {
      const anyReady = railguns.some(([, w]) => w.solution?.ready_to_fire);
      const anyCharging = railguns.some(
        ([, w]) => (w.charge_time ?? 0) > 0 && w.charge_state === "charging"
      );
      if (anyReady) {
        hintEl.textContent = "";
      } else if (anyCharging) {
        hintEl.textContent = "Capacitor charging...";
      } else {
        // Show the most informative reason from any railgun's solution
        const reasons = railguns
          .map(([, w]) => w.solution?.reason)
          .filter(Boolean);
        const arcReason = reasons.find((r) => r.includes("arc"));
        hintEl.textContent = arcReason || reasons[0] || "Waiting for firing solution";
      }
    }
  }

  /**
   * Send fire_railgun command to server.
   * @param {string} mountId - e.g. "railgun_1"
   */
  async _fireRailgun(mountId) {
    try {
      await wsClient.sendShipCommand("fire_railgun", { mount_id: mountId });
    } catch (error) {
      console.error("Fire railgun failed:", error);
    }
  }
}

customElements.define("railgun-control", RailgunControl);
export { RailgunControl };
