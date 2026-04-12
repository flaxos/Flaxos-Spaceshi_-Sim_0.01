import type { JsonMap, Vec3 } from "../helm/helmData.js";
import {
  asRecord,
  clamp,
  extractShipState,
  formatDistance,
  formatSpeed,
  magnitude,
  toNumber,
  toStringValue,
  toVec3,
} from "../helm/helmData.js";
import { getTacticalContacts, type TacticalContact } from "../tactical/tacticalData.js";

export interface ScienceContact extends TacticalContact {
  signalSignature: number;
  irWatts: number;
  rcsSquareMeters: number;
  lastUpdate: number;
  detectionMethod: string;
}

export interface SpectralBand {
  id: string;
  label: string;
  value: number;
}

export const KNOWN_SHIP_CLASSES = [
  "Unknown",
  "Corvette",
  "Frigate",
  "Destroyer",
  "Cruiser",
  "Carrier",
  "Freighter",
  "Transport",
  "Gunboat",
  "Station",
] as const;

function seeded01(seedText: string): number {
  let hash = 0;
  for (let i = 0; i < seedText.length; i += 1) {
    hash = ((hash << 5) - hash + seedText.charCodeAt(i)) | 0;
  }
  return (Math.abs(hash) % 10_000) / 10_000;
}

export function getScienceShip(gameState: JsonMap | null | undefined): JsonMap {
  return extractShipState(gameState);
}

export function getScienceState(ship: JsonMap): JsonMap {
  return asRecord(ship.science) ?? {};
}

export function getScienceContacts(ship: JsonMap): ScienceContact[] {
  const tactical = getTacticalContacts(ship);
  const rawSensors = asRecord(ship.sensors) ?? {};
  const rawContacts = Array.isArray(rawSensors.contacts) ? (rawSensors.contacts as unknown[]) : [];
  const byId = new Map<string, JsonMap>();

  rawContacts
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .forEach((item) => {
      byId.set(toStringValue(item.id), item);
    });

  return tactical.map((contact) => {
    const raw = byId.get(contact.id) ?? {};
    const signature = toNumber(raw.signature, contact.signalStrength || seeded01(contact.id) * 1_000_000);
    const irWatts = signature > 0 ? signature : (0.25 + seeded01(`${contact.id}:ir`)) * 1_500_000;
    const rcsSquareMeters = Math.max(1, toNumber(raw.rcs_m2, (0.15 + seeded01(`${contact.id}:rcs`)) * 220));

    return {
      ...contact,
      signalSignature: signature,
      irWatts,
      rcsSquareMeters,
      lastUpdate: toNumber(raw.last_update, 0),
      detectionMethod: toStringValue(raw.detection_method, contact.detectionMethod),
    };
  });
}

export function findScienceContact(ship: JsonMap, contactId: string): ScienceContact | null {
  return getScienceContacts(ship).find((contact) => contact.id === contactId) ?? null;
}

export function spectralBandsForContact(contact: ScienceContact | null, spectralResult: JsonMap | null = null): SpectralBand[] {
  if (!contact) {
    return [
      { id: "infrared", label: "Infrared", value: 0 },
      { id: "radar", label: "Radar", value: 0 },
      { id: "plume", label: "Plume", value: 0 },
      { id: "noise", label: "Noise", value: 0 },
    ];
  }

  const spectralData = asRecord(spectralResult?.spectral_data) ?? {};
  const ir = asRecord(spectralData.ir_signature) ?? {};
  const rcs = asRecord(spectralData.rcs_data) ?? {};

  const totalIr = toNumber(ir.total_ir, contact.irWatts);
  const plume = toNumber(ir.plume_ir, totalIr * 0.45);
  const radar = toNumber(rcs.effective_rcs, contact.rcsSquareMeters);
  const noise = clamp((1 - contact.confidence) * 100, 3, 96);

  const maxValue = Math.max(totalIr, plume, radar * 1000, noise, 1);
  return [
    { id: "infrared", label: "Infrared", value: clamp((totalIr / maxValue) * 100, 0, 100) },
    { id: "radar", label: "Radar", value: clamp(((radar * 1000) / maxValue) * 100, 0, 100) },
    { id: "plume", label: "Plume", value: clamp((plume / maxValue) * 100, 0, 100) },
    { id: "noise", label: "Noise", value: noise },
  ];
}

export function inferredThrustProfile(contact: ScienceContact | null, spectralResult: JsonMap | null = null): { label: string; thrustKn: number; burnState: string } {
  if (!contact) return { label: "--", thrustKn: 0, burnState: "unknown" };

  const spectralData = asRecord(spectralResult?.spectral_data) ?? {};
  const drive = asRecord(spectralData.drive_inference) ?? {};
  const label = toStringValue(drive.drive_type, contact.speed > 250 ? "epstein-like" : "ion-like");
  const burnState = toStringValue(drive.burn_state, contact.speed > 180 ? "full" : "partial");
  const thrustKn = toNumber(drive.estimated_thrust_kn, Math.max(8, contact.speed * 0.12));
  return { label, thrustKn, burnState };
}

export function estimateMassFromContact(contact: ScienceContact | null): number {
  if (!contact) return 0;
  const accel = 2 + seeded01(`${contact.id}:accel`) * 32;
  const thrust = Math.max(20_000, contact.irWatts * 0.08);
  return Math.round(thrust / accel);
}

export function recommendClassFromMass(massKg: number): string {
  if (massKg <= 10_000) return "Corvette";
  if (massKg <= 45_000) return "Frigate";
  if (massKg <= 120_000) return "Destroyer";
  if (massKg <= 300_000) return "Cruiser";
  return "Carrier";
}

export function probeRows(ship: JsonMap): JsonMap[] {
  const sensors = asRecord(ship.sensors) ?? {};
  const probes = Array.isArray(sensors.probes) ? sensors.probes : [];
  return probes.map((item) => asRecord(item)).filter((item): item is JsonMap => Boolean(item));
}

export function currentNoiseFloor(ship: JsonMap): number {
  const sensors = asRecord(ship.sensors) ?? {};
  const ownEmissions = asRecord(sensors.own_emissions) ?? {};
  return toNumber(sensors.noise_floor, Math.max(0.00000001, toNumber(ownEmissions.ir_signature, 0.0001) * 0.000001));
}

export function confidencePercent(contact: ScienceContact | null): number {
  return contact ? clamp(contact.confidence * 100, 0, 100) : 0;
}

export function formatWatts(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} MW`;
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)} kW`;
  return `${value.toFixed(1)} W`;
}

export function formatSquareMeters(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${value.toFixed(value >= 100 ? 0 : 1)} m²`;
}

export function formatVectorShort(vec: Vec3): string {
  return `${vec.x.toFixed(0)}, ${vec.y.toFixed(0)}, ${vec.z.toFixed(0)}`;
}

export function pseudoAcceleration(contact: ScienceContact | null): number {
  if (!contact) return 0;
  return 2 + seeded01(`${contact.id}:acc`) * 30;
}

export function pseudoTargetMass(contact: ScienceContact | null): number {
  if (!contact) return 80_000;
  return Math.max(4_000, estimateMassFromContact(contact));
}

export { asRecord, formatDistance, formatSpeed, magnitude, toNumber, toStringValue, toVec3 };
