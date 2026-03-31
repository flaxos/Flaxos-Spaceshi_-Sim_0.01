/**
 * Damage State Manager
 * Subscribes to stateManager, reads subsystem_health each tick,
 * detects health changes ("under attack"), and dispatches events
 * that panels use to show damage visualization.
 *
 * Subsystem-to-panel mapping: each panel element has a `data-subsystem`
 * attribute (set on the wrapping <flaxos-panel>) that this manager reads.
 * Multiple panels can map to the same subsystem.
 */

import { stateManager } from "./state-manager.js";

/**
 * Map from subsystem names (as they appear in telemetry subsystem_health.subsystems)
 * to the CSS selectors of panels/components they affect.
 * Panels are identified by their custom element tag or a class on the wrapping
 * <flaxos-panel> element.
 */
const SUBSYSTEM_PANEL_MAP = {
  propulsion: [
    "manual-flight-panel",
    "flight-data-panel",
  ],
  rcs: [
    "manual-flight-panel",
  ],
  sensors: [
    "sensor-contacts",
    "science-analysis-panel",
  ],
  weapons: [
    "weapons-status",
    "weapon-controls",
    "firing-solution-display",
  ],
  targeting: [
    "targeting-display",
    "firing-solution-display",
  ],
  reactor: [
    "engineering-control-panel",
    "power-draw-display",
    "power-profile-selector",
  ],
  radiators: [
    "engineering-control-panel",
    "thermal-display",
  ],
  power: [
    "power-management",
    "power-draw-display",
  ],
  life_support: [],
};

/**
 * Determine the damage level from a subsystem report.
 * @param {object} report - Subsystem report from damage_model.get_subsystem_report()
 * @returns {"nominal"|"impaired"|"destroyed"}
 */
function getDamageLevel(report) {
  if (!report) return "nominal";
  const pct = report.health_percent ?? 100;
  if (pct <= 0) return "destroyed";
  if (pct <= 50) return "impaired";
  return "nominal";
}

class DamageStateManager {
  constructor() {
    /** @type {Map<string, {level: string, healthPct: number}>} previous tick's state */
    this._prev = new Map();
    this._unsubscribe = null;
    this._flashTimers = new Map();
  }

  /**
   * Start monitoring subsystem health from stateManager.
   * Call once after stateManager.init().
   */
  init() {
    this._unsubscribe = stateManager.subscribe("*", () => this._onStateUpdate());
  }

  destroy() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    for (const timer of this._flashTimers.values()) {
      clearTimeout(timer);
    }
    this._flashTimers.clear();
  }

  /**
   * Called every state poll tick. Reads subsystem_health, computes
   * damage levels, detects drops (under attack), and updates panels.
   */
  _onStateUpdate() {
    const ship = stateManager.getShipState();
    const healthData = ship?.subsystem_health;
    if (!healthData || !healthData.subsystems) return;

    const subsystems = healthData.subsystems;

    for (const [name, report] of Object.entries(subsystems)) {
      const level = getDamageLevel(report);
      const pct = report.health_percent ?? 100;
      const prev = this._prev.get(name);
      const prevPct = prev?.healthPct ?? 100;
      const prevLevel = prev?.level ?? "nominal";

      // Detect health drop ("under attack")
      const healthDropped = pct < prevPct;

      // Update stored state
      this._prev.set(name, { level, healthPct: pct });

      // Only update DOM if something changed
      if (level !== prevLevel || healthDropped) {
        this._applyToPanels(name, level, healthDropped, pct);
      }
    }

    // Dispatch a global event for any component that wants raw data
    document.dispatchEvent(new CustomEvent("subsystem-damage-update", {
      detail: {
        subsystems,
        missionKill: healthData.mission_kill || false,
      },
    }));
  }

  /**
   * Find panels affected by a subsystem and update their damage state.
   * @param {string} subsystem - Subsystem name
   * @param {"nominal"|"impaired"|"destroyed"} level - Current damage level
   * @param {boolean} flash - Whether to trigger the "under attack" flash
   * @param {number} healthPct - Health percentage (0-100)
   */
  _applyToPanels(subsystem, level, flash, healthPct) {
    const selectors = SUBSYSTEM_PANEL_MAP[subsystem];
    if (!selectors || selectors.length === 0) return;

    for (const tag of selectors) {
      // Find the component element and its wrapping <flaxos-panel>
      const elements = document.querySelectorAll(tag);
      for (const el of elements) {
        const panel = el.closest("flaxos-panel") || el;
        this._setPanelDamageState(panel, subsystem, level, flash, healthPct);
      }
    }
  }

  /**
   * Apply damage visual state to a single panel element.
   * Uses data attributes that panel.js reads to render overlays.
   */
  _setPanelDamageState(panel, subsystem, level, flash, healthPct) {
    // Set data attributes — panel.js CSS reacts to these
    panel.setAttribute("data-damage", level);
    panel.setAttribute("data-damage-subsystem", subsystem);
    panel.setAttribute("data-damage-pct", String(Math.round(healthPct)));

    // Handle the "under attack" flash
    if (flash && level !== "nominal") {
      panel.classList.add("damage-flash");
      // Clear any existing timer for this panel
      const key = `${panel.tagName}-${subsystem}`;
      if (this._flashTimers.has(key)) {
        clearTimeout(this._flashTimers.get(key));
      }
      this._flashTimers.set(key, setTimeout(() => {
        panel.classList.remove("damage-flash");
        this._flashTimers.delete(key);
      }, 600));
    }

    // For destroyed state, set the offline overlay via the panel's
    // existing disabled-reason mechanism (repurposed for damage)
    if (level === "destroyed") {
      const label = SUBSYSTEM_LABELS[subsystem] || subsystem.toUpperCase();
      panel.setAttribute("data-damage-offline-label", label);
    } else {
      panel.removeAttribute("data-damage-offline-label");
    }
  }
}

/** Human-readable labels for subsystems (used in OFFLINE overlay) */
const SUBSYSTEM_LABELS = {
  power: "POWER",
  propulsion: "PROPULSION",
  rcs: "RCS",
  sensors: "SENSORS",
  weapons: "WEAPONS",
  targeting: "TARGETING",
  reactor: "REACTOR",
  life_support: "LIFE SUPPORT",
  radiators: "RADIATORS",
};

// Singleton
const damageStateManager = new DamageStateManager();
export { damageStateManager, DamageStateManager, SUBSYSTEM_PANEL_MAP };
