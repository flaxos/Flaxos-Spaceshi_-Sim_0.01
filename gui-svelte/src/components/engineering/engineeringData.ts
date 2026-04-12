import type { JsonMap } from "../helm/helmData.js";
import {
  asRecord,
  clamp,
  extractShipState,
  formatDuration,
  formatSpeed,
  getSystem,
  toNumber,
  toStringValue,
} from "../helm/helmData.js";

export interface EngineeringProposal {
  proposalId: string;
  action: string;
  target: string;
  reason: string;
  confidence: number;
  params: JsonMap;
}

export interface SystemHealthRow {
  id: string;
  label: string;
  healthPercent: number;
  heatPercent: number;
  damagePercent: number;
  status: string;
  repairStatus: string;
  combinedFactor: number;
}

export const ENGINEERING_SYSTEM_LABELS: Record<string, string> = {
  propulsion: "Drive",
  reactor: "Reactor",
  weapons: "Weapons",
  sensors: "Sensors",
  comms: "Comms",
  radiators: "Radiators",
  life_support: "Life Support",
};

export const POWER_CATEGORY_ORDER = [
  "weapons",
  "sensors",
  "comms",
  "life_support",
  "propulsion",
] as const;

export type PowerCategory = typeof POWER_CATEGORY_ORDER[number];

export const POWER_CATEGORY_TO_BUS: Record<PowerCategory, "primary" | "secondary" | "tertiary"> = {
  propulsion: "primary",
  weapons: "primary",
  sensors: "primary",
  comms: "secondary",
  life_support: "tertiary",
};

export function getEngineeringShip(gameState: JsonMap | null | undefined): JsonMap {
  return extractShipState(gameState);
}

export function getEngineeringState(ship: JsonMap): JsonMap {
  return asRecord(ship.engineering) ?? getSystem(ship, "engineering");
}

export function getThermalState(ship: JsonMap): JsonMap {
  return asRecord(ship.thermal) ?? getSystem(ship, "thermal");
}

export function getOpsState(ship: JsonMap): JsonMap {
  return asRecord(ship.ops) ?? getSystem(ship, "ops");
}

export function getAutoEngineeringState(ship: JsonMap): JsonMap {
  return asRecord(ship.auto_engineering) ?? getSystem(ship, "auto_engineering");
}

export function getFuelState(ship: JsonMap): JsonMap {
  return asRecord(ship.fuel) ?? {};
}

export function getDrawProfileBuses(profile: JsonMap | null): Record<string, JsonMap> {
  return (asRecord(profile?.buses) as Record<string, JsonMap> | null) ?? {};
}

export function getReactorSummary(ship: JsonMap): { output: number; driveLimit: number; fuelPercent: number; timeRemaining: number | null; burnRate: number; deltaV: number } {
  const engineering = getEngineeringState(ship);
  const fuel = getFuelState(ship);
  return {
    output: clamp(toNumber(engineering.reactor_output, 1), 0, 1),
    driveLimit: clamp(toNumber(engineering.drive_limit, 1), 0, 1),
    fuelPercent: clamp(toNumber(fuel.percent), 0, 100),
    timeRemaining: Number.isFinite(toNumber(fuel.time_remaining, Number.NaN)) ? toNumber(fuel.time_remaining, Number.NaN) : null,
    burnRate: toNumber(fuel.burn_rate, toNumber(engineering.fuel_burn_rate)),
    deltaV: toNumber(ship.delta_v_remaining),
  };
}

export function getPowerCategoryWeights(ship: JsonMap): Record<PowerCategory, number> {
  const ops = getOpsState(ship);
  const source = asRecord(ops.power_allocation) ?? {};
  const defaults: Record<PowerCategory, number> = {
    propulsion: 0.25,
    weapons: 0.15,
    sensors: 0.15,
    comms: 0.05,
    life_support: 0.05,
  };

  return {
    propulsion: toNumber(source.propulsion, defaults.propulsion),
    weapons: toNumber(source.weapons, defaults.weapons),
    sensors: toNumber(source.sensors, defaults.sensors),
    comms: toNumber(source.comms, defaults.comms),
    life_support: toNumber(source.life_support, defaults.life_support),
  };
}

export function translateCategoryWeightsToBusAllocation(weights: Record<PowerCategory, number>): Record<"primary" | "secondary" | "tertiary", number> {
  const buses = {
    primary: 0,
    secondary: 0,
    tertiary: 0,
  };

  for (const category of POWER_CATEGORY_ORDER) {
    buses[POWER_CATEGORY_TO_BUS[category]] += Math.max(0, weights[category]);
  }

  const total = buses.primary + buses.secondary + buses.tertiary;
  if (total <= 0) {
    return { primary: 0.5, secondary: 0.3, tertiary: 0.2 };
  }

  return {
    primary: buses.primary / total,
    secondary: buses.secondary / total,
    tertiary: buses.tertiary / total,
  };
}

export function getSubsystemRows(ship: JsonMap): SystemHealthRow[] {
  const report = asRecord(ship.subsystem_health) ?? {};
  const subsystems = asRecord(report.subsystems) ?? {};
  const ops = getOpsState(ship);
  const repairTeams = Array.isArray(ops.repair_teams) ? ops.repair_teams : [];

  const getRepairStatus = (subsystemId: string): string => {
    const assigned = repairTeams
      .map((team) => asRecord(team))
      .find((team) => toStringValue(team?.assigned_subsystem) === subsystemId);
    if (!assigned) return "idle";
    return toStringValue(assigned.status, "assigned");
  };

  return Object.entries(ENGINEERING_SYSTEM_LABELS).map(([id, label]) => {
    const row = asRecord(subsystems[id]) ?? {};
    const healthPercent = clamp(toNumber(row.health_percent, 100), 0, 100);
    const heatPercent = clamp(toNumber(row.heat_percent, 0), 0, 100);
    return {
      id,
      label,
      healthPercent,
      heatPercent,
      damagePercent: 100 - healthPercent,
      status: toStringValue(row.status, "online"),
      repairStatus: getRepairStatus(id),
      combinedFactor: clamp(toNumber(row.combined_factor, 1), 0, 1),
    };
  });
}

export function getSystemToggleState(ship: JsonMap): Array<{ id: string; label: string; enabled: boolean; status: string }> {
  const statuses = asRecord(ship.systems) ?? {};
  const topLevel = ship;
  const ids = ["propulsion", "reactor", "weapons", "sensors", "comms", "radiators", "life_support"];
  return ids.map((id) => {
    const statusValue = toStringValue(statuses[id], toStringValue(asRecord(topLevel[id])?.status, "online"));
    const enabled = !["offline", "failed", "destroyed", "disabled", "unavailable"].includes(statusValue.toLowerCase());
    return {
      id,
      label: ENGINEERING_SYSTEM_LABELS[id] ?? id,
      enabled,
      status: statusValue,
    };
  });
}

export function getThermalBars(ship: JsonMap): Array<{ id: string; label: string; percent: number; current: number; status: string }> {
  const thermal = getThermalState(ship);
  const subsystems = asRecord(asRecord(ship.subsystem_health)?.subsystems) ?? {};
  const weaponHeat = toNumber(asRecord(subsystems.weapons)?.heat_percent, 0);
  const radiatorHeat = toNumber(asRecord(subsystems.radiators)?.heat_percent, 0);
  const reactorHeat = Math.max(
    toNumber(asRecord(subsystems.reactor)?.heat_percent, 0),
    clamp((toNumber(thermal.reactor_heat) / 100_000) * 100, 0, 100),
  );
  const driveHeat = Math.max(
    toNumber(asRecord(subsystems.propulsion)?.heat_percent, 0),
    clamp((toNumber(thermal.drive_heat) / 100_000) * 100, 0, 100),
  );

  return [
    { id: "reactor", label: "Reactor", percent: reactorHeat, current: toNumber(thermal.reactor_heat), status: thermalStatusFromPercent(reactorHeat) },
    { id: "drives", label: "Drives", percent: driveHeat, current: toNumber(thermal.drive_heat), status: thermalStatusFromPercent(driveHeat) },
    { id: "weapons", label: "Weapons", percent: weaponHeat, current: weaponHeat, status: thermalStatusFromPercent(weaponHeat) },
    { id: "radiators", label: "Radiators", percent: radiatorHeat, current: toNumber(thermal.radiator_effective_area), status: thermalStatusFromPercent(radiatorHeat) },
  ];
}

export function getEngineeringProposals(ship: JsonMap): EngineeringProposal[] {
  const autoEngineering = getAutoEngineeringState(ship);
  const source = Array.isArray(autoEngineering.proposals) ? autoEngineering.proposals : [];
  return source
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      proposalId: toStringValue(item.proposal_id),
      action: toStringValue(item.action, "proposal"),
      target: toStringValue(item.target, "ship"),
      reason: toStringValue(item.reason, "Awaiting approval"),
      confidence: clamp(toNumber(item.confidence, 0), 0, 1),
      params: asRecord(item.params) ?? {},
    }));
}

export function thermalStatusFromPercent(percent: number): "green" | "yellow" | "orange" | "red" {
  if (percent >= 85) return "red";
  if (percent >= 65) return "orange";
  if (percent >= 40) return "yellow";
  return "green";
}

export function formatKw(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${value.toFixed(value >= 100 ? 0 : 1)} kW`;
}

export function formatThermalStatus(thermal: JsonMap): string {
  return toStringValue(thermal.status, "nominal").toUpperCase();
}

export function formatFuelTime(seconds: number | null): string {
  return seconds == null ? "--" : formatDuration(seconds);
}

export function formatDriveLimit(limit: number): string {
  return `${Math.round(limit * 100)}%`;
}

export function formatFuelBurnRate(value: number): string {
  if (!Number.isFinite(value)) return "--";
  return `${value.toFixed(value >= 10 ? 1 : 2)} kg/s`;
}

export { asRecord, clamp, extractShipState, formatDuration, formatSpeed, toNumber, toStringValue };
