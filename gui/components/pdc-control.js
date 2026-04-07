/**
 * PDC (Point Defense Cannon) Controls
 * Sub-component of weapon-controls: PDC mode selector (auto/manual/priority/
 * network/hold_fire) and incoming threat mini-list for PRIORITY mode.
 *
 * Receives state via update() from parent weapon-controls orchestrator.
 * Does NOT subscribe to stateManager directly.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getWeaponControlsCSS } from "./weapon-controls-styles.js";

class PdcControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._pdcMode = "auto";
  }

  connectedCallback() {
    this.render();
    this._setupInteraction();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${getWeaponControlsCSS("shared")}
        ${getWeaponControlsCSS("pdc")}
      </style>
      <div class="weapon-group">
        <div class="group-title">Point Defense</div>
        <div class="pdc-mode-group" id="pdc-mode-group" data-testid="pdc-mode-group">
          <button class="pdc-mode-btn active" data-mode="auto" data-testid="pdc-auto">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>AUTO</span>
          </button>
          <button class="pdc-mode-btn" data-mode="manual" data-testid="pdc-manual">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>MANUAL</span>
          </button>
          <button class="pdc-mode-btn" data-mode="priority" data-testid="pdc-priority">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>PRIORITY</span>
          </button>
          <button class="pdc-mode-btn" data-mode="network" data-testid="pdc-network">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>NETWORK</span>
          </button>
          <button class="pdc-mode-btn" data-mode="hold_fire" data-testid="pdc-hold">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>HOLD</span>
          </button>
        </div>

        <!-- Incoming threat mini-list: visible when PRIORITY mode active -->
        <div class="pdc-threat-list" id="pdc-threat-list" style="display:none;">
          <div class="threat-list-header">INCOMING THREATS</div>
          <div class="threat-list-items" id="threat-list-items">
            <div class="threat-empty">No incoming threats</div>
          </div>
        </div>
      </div>
    `;
  }

  _setupInteraction() {
    // PDC mode buttons
    this.shadowRoot.getElementById("pdc-mode-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".pdc-mode-btn");
      if (btn) {
        this._setPdcMode(btn.dataset.mode);
      }
    });
  }

  /**
   * Called by parent weapon-controls on each display tick.
   * @param {object} params
   * @param {object} params.weapons - Weapons telemetry slice
   * @param {object} params.combat - Combat telemetry slice
   * @param {object} params.ship - Ship state slice
   */
  update({ weapons, combat, ship }) {
    const currentPdcMode = weapons?.pdc_mode || combat?.pdc_mode || "auto";
    this._pdcMode = currentPdcMode;

    this.shadowRoot.querySelectorAll(".pdc-mode-btn").forEach((btn) => {
      const isActive = btn.dataset.mode === currentPdcMode;
      btn.classList.toggle("active", isActive);
      if (btn.dataset.mode === "hold_fire") {
        btn.classList.toggle("hold-fire", isActive);
      }
    });

    // Incoming threat list -- show only in PRIORITY mode
    this._updateThreatList(currentPdcMode, ship, weapons, combat);
  }

  /** @returns {string} Current PDC mode */
  get pdcMode() {
    return this._pdcMode;
  }

  /**
   * Send set_pdc_mode command to server.
   * @param {string} mode
   */
  async _setPdcMode(mode) {
    try {
      await wsClient.sendShipCommand("set_pdc_mode", { mode });
    } catch (error) {
      console.error("Set PDC mode failed:", error);
    }
  }

  /**
   * Update the incoming threat mini-list below PDC mode buttons.
   * Filters active munitions targeting our ship.
   * In PRIORITY mode, threats are clickable to reorder engagement priority.
   */
  _updateThreatList(pdcMode, ship, weapons, combat) {
    const listEl = this.shadowRoot.getElementById("pdc-threat-list");
    if (!listEl) return;

    // Only show in PRIORITY mode
    const showList = pdcMode === "priority";
    listEl.style.display = showList ? "" : "none";
    if (!showList) return;

    const itemsEl = this.shadowRoot.getElementById("threat-list-items");
    if (!itemsEl) return;

    // Read all in-flight munitions from top-level telemetry
    const allMunitions = stateManager.getTorpedoes() || [];
    const ourId = ship?.id || ship?.ship_id || "";

    // Filter: only munitions targeting us
    const incoming = allMunitions.filter((m) => m.alive && m.target === ourId);

    // Current server priority order
    const priorityIds = weapons?.pdc_priority_targets || combat?.pdc_priority_targets || [];

    if (incoming.length === 0) {
      itemsEl.innerHTML = '<div class="threat-empty">No incoming threats</div>';
      return;
    }

    // Sort: prioritized first (in order), then by ETA ascending
    incoming.sort((a, b) => {
      const aIdx = priorityIds.indexOf(a.id);
      const bIdx = priorityIds.indexOf(b.id);
      if (aIdx !== -1 && bIdx !== -1) return aIdx - bIdx;
      if (aIdx !== -1) return -1;
      if (bIdx !== -1) return 1;
      return (a.eta ?? 999) - (b.eta ?? 999);
    });

    // Build threat items
    itemsEl.innerHTML = "";
    incoming.forEach((threat) => {
      const priIdx = priorityIds.indexOf(threat.id);
      const isPrioritized = priIdx !== -1;
      const typeLabel = threat.munition_type || "torpedo";
      const rangeKm = (threat.distance / 1000).toFixed(1);
      const etaStr = threat.eta != null ? `${threat.eta.toFixed(0)}s` : "--";

      const item = document.createElement("div");
      item.className = `threat-item${isPrioritized ? " prioritized" : ""}`;
      item.dataset.threatId = threat.id;
      item.title = "Click to toggle priority";

      item.innerHTML = `
        ${isPrioritized ? `<span class="threat-priority-num">${priIdx + 1}</span>` : ""}
        <span class="threat-type ${typeLabel}">${typeLabel.substring(0, 4).toUpperCase()}</span>
        <span class="threat-range">${rangeKm} km</span>
        <span class="threat-eta">${etaStr}</span>
      `;

      // Click to toggle this threat in the priority queue
      item.addEventListener("click", () => this._toggleThreatPriority(threat.id, weapons, combat));

      itemsEl.appendChild(item);
    });
  }

  /**
   * Toggle a threat in/out of the PDC priority queue and send the updated order.
   * @param {string} threatId
   * @param {object} weapons - Weapons telemetry
   * @param {object} combat - Combat telemetry
   */
  async _toggleThreatPriority(threatId, weapons, combat) {
    const current = [...(weapons?.pdc_priority_targets || combat?.pdc_priority_targets || [])];

    const idx = current.indexOf(threatId);
    if (idx !== -1) {
      current.splice(idx, 1);
    } else {
      current.push(threatId);
    }

    try {
      await wsClient.sendShipCommand("set_pdc_priority", { torpedo_ids: current });
    } catch (error) {
      console.error("Set PDC priority failed:", error);
    }
  }
}

customElements.define("pdc-control", PdcControl);
export { PdcControl };
