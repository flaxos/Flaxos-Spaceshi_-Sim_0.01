/**
 * Shared difficulty scaling for ARCADE mini-games.
 * Reads subsystem health from stateManager and returns a degradation
 * factor (0 = perfect, 1 = fully destroyed).
 */
import { stateManager } from "./state-manager.js";

/**
 * Get degradation factor for a subsystem (0 = healthy, 1 = destroyed).
 * @param {string} subsystem - e.g. "sensors", "weapons", "rcs", "reactor", "radiators", "comms"
 * @returns {number} 0-1
 */
export function getDegradation(subsystem) {
  const ship = stateManager.getShipState?.() || {};
  const health = ship?.subsystem_health?.subsystems?.[subsystem]?.health_percent;
  if (health == null) return 0; // missing data = no scaling
  return Math.max(0, Math.min(1, 1 - health / 100));
}
