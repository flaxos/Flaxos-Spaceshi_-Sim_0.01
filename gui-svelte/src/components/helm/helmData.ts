import type { Tier } from "../../lib/stores/tier.js";

export type JsonMap = Record<string, unknown>;

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Orientation {
  pitch: number;
  yaw: number;
  roll: number;
}

export interface ContactSummary {
  id: string;
  name: string;
  classification: string;
  distance: number;
  position: Vec3;
  velocity: Vec3;
}

export interface AutopilotSnapshot {
  active: boolean;
  mode: string;
  program: string;
  phase: string;
  status: string;
  targetId: string;
  distance: number | null;
  eta: number | null;
  progress: number;
}

export interface DockingSnapshot {
  status: string;
  targetId: string;
  range: number | null;
  relativeVelocity: number | null;
  dockingRange: number;
  maxRelativeVelocity: number;
  serviceReport: JsonMap | null;
}

export interface QueueEntry {
  id: number | null;
  command: string;
  status: string;
  elapsed: number;
  target: string;
  params: JsonMap;
}

export interface ThrusterState {
  id: string;
  throttle: number;
  position: Vec3;
  direction: Vec3;
  torque: Vec3;
  maxThrust: number;
}

const ZERO_VEC: Vec3 = { x: 0, y: 0, z: 0 };
const ZERO_ORIENTATION: Orientation = { pitch: 0, yaw: 0, roll: 0 };

export function asRecord(value: unknown): JsonMap | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonMap)
    : null;
}

export function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export function toStringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

export function toVec3(value: unknown, fallback: Vec3 = ZERO_VEC): Vec3 {
  const rec = asRecord(value);
  if (rec) {
    return {
      x: toNumber(rec.x, fallback.x),
      y: toNumber(rec.y, fallback.y),
      z: toNumber(rec.z, fallback.z),
    };
  }

  if (Array.isArray(value)) {
    return {
      x: toNumber(value[0], fallback.x),
      y: toNumber(value[1], fallback.y),
      z: toNumber(value[2], fallback.z),
    };
  }

  return fallback;
}

export function toOrientation(value: unknown, fallback: Orientation = ZERO_ORIENTATION): Orientation {
  const rec = asRecord(value);
  if (!rec) return fallback;
  return {
    pitch: toNumber(rec.pitch, fallback.pitch),
    yaw: normalizeAngle(toNumber(rec.yaw, fallback.yaw)),
    roll: normalizeAngle(toNumber(rec.roll, fallback.roll)),
  };
}

export function extractShipState(gameState: JsonMap | null | undefined): JsonMap {
  const state = asRecord(gameState);
  if (!state) return {};

  const topState = asRecord(state.state);
  if (topState) return topState;

  const ship = asRecord(state.ship);
  if (ship) return ship;

  const ships = asRecord(state.ships);
  if (ships) {
    const first = Object.values(ships)[0];
    return asRecord(first) ?? {};
  }

  const list = Array.isArray(state.ships) ? state.ships : [];
  if (list.length > 0) return asRecord(list[0]) ?? {};

  return state;
}

export function getSystem(ship: JsonMap, name: string): JsonMap {
  const systems = asRecord(ship.systems);
  return asRecord(systems?.[name]) ?? {};
}

export function getPosition(ship: JsonMap): Vec3 {
  return toVec3(ship.position);
}

export function getVelocity(ship: JsonMap): Vec3 {
  const nav = asRecord(ship.navigation);
  return toVec3(ship.velocity, toVec3(nav?.velocity));
}

export function getOrientation(ship: JsonMap): Orientation {
  const nav = asRecord(ship.navigation);
  return toOrientation(ship.orientation, toOrientation(nav?.heading));
}

export function magnitude(vec: Vec3): number {
  return Math.sqrt(vec.x * vec.x + vec.y * vec.y + vec.z * vec.z);
}

export function subtract(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
}

export function distance(a: Vec3, b: Vec3): number {
  return magnitude(subtract(a, b));
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function normalizeAngle(value: number): number {
  let normalized = value % 360;
  if (normalized > 180) normalized -= 360;
  if (normalized <= -180) normalized += 360;
  return normalized;
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters == null || !Number.isFinite(meters)) return "--";
  const abs = Math.abs(meters);
  if (abs >= 1_000_000) return `${(meters / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })} km`;
  if (abs >= 1000) return `${(meters / 1000).toFixed(abs >= 10_000 ? 0 : 1)} km`;
  return `${meters.toFixed(abs >= 100 ? 0 : 1)} m`;
}

export function formatSpeed(speed: number | null | undefined): string {
  if (speed == null || !Number.isFinite(speed)) return "--";
  const abs = Math.abs(speed);
  if (abs >= 1000) return `${(speed / 1000).toFixed(2)} km/s`;
  if (abs >= 100) return `${speed.toFixed(0)} m/s`;
  return `${speed.toFixed(1)} m/s`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "--";
  if (seconds <= 0) return "0s";
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole}s`;
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  if (minutes < 60) return `${minutes}m ${String(secs).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${String(remainingMinutes).padStart(2, "0")}m`;
}

export function formatVector(vec: Vec3, digits = 1): string {
  return `${signed(vec.x, digits)} ${signed(vec.y, digits)} ${signed(vec.z, digits)}`;
}

export function signed(value: number, digits = 1): string {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}`;
}

export function toPercent(value: number, digits = 0): string {
  return `${value.toFixed(digits)}%`;
}

export function getContacts(ship: JsonMap): ContactSummary[] {
  const topSensors = asRecord(ship.sensors);
  const systemSensors = getSystem(ship, "sensors");
  const source = Array.isArray(topSensors?.contacts)
    ? topSensors.contacts
    : Array.isArray(systemSensors.contacts)
      ? systemSensors.contacts
      : [];

  return source
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      id: toStringValue(item.id, "unknown"),
      name: toStringValue(item.name) || toStringValue(item.classification) || toStringValue(item.id, "Unknown"),
      classification: toStringValue(item.classification, "Unknown"),
      distance: toNumber(item.distance, Number.POSITIVE_INFINITY),
      position: toVec3(item.position),
      velocity: toVec3(item.velocity),
    }))
    .sort((a, b) => a.distance - b.distance);
}

export function findContact(ship: JsonMap, targetId: string): ContactSummary | null {
  return getContacts(ship).find((contact) => contact.id === targetId) ?? null;
}

export function getAutopilotSnapshot(ship: JsonMap): AutopilotSnapshot {
  const nav = getSystem(ship, "navigation");
  const helm = getSystem(ship, "helm");
  const flightComputer = asRecord(ship.flight_computer) ?? getSystem(ship, "flight_computer");
  const autopilotState = asRecord(ship.autopilot_state)
    ?? asRecord(nav.autopilot_state)
    ?? asRecord(ship.autopilot)
    ?? {};
  const course = asRecord(ship.course) ?? asRecord(nav.course) ?? {};
  const program = toStringValue(ship.autopilot_program)
    || toStringValue(nav.current_program)
    || toStringValue(helm.autopilot_program);
  const phase = toStringValue(autopilotState.phase) || toStringValue(helm.autopilot_phase);
  const mode = toStringValue(ship.nav_mode)
    || toStringValue(nav.mode)
    || toStringValue(helm.mode, "manual");
  const distanceValue = autopilotState.range ?? autopilotState.distance ?? course.distance ?? null;
  const etaValue = autopilotState.time_to_arrival ?? flightComputer.eta ?? null;
  const active = Boolean(program) || Boolean(nav.autopilot_enabled) || mode === "autopilot";

  return {
    active,
    mode,
    program,
    phase,
    status: toStringValue(autopilotState.status) || toStringValue(flightComputer.status_text),
    targetId: toStringValue(ship.target_id) || toStringValue(nav.target_id),
    distance: distanceValue == null ? null : toNumber(distanceValue),
    eta: etaValue == null ? null : toNumber(etaValue),
    progress: clamp(toNumber(flightComputer.progress, 0) * 100, 0, 100),
  };
}

export function getDockingSnapshot(ship: JsonMap): DockingSnapshot {
  const docking = asRecord(ship.docking) ?? getSystem(ship, "docking");
  const lastCheck = asRecord(docking.last_check);
  return {
    status: normalizeDockingState(toStringValue(docking.status, "idle")),
    targetId: toStringValue(docking.target),
    range: lastCheck?.range == null ? null : toNumber(lastCheck.range),
    relativeVelocity: lastCheck?.relative_velocity == null ? null : toNumber(lastCheck.relative_velocity),
    dockingRange: toNumber(docking.docking_range, 50),
    maxRelativeVelocity: toNumber(docking.max_relative_velocity, 1),
    serviceReport: asRecord(docking.service_report),
  };
}

function normalizeDockingState(state: string): string {
  const normalized = state.toLowerCase();
  if (["docking_initiated", "requested", "requesting"].includes(normalized)) return "approaching";
  return normalized;
}

export function getQueueState(ship: JsonMap): { active: QueueEntry | null; pending: QueueEntry[] } {
  const topQueue = asRecord(ship.helm_queue);
  const helm = getSystem(ship, "helm");
  const queue = asRecord(topQueue) ?? asRecord(helm.command_queue) ?? {};
  return {
    active: formatQueueEntry(queue.active),
    pending: Array.isArray(queue.pending) ? queue.pending.map(formatQueueEntry).filter((item): item is QueueEntry => Boolean(item)) : [],
  };
}

function formatQueueEntry(value: unknown): QueueEntry | null {
  const entry = asRecord(value);
  if (!entry) return null;
  return {
    id: entry.id == null ? null : toNumber(entry.id),
    command: toStringValue(entry.command, "unknown"),
    status: toStringValue(entry.status, "pending"),
    elapsed: toNumber(entry.elapsed, 0),
    target: toStringValue(entry.target),
    params: asRecord(entry.params) ?? {},
  };
}

export function getThrusters(ship: JsonMap): ThrusterState[] {
  const rcs = getSystem(ship, "rcs");
  const thrusters = Array.isArray(rcs.thrusters) ? rcs.thrusters : [];
  return thrusters
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      id: toStringValue(item.id, "thruster"),
      throttle: toNumber(item.throttle, 0),
      position: toVec3(item.position),
      direction: toVec3(item.direction),
      torque: toVec3(item.torque),
      maxThrust: toNumber(item.max_thrust, 0),
    }));
}

export function getDeltaV(ship: JsonMap): number {
  const prop = getSystem(ship, "propulsion");
  return toNumber(ship.delta_v_remaining, toNumber(prop.delta_v));
}

export function getPONR(ship: JsonMap): JsonMap {
  return asRecord(ship.ponr) ?? {};
}

export function getMaxAccel(ship: JsonMap): number {
  const propulsion = getSystem(ship, "propulsion");
  const mass = toNumber(ship.mass, 1);
  const thrust = toNumber(propulsion.max_thrust, 0);
  return mass > 0 ? thrust / mass : 0;
}

export function getThrottle(ship: JsonMap): number {
  const helm = getSystem(ship, "helm");
  const propulsion = getSystem(ship, "propulsion");
  const raw = helm.manual_throttle ?? propulsion.throttle ?? ship.throttle;
  return clamp(toNumber(raw, 0), 0, 1);
}

export function getFlightComputer(ship: JsonMap): JsonMap {
  return asRecord(ship.flight_computer) ?? getSystem(ship, "flight_computer");
}

export function getCourse(ship: JsonMap): JsonMap {
  const nav = getSystem(ship, "navigation");
  return asRecord(ship.course) ?? asRecord(nav.course) ?? {};
}

export function getWaypoint(ship: JsonMap): Vec3 | null {
  const course = getCourse(ship);
  const destination = asRecord(course.destination)
    ?? asRecord(course.target_position)
    ?? asRecord(asRecord(ship.autopilot_state)?.destination);
  return destination ? toVec3(destination) : null;
}

export function computeEta(distanceMeters: number, speedMetersPerSecond: number): number | null {
  if (distanceMeters <= 0 || speedMetersPerSecond <= 0.01) return null;
  return distanceMeters / speedMetersPerSecond;
}

export function computeRelativeSpeed(ship: JsonMap, targetId: string): number | null {
  if (!targetId) return null;
  const contact = findContact(ship, targetId);
  if (!contact) return null;
  const shipVelocity = getVelocity(ship);
  return magnitude(subtract(shipVelocity, contact.velocity));
}

export function headingToTarget(ship: JsonMap, target: Vec3): Orientation {
  const from = getPosition(ship);
  const delta = subtract(target, from);
  const horizontal = Math.sqrt(delta.x * delta.x + delta.y * delta.y);
  return {
    pitch: Math.atan2(delta.z, Math.max(horizontal, 0.001)) * 180 / Math.PI,
    yaw: normalizeAngle(Math.atan2(delta.y, delta.x) * 180 / Math.PI),
    roll: getOrientation(ship).roll,
  };
}

export function deriveWorkflowStep(ship: JsonMap, tier: Tier): number {
  const contacts = getContacts(ship);
  const autopilot = getAutopilotSnapshot(ship);
  const queue = getQueueState(ship);
  const throttle = getThrottle(ship);
  const hasTarget = Boolean(autopilot.targetId || toStringValue(ship.target_id));

  if (tier === "arcade") {
    if (!contacts.length) return 0;
    if (!hasTarget) return 1;
    return autopilot.active || throttle > 0.02 ? 2 : 1;
  }

  if (tier === "cpu-assist") {
    if (!contacts.length) return 0;
    if (!hasTarget) return 1;
    if (queue.active || queue.pending.length > 0) return 3;
    return autopilot.active ? 2 : 1;
  }

  if (!contacts.length && throttle <= 0.02) return 0;
  if (!hasTarget) return 1;
  if (throttle > 0.02 || autopilot.active) return 2;
  return 3;
}
