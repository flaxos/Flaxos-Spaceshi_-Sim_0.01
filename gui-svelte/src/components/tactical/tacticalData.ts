import type { JsonMap, Vec3 } from "../helm/helmData.js";
import {
  asRecord,
  clamp,
  extractShipState,
  formatDistance,
  formatDuration,
  formatSpeed,
  formatVector,
  getSystem,
  magnitude,
  normalizeAngle,
  signed,
  toNumber,
  toStringValue,
  toVec3,
} from "../helm/helmData.js";

export type ThreatLevel = "green" | "yellow" | "orange" | "red";

export interface TacticalContact {
  id: string;
  name: string;
  classification: string;
  faction: string;
  diplomaticState: string;
  distance: number;
  bearing: number;
  confidence: number;
  threatScore: number;
  threatLevel: ThreatLevel;
  position: Vec3;
  velocity: Vec3;
  closureRate: number;
  speed: number;
  contactState: string;
  detectionMethod: string;
  signalStrength: number;
}

export interface WeaponMountState {
  id: string;
  type: string;
  weaponType: "railgun" | "pdc" | "torpedo" | "missile" | "other";
  ammo: number;
  ready: boolean;
  charge: number;
  cooldown: number;
  status: string;
  range: number;
}

export interface ActiveMunitionState {
  id: string;
  munitionType: "torpedo" | "missile";
  shooter: string;
  target: string;
  distance: number;
  eta: number | null;
  profile: string;
  guidanceMode: string;
  warheadType: string;
  state: string;
}

const ZERO_VEC: Vec3 = { x: 0, y: 0, z: 0 };

function textIncludes(source: string, values: string[]): boolean {
  const lower = source.toLowerCase();
  return values.some((value) => lower.includes(value));
}

function deriveBearing(position: Vec3): number {
  const radians = Math.atan2(position.x, position.y);
  return normalizeAngle((radians * 180) / Math.PI);
}

function parseBearing(value: unknown, position: Vec3): number {
  if (typeof value === "number" && Number.isFinite(value)) return normalizeAngle(value);
  const rec = asRecord(value);
  if (rec) {
    const vec = toVec3(rec, position);
    return deriveBearing(vec);
  }
  return deriveBearing(position);
}

function computeThreatScore(contact: TacticalContact): number {
  const classText = `${contact.classification} ${contact.name}`.toLowerCase();
  let base = 0.2;

  if (textIncludes(classText, ["torpedo", "missile"])) base += 0.55;
  else if (textIncludes(classText, ["battleship", "cruiser", "carrier"])) base += 0.45;
  else if (textIncludes(classText, ["frigate", "destroyer", "corvette", "gunship"])) base += 0.32;
  else if (textIncludes(classText, ["drone", "shuttle", "probe"])) base += 0.1;

  const closing = Math.max(0, contact.closureRate);
  const approachBonus = clamp(closing / 2000, 0, 0.25);
  const distanceBonus = 0.28 * (1 - clamp(contact.distance / 250_000, 0, 1));
  const hostileBonus = textIncludes(contact.diplomaticState, ["hostile", "enemy"]) ? 0.15 : 0;
  const confidenceBonus = contact.confidence * 0.12;

  return clamp(base + approachBonus + distanceBonus + hostileBonus + confidenceBonus, 0, 1);
}

function scoreToThreatLevel(score: number): ThreatLevel {
  if (score >= 0.78) return "red";
  if (score >= 0.58) return "orange";
  if (score >= 0.35) return "yellow";
  return "green";
}

function normalizeContact(item: JsonMap): TacticalContact {
  const position = toVec3(item.position);
  const velocity = toVec3(item.velocity);
  const distance = toNumber(item.distance, magnitude(position));
  const speed = magnitude(velocity);
  const bearing = parseBearing(item.bearing, position);
  const closureRate = distance > 0
    ? -((position.x * velocity.x) + (position.y * velocity.y) + (position.z * velocity.z)) / distance
    : 0;

  const contact: TacticalContact = {
    id: toStringValue(item.id, "unknown"),
    name: toStringValue(item.name) || toStringValue(item.classification) || toStringValue(item.id, "Unknown"),
    classification: toStringValue(item.classification, "Unknown"),
    faction: toStringValue(item.faction, "unknown"),
    diplomaticState: toStringValue(item.diplomatic_state, "unknown"),
    distance,
    bearing,
    confidence: clamp(toNumber(item.confidence, 0), 0, 1),
    threatScore: 0,
    threatLevel: "green",
    position,
    velocity,
    closureRate,
    speed,
    contactState: toStringValue(item.contact_state, "confirmed"),
    detectionMethod: toStringValue(item.detection_method, "passive"),
    signalStrength: toNumber(item.signal_strength, toNumber(item.signature_strength, toNumber(item.confidence, 0))),
  };

  contact.threatScore = computeThreatScore(contact);
  contact.threatLevel = scoreToThreatLevel(contact.threatScore);
  return contact;
}

export function getShip(gameState: JsonMap | null | undefined): JsonMap {
  return extractShipState(gameState);
}

export function getSensorState(ship: JsonMap): JsonMap {
  return asRecord(ship.sensors) ?? getSystem(ship, "sensors");
}

export function getTargetingState(ship: JsonMap): JsonMap {
  return asRecord(ship.targeting) ?? getSystem(ship, "targeting");
}

export function getCombatState(ship: JsonMap): JsonMap {
  return asRecord(ship.combat) ?? getSystem(ship, "combat") ?? asRecord(ship.weapons) ?? {};
}

export function getECMState(ship: JsonMap): JsonMap {
  return asRecord(ship.ecm) ?? getSystem(ship, "ecm");
}

export function getECCMState(ship: JsonMap): JsonMap {
  const sensors = getSensorState(ship);
  return asRecord(ship.eccm) ?? asRecord(sensors.eccm) ?? {};
}

export function getAutoTacticalState(ship: JsonMap): JsonMap {
  return asRecord(ship.auto_tactical) ?? getSystem(ship, "auto_tactical");
}

export function getTacticalContacts(ship: JsonMap): TacticalContact[] {
  const sensors = getSensorState(ship);
  const contacts = Array.isArray(sensors.contacts) ? sensors.contacts : [];
  return contacts
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map(normalizeContact)
    .sort((a, b) => {
      if (b.threatScore !== a.threatScore) return b.threatScore - a.threatScore;
      return a.distance - b.distance;
    });
}

export function findTacticalContact(ship: JsonMap, contactId: string): TacticalContact | null {
  return getTacticalContacts(ship).find((contact) => contact.id === contactId) ?? null;
}

export function getThreatList(ship: JsonMap): TacticalContact[] {
  return getTacticalContacts(ship).filter((contact) => contact.confidence > 0.1);
}

export function getLockedTargetId(ship: JsonMap): string {
  const targeting = getTargetingState(ship);
  return toStringValue(targeting.locked_target);
}

export function getLockStage(targeting: JsonMap): number {
  const state = toStringValue(targeting.lock_state, "idle");
  if (state === "locked") return 4;
  if (state === "tracking") return 3;
  if (state === "acquiring") return 2;
  if (state === "designated") return 1;
  return 0;
}

export function getWeaponMounts(ship: JsonMap): WeaponMountState[] {
  const combat = getCombatState(ship);
  const source = asRecord(combat.truth_weapons) ?? asRecord(combat.weapons) ?? {};

  return Object.entries(source)
    .map(([id, raw]) => {
      const item = asRecord(raw);
      if (!item) return null;
      const typeString = toStringValue(item.type, id).toLowerCase();
      let weaponType: WeaponMountState["weaponType"] = "other";
      if (id.startsWith("railgun") || typeString.includes("railgun")) weaponType = "railgun";
      else if (id.startsWith("pdc") || typeString.includes("pdc")) weaponType = "pdc";
      else if (typeString.includes("torpedo")) weaponType = "torpedo";
      else if (typeString.includes("missile")) weaponType = "missile";

      return {
        id,
        type: toStringValue(item.type, id),
        weaponType,
        ammo: toNumber(item.ammo),
        ready: Boolean(item.ready),
        charge: clamp(toNumber(item.charge_fraction, toNumber(item.charge, 0)), 0, 1),
        cooldown: toNumber(item.cooldown_remaining, toNumber(item.cooldown)),
        status: toStringValue(item.status, item.ready ? "ready" : "standby"),
        range: toNumber(item.range, toNumber(item.max_range)),
      };
    })
    .filter((item): item is WeaponMountState => Boolean(item));
}

export function getRailgunMounts(ship: JsonMap): WeaponMountState[] {
  return getWeaponMounts(ship).filter((mount) => mount.weaponType === "railgun");
}

export function getPdcMounts(ship: JsonMap): WeaponMountState[] {
  return getWeaponMounts(ship).filter((mount) => mount.weaponType === "pdc");
}

export function getLauncherInventory(ship: JsonMap): { torpedoes: JsonMap; missiles: JsonMap } {
  const combat = getCombatState(ship);
  return {
    torpedoes: asRecord(combat.torpedoes) ?? {},
    missiles: asRecord(combat.missiles) ?? {},
  };
}

export function getIncomingMunitions(gameState: JsonMap, ship: JsonMap): ActiveMunitionState[] {
  const shipId = toStringValue(ship.id);
  const active = Array.isArray(gameState.torpedoes) ? gameState.torpedoes : [];

  return active
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .filter((item) => toStringValue(item.target) === shipId && toStringValue(item.shooter) !== shipId)
    .map((item) => {
      const munitionType: ActiveMunitionState["munitionType"] =
        toStringValue(item.munition_type, "torpedo") === "missile"
          ? "missile"
          : "torpedo";
      return {
        id: toStringValue(item.id),
        munitionType,
        shooter: toStringValue(item.shooter),
        target: toStringValue(item.target),
        distance: toNumber(item.distance),
        eta: item.eta == null ? null : toNumber(item.eta),
        profile: toStringValue(item.profile, "direct"),
        guidanceMode: toStringValue(item.guidance_mode, "guided"),
        warheadType: toStringValue(item.warhead_type, "fragmentation"),
        state: toStringValue(item.state, "unknown"),
      };
    })
    .sort((a, b) => {
      const etaA = a.eta ?? Number.POSITIVE_INFINITY;
      const etaB = b.eta ?? Number.POSITIVE_INFINITY;
      if (etaA !== etaB) return etaA - etaB;
      return a.distance - b.distance;
    });
}

export function getBestWeaponSolution(ship: JsonMap): JsonMap {
  const targeting = getTargetingState(ship);
  const solutions = asRecord(targeting.solutions) ?? {};
  const ranked = Object.entries(solutions)
    .map(([id, raw]) => ({ id, data: asRecord(raw) }))
    .filter((row): row is { id: string; data: JsonMap } => Boolean(row.data))
    .sort((a, b) => toNumber(b.data.confidence) - toNumber(a.data.confidence));

  return ranked[0]?.data ?? {};
}

export function getSolutionFactors(solution: JsonMap): Array<{ label: string; value: number }> {
  const factors = asRecord(solution.confidence_factors);
  if (factors) {
    return [
      { label: "Range", value: clamp(toNumber(factors.range, 0), 0, 1) },
      { label: "Closure", value: clamp(toNumber(factors.closure_rate, toNumber(factors.closure, 0)), 0, 1) },
      { label: "Motion", value: clamp(toNumber(factors.target_motion, 0), 0, 1) },
      { label: "Track", value: clamp(toNumber(factors.track_quality, 0), 0, 1) },
      { label: "Age", value: clamp(toNumber(factors.solution_age, 0), 0, 1) },
    ];
  }

  return [
    { label: "Range", value: clamp(1 - toNumber(solution.range) / 200_000, 0, 1) },
    { label: "Closure", value: clamp(1 - Math.abs(toNumber(solution.range_rate)) / 2500, 0, 1) },
    { label: "Motion", value: clamp(toNumber(solution.hit_probability, toNumber(solution.confidence)), 0, 1) },
    { label: "Track", value: clamp(toNumber(solution.lock_quality, toNumber(solution.track_quality)), 0, 1) },
    { label: "Age", value: clamp(1 - toNumber(solution.solution_age) / 12, 0, 1) },
  ];
}

export function getTargetingSummary(ship: JsonMap): {
  lockedTarget: string;
  lockState: string;
  lockQuality: number;
  stage: number;
  correlation: number;
  trackQuality: number;
  lockProgress: number;
  subsystem: string;
} {
  const targeting = getTargetingState(ship);
  return {
    lockedTarget: toStringValue(targeting.locked_target),
    lockState: toStringValue(targeting.lock_state, "idle"),
    lockQuality: clamp(toNumber(targeting.lock_quality), 0, 1),
    stage: getLockStage(targeting),
    correlation: clamp(toNumber(targeting.correlation_progress), 0, 1),
    trackQuality: clamp(toNumber(targeting.track_quality), 0, 1),
    lockProgress: clamp(toNumber(targeting.lock_progress), 0, 1),
    subsystem: toStringValue(targeting.target_subsystem, "none"),
  };
}

export function getMultiTrackState(ship: JsonMap): {
  trackCount: number;
  tracks: JsonMap[];
  primaryTarget: string;
  pdcAssignments: JsonMap;
  splitFireAssignments: JsonMap;
} {
  const targeting = getTargetingState(ship);
  const state = asRecord(targeting.multi_track) ?? {};
  return {
    trackCount: toNumber(state.track_count),
    tracks: Array.isArray(state.tracks) ? state.tracks.map((item) => asRecord(item)).filter((item): item is JsonMap => Boolean(item)) : [],
    primaryTarget: toStringValue(state.primary_target),
    pdcAssignments: asRecord(state.pdc_assignments) ?? {},
    splitFireAssignments: asRecord(state.split_fire_assignments) ?? {},
  };
}

export function getAuthorizedWeapons(ship: JsonMap): Record<string, boolean> {
  const combat = getCombatState(ship);
  const autoFire = asRecord(combat.auto_fire) ?? {};
  const authorized = asRecord(autoFire.authorized) ?? {};
  return {
    railgun: Boolean(authorized.railgun),
    torpedo: Boolean(authorized.torpedo),
    missile: Boolean(authorized.missile),
  };
}

export function getTacticalProposals(ship: JsonMap): JsonMap[] {
  const autoTactical = getAutoTacticalState(ship);
  return Array.isArray(autoTactical.proposals)
    ? autoTactical.proposals.map((proposal) => asRecord(proposal)).filter((proposal): proposal is JsonMap => Boolean(proposal))
    : [];
}

export function formatBearing(value: number): string {
  return `${signed(normalizeAngle(value), 0)}°`;
}

export function formatContactVector(contact: TacticalContact): string {
  return formatVector(contact.velocity);
}

export function formatContactSummary(contact: TacticalContact): string {
  return `${formatDistance(contact.distance)} · ${formatSpeed(contact.speed)}`;
}

export function summarizeSolution(solution: JsonMap): string {
  const eta = formatDuration(toNumber(solution.time_of_flight, toNumber(solution.eta)));
  const range = formatDistance(toNumber(solution.range));
  return `${range} · TOF ${eta}`;
}

export function getAssessmentSummary(assessment: JsonMap | null): { hull: number; subsystems: JsonMap[] } {
  const record = assessment ?? {};
  const subsystems = asRecord(record.subsystems) ?? {};
  const rows = Object.entries(subsystems)
    .map(([name, raw]) => {
      const item = asRecord(raw);
      if (!item) return null;
      return {
        name,
        health: toNumber(item.health, -1),
        status: toStringValue(item.status, "unknown"),
        confidence: toStringValue(item.confidence, "none"),
      };
    })
    .filter((row): row is { name: string; health: number; status: string; confidence: string } => Boolean(row));

  const numeric = rows
    .map((row) => toNumber(row.health, -1))
    .filter((value) => value >= 0);
  const hull = numeric.length ? numeric.reduce((sum, value) => sum + value, 0) / numeric.length : 0;
  return { hull, subsystems: rows as unknown as JsonMap[] };
}

export { formatDistance, formatDuration, formatSpeed, formatVector, magnitude, toNumber, toStringValue, asRecord };
export { extractShipState };
