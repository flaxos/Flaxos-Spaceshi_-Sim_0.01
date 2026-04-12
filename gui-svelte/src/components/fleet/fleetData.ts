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

export interface FleetShipRow {
  id: string;
  name: string;
  className: string;
  hullPercent: number;
  status: string;
  isFlagship: boolean;
  position: Vec3;
  velocity: Vec3;
}

export interface FleetProposal {
  proposalId: string;
  action: string;
  target: string;
  reason: string;
  confidence: number;
  params: JsonMap;
}

export interface SharedFleetContact {
  id: string;
  classification: string;
  sourceShip: string;
  threatLevel: string;
  hostile: boolean;
  distance: number;
  bearing: number;
}

function seededPercent(seedText: string): number {
  let hash = 0;
  for (let i = 0; i < seedText.length; i += 1) hash = ((hash << 5) - hash + seedText.charCodeAt(i)) | 0;
  return Math.abs(hash % 85) + 15;
}

export function getFleetShip(gameState: JsonMap | null | undefined): JsonMap {
  return extractShipState(gameState);
}

export function getFleetCoordState(ship: JsonMap): JsonMap {
  return asRecord(ship.fleet_coord) ?? {};
}

export function getFleetStatusRecord(response: unknown): JsonMap {
  return asRecord(response) ?? {};
}

export function fleetIdFromRecord(record: JsonMap): string {
  return toStringValue(record.fleet_id) || toStringValue(asRecord(record.fleet)?.fleet_id);
}

export function fleetShipsFromStatus(response: unknown): FleetShipRow[] {
  const record = getFleetStatusRecord(response);
  const source = Array.isArray(record.ships) ? (record.ships as unknown[]) : [];

  return source
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => {
      const id = toStringValue(item.ship_id, "unknown");
      const position = toVec3(item.position);
      const velocity = toVec3(item.velocity);
      const systemsOnline = asRecord(item.systems_online) ?? {};
      const statuses = Object.values(systemsOnline).map((value) => Boolean(value));
      const onlineRatio = statuses.length ? statuses.filter(Boolean).length / statuses.length : 0.85;
      const hullPercent = clamp(toNumber(item.hull_percent, onlineRatio * 100), 0, 100);

      return {
        id,
        name: toStringValue(item.name, id),
        className: toStringValue(item.class, "Escort"),
        hullPercent,
        status: toStringValue(item.status, hullPercent < 40 ? "damaged" : "nominal"),
        isFlagship: Boolean(item.is_flagship),
        position,
        velocity,
      };
    });
}

export function fleetSummaryFromTactical(response: unknown): JsonMap {
  return asRecord(response) ?? {};
}

export function autoFleetProposals(value: unknown): FleetProposal[] {
  const record = asRecord(value) ?? {};
  const source = Array.isArray(record.proposals) ? (record.proposals as unknown[]) : [];
  return source
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      proposalId: toStringValue(item.proposal_id),
      action: toStringValue(item.action, "proposal"),
      target: toStringValue(item.target, "fleet"),
      reason: toStringValue(item.reason, "Awaiting approval"),
      confidence: clamp(toNumber(item.confidence, 0), 0, 1),
      params: asRecord(item.params) ?? {},
    }));
}

export function localSharedContacts(ship: JsonMap): SharedFleetContact[] {
  return getTacticalContacts(ship).map((contact) => ({
    id: contact.id,
    classification: contact.classification,
    sourceShip: toStringValue(asRecord(contact as unknown as JsonMap)?.source_ship, "LOCAL"),
    threatLevel: contact.threatLevel,
    hostile: ["orange", "red"].includes(contact.threatLevel),
    distance: contact.distance,
    bearing: contact.bearing,
  }));
}

export function formationLabel(form: string): string {
  return form.replaceAll("_", " ").toUpperCase();
}

export function statusClass(status: string): "critical" | "warning" | "nominal" {
  const lower = status.toLowerCase();
  if (["damaged", "retreating", "broken", "offline"].some((token) => lower.includes(token))) return "critical";
  if (["forming", "engaging", "holding"].some((token) => lower.includes(token))) return "warning";
  return "nominal";
}

export function contactPosition(contact: TacticalContact): Vec3 {
  return contact.position;
}

export function contactSpeed(contact: TacticalContact): number {
  return magnitude(contact.velocity);
}

export { asRecord, formatDistance, formatSpeed, magnitude, toNumber, toStringValue, toVec3 };
