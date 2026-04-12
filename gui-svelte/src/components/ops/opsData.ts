import type { JsonMap } from "../helm/helmData.js";
import {
  asRecord,
  clamp,
  extractShipState,
  formatDistance,
  formatDuration,
  formatSpeed,
  toNumber,
  toStringValue,
} from "../helm/helmData.js";
import {
  ENGINEERING_SYSTEM_LABELS,
  POWER_CATEGORY_ORDER,
  type PowerCategory,
  getPowerCategoryWeights,
  getSubsystemRows,
  translateCategoryWeightsToBusAllocation,
} from "../engineering/engineeringData.js";

export interface ArmorSectionRow {
  id: string;
  label: string;
  integrityPercent: number;
  material: string;
  stripped: boolean;
}

export interface OpsProposal {
  proposalId: string;
  action: string;
  target: string;
  reason: string;
  confidence: number;
}

export interface CrewRow {
  crewId: string;
  clientId: string;
  name: string;
  station: string;
  injury: string;
  health: number;
  fatigue: number;
  stress: number;
  skills: Record<string, number>;
}

export const OPS_SYSTEM_PRIORITY_ORDER = [
  "life_support",
  "reactor",
  "sensors",
  "rcs",
  "propulsion",
  "targeting",
  "weapons",
  "radiators",
] as const;

export function getOpsShip(gameState: JsonMap | null | undefined): JsonMap {
  return extractShipState(gameState);
}

export function getOpsState(ship: JsonMap): JsonMap {
  return asRecord(ship.ops) ?? {};
}

export function getAutoOpsState(ship: JsonMap): JsonMap {
  return asRecord(ship.auto_ops) ?? {};
}

export function getCrewFatigueState(ship: JsonMap): JsonMap {
  return asRecord(ship.crew_fatigue) ?? {};
}

export function getCrewProgressionState(ship: JsonMap): JsonMap {
  return asRecord(ship.crew_progression) ?? {};
}

export function getBoardingTelemetry(ship: JsonMap): JsonMap {
  return asRecord(ship.boarding) ?? {};
}

export function getDroneBayTelemetry(ship: JsonMap): JsonMap {
  return asRecord(ship.drone_bay) ?? {};
}

export function getArmorRows(ship: JsonMap): ArmorSectionRow[] {
  const sections = asRecord(asRecord(ship.armor_status)?.sections) ?? asRecord(ship.armor) ?? {};
  const order = ["fore", "aft", "port", "starboard", "dorsal", "ventral"];
  const labels: Record<string, string> = {
    fore: "Fore",
    aft: "Aft",
    port: "Port",
    starboard: "Starboard",
    dorsal: "Dorsal",
    ventral: "Ventral",
  };

  return order.map((id) => {
    const row = asRecord(sections[id]) ?? {};
    return {
      id,
      label: labels[id] ?? id,
      integrityPercent: clamp(
        toNumber(row.integrity_percent, toNumber(row.percent, toNumber(row.integrity, 100))),
        0,
        100,
      ),
      material: toStringValue(row.material, "unknown"),
      stripped: Boolean(row.stripped),
    };
  });
}

export function getHullPercent(ship: JsonMap): number {
  return clamp(toNumber(ship.hull_percent, 100), 0, 100);
}

export function getArmorIntegrity(ship: JsonMap): number {
  return clamp(toNumber(asRecord(ship.armor_status)?.overall_integrity_percent, 100), 0, 100);
}

export function getReadiness(ship: JsonMap): { score: number; label: string } {
  const hull = getHullPercent(ship);
  const armor = getArmorIntegrity(ship);
  const fatigue = getCrewFatigueState(ship);
  const crewPerf = clamp(toNumber(fatigue.performance, 1) * 100, 0, 100);
  const subsystemAverage = (() => {
    const rows = getSubsystemRows(ship);
    if (!rows.length) return 100;
    return rows.reduce((sum, row) => sum + row.healthPercent, 0) / rows.length;
  })();

  const score = (hull + armor + crewPerf + subsystemAverage) / 4;
  let label = "Mission Ready";
  if (score < 35) label = "Critical";
  else if (score < 60) label = "Compromised";
  else if (score < 82) label = "Degraded";
  return { score, label };
}

export function getRepairTeams(ship: JsonMap): JsonMap[] {
  const rawTeams = getOpsState(ship).repair_teams;
  const source = Array.isArray(rawTeams) ? (rawTeams as unknown[]) : [];
  return source.map((item: unknown) => asRecord(item)).filter((item): item is JsonMap => Boolean(item));
}

export function getFieldRepair(ship: JsonMap): JsonMap {
  return asRecord(getOpsState(ship).field_repair) ?? {};
}

export function getRepairTargets(ship: JsonMap): Array<{
  id: string;
  label: string;
  healthPercent: number;
  damagePercent: number;
  assignedTeam: string;
  status: string;
}> {
  const teamAssignments = new Map(
    getRepairTeams(ship)
      .filter((team) => toStringValue(team.assigned_subsystem))
      .map((team) => [toStringValue(team.assigned_subsystem), toStringValue(team.team_id)]),
  );

  return getSubsystemRows(ship)
    .filter((row) => row.damagePercent > 0.01)
    .map((row) => ({
      id: row.id,
      label: row.label,
      healthPercent: row.healthPercent,
      damagePercent: row.damagePercent,
      assignedTeam: teamAssignments.get(row.id) ?? "",
      status: row.status,
    }))
    .sort((a, b) => b.damagePercent - a.damagePercent);
}

export function getOpsProposals(ship: JsonMap): OpsProposal[] {
  const rawProposals = getAutoOpsState(ship).proposals;
  const source = Array.isArray(rawProposals) ? (rawProposals as unknown[]) : [];
  return source
    .map((item: unknown) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item: JsonMap) => ({
      proposalId: toStringValue(item.proposal_id),
      action: toStringValue(item.action, "proposal"),
      target: toStringValue(item.target, "ship"),
      reason: toStringValue(item.reason, "Awaiting approval"),
      confidence: clamp(toNumber(item.confidence, 0), 0, 1),
    }));
}

export function getCrewRows(ship: JsonMap): CrewRow[] {
  const roster = Array.isArray(asRecord(getCrewProgressionState(ship))?.roster)
    ? (asRecord(getCrewProgressionState(ship))?.roster as unknown[])
    : [];

  return roster
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      crewId: toStringValue(item.crew_id),
      clientId: toStringValue(item.client_id),
      name: toStringValue(item.name, "Crew"),
      station: toStringValue(item.station_assignment, "UNASSIGNED"),
      injury: toStringValue(item.injury_state, "healthy"),
      health: clamp(toNumber(item.health, 1), 0, 1),
      fatigue: clamp(toNumber(item.fatigue, 0), 0, 1),
      stress: clamp(toNumber(item.stress, 0), 0, 1),
      skills: (asRecord(item.skills) as Record<string, number> | null) ?? {},
    }));
}

export function countRestingCrew(ship: JsonMap): number {
  const fatigue = getCrewFatigueState(ship);
  if (!Boolean(fatigue.rest_ordered)) return 0;
  const rows = getCrewRows(ship);
  return rows.length;
}

export function getSystemPriority(ship: JsonMap, subsystem: string): number {
  return toNumber(asRecord(getOpsState(ship).system_priorities)?.[subsystem], 0);
}

export function skillShort(level: number): string {
  const map: Record<number, string> = {
    1: "NOV",
    2: "TRN",
    3: "CMP",
    4: "SKL",
    5: "EXP",
    6: "MST",
  };
  return map[level] ?? `${level}`;
}

export function skillLong(level: number): string {
  const map: Record<number, string> = {
    1: "NOVICE",
    2: "TRAINEE",
    3: "COMPETENT",
    4: "SKILLED",
    5: "EXPERT",
    6: "MASTER",
  };
  return map[level] ?? `${level}`;
}

export function powerCategoryWeights(ship: JsonMap): Record<PowerCategory, number> {
  return getPowerCategoryWeights(ship);
}

export function translatePowerCategoryWeights(weights: Record<PowerCategory, number>): Record<"primary" | "secondary" | "tertiary", number> {
  return translateCategoryWeightsToBusAllocation(weights);
}

export function readinessClass(score: number): "critical" | "warning" | "nominal" {
  if (score < 35) return "critical";
  if (score < 60) return "warning";
  return "nominal";
}

export function formatMass(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  if (value >= 1000) return `${(value / 1000).toFixed(1)} kt`;
  return `${value.toFixed(0)} t`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${Math.round(value)}%`;
}

export {
  ENGINEERING_SYSTEM_LABELS,
  POWER_CATEGORY_ORDER,
  type PowerCategory,
  asRecord,
  clamp,
  formatDistance,
  formatDuration,
  formatSpeed,
  toNumber,
  toStringValue,
};
