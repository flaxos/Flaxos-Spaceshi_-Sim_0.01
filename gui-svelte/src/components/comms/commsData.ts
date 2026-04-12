import type { JsonMap } from "../helm/helmData.js";
import {
  asRecord,
  clamp,
  extractShipState,
  formatDistance,
  formatDuration,
  toNumber,
  toStringValue,
} from "../helm/helmData.js";
import { getTacticalContacts, type TacticalContact } from "../tactical/tacticalData.js";

export interface CommsProposal {
  proposalId: string;
  action: string;
  target: string;
  reason: string;
  confidence: number;
  params: JsonMap;
}

export interface ChoiceOption {
  optionId: string;
  label: string;
  description: string;
}

export interface CommsChoice {
  choiceId: string;
  contactId: string;
  prompt: string;
  timeout: number | null;
  presentedAt: number | null;
  defaultOption: string;
  options: ChoiceOption[];
}

export interface StationMessageRow {
  id: number;
  fromStation: string;
  fromPlayer: string;
  to: string;
  text: string;
  timestamp: number;
}

export function getCommsShip(gameState: JsonMap | null | undefined): JsonMap {
  return extractShipState(gameState);
}

export function getCommsState(ship: JsonMap): JsonMap {
  return asRecord(ship.comms) ?? {};
}

export function getAutoCommsState(ship: JsonMap): JsonMap {
  return asRecord(ship.auto_comms) ?? {};
}

export function getCommsContacts(ship: JsonMap): TacticalContact[] {
  return getTacticalContacts(ship);
}

export function getRecentCommsMessages(ship: JsonMap): JsonMap[] {
  const comms = getCommsState(ship);
  const source = Array.isArray(comms.recent_messages) ? comms.recent_messages : [];
  return source.map((item) => asRecord(item)).filter((item): item is JsonMap => Boolean(item));
}

export function getCommsProposals(ship: JsonMap): CommsProposal[] {
  const autoComms = getAutoCommsState(ship);
  const source = Array.isArray(autoComms.proposals) ? (autoComms.proposals as unknown[]) : [];
  return source
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      proposalId: toStringValue(item.proposal_id),
      action: toStringValue(item.action, "proposal"),
      target: toStringValue(item.target, "contact"),
      reason: toStringValue(item.reason, "Awaiting approval"),
      confidence: clamp(toNumber(item.confidence, 0), 0, 1),
      params: asRecord(item.params) ?? {},
    }));
}

export function normalizeCommsChoices(value: unknown): CommsChoice[] {
  const record = asRecord(value) ?? {};
  const source = Array.isArray(record.choices) ? (record.choices as unknown[]) : [];
  return source
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      choiceId: toStringValue(item.choice_id),
      contactId: toStringValue(item.contact_id, "unknown"),
      prompt: toStringValue(item.prompt, "Incoming message"),
      timeout: Number.isFinite(toNumber(item.timeout, Number.NaN)) ? toNumber(item.timeout, Number.NaN) : null,
      presentedAt: Number.isFinite(toNumber(item.presented_at, Number.NaN)) ? toNumber(item.presented_at, Number.NaN) : null,
      defaultOption: toStringValue(item.default_option),
      options: (Array.isArray(item.options) ? item.options : [])
        .map((option) => asRecord(option))
        .filter((option): option is JsonMap => Boolean(option))
        .map((option) => ({
          optionId: toStringValue(option.option_id),
          label: toStringValue(option.label, "Option"),
          description: toStringValue(option.description),
        })),
    }));
}

export function normalizeStationMessages(value: unknown): StationMessageRow[] {
  const record = asRecord(value) ?? {};
  const source = Array.isArray(record.messages) ? (record.messages as unknown[]) : [];
  return source
    .map((item) => asRecord(item))
    .filter((item): item is JsonMap => Boolean(item))
    .map((item) => ({
      id: toNumber(item.id, 0),
      fromStation: toStringValue(item.from_station, "unknown"),
      fromPlayer: toStringValue(item.from_player, ""),
      to: toStringValue(item.to, "all"),
      text: toStringValue(item.text),
      timestamp: toNumber(item.timestamp, 0),
    }));
}

export function recommendChoice(choice: CommsChoice): ChoiceOption | null {
  if (!choice.options.length) return null;
  if (choice.defaultOption) {
    const defaultMatch = choice.options.find((option) => option.optionId === choice.defaultOption);
    if (defaultMatch) return defaultMatch;
  }

  const positive = choice.options.find((option) => {
    const text = `${option.label} ${option.description}`.toLowerCase();
    return ["identify", "accept", "reply", "acknowledge", "stand down", "assist"].some((token) => text.includes(token));
  });

  return positive ?? choice.options[0] ?? null;
}

export function commsModeClass(ship: JsonMap): "active" | "silent" | "emcon" | "distress" | "offline" {
  const comms = getCommsState(ship);
  const status = toStringValue(comms.status, "offline").toLowerCase();
  if (status.includes("distress")) return "distress";
  if (status.includes("emcon")) return "emcon";
  if (status.includes("silent")) return "silent";
  if (status.includes("active")) return "active";
  return "offline";
}

export function emconLevelFromShip(ship: JsonMap): number {
  const ecm = asRecord(ship.ecm) ?? {};
  return Boolean(ecm.emcon_active) ? 5 : 0;
}

export function formatChoiceCountdown(choice: CommsChoice, nowSeconds: number): { remaining: number; progress: number } {
  if (choice.timeout == null || choice.presentedAt == null) {
    return { remaining: 0, progress: 1 };
  }
  const elapsed = Math.max(0, nowSeconds - choice.presentedAt);
  const remaining = Math.max(0, choice.timeout - elapsed);
  const progress = choice.timeout > 0 ? clamp(remaining / choice.timeout, 0, 1) : 0;
  return { remaining, progress };
}

export function humanMessageTimestamp(timestamp: number): string {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "--:--";
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatSignalDistance(distance: number): string {
  return formatDistance(distance);
}

export { asRecord, formatDistance, formatDuration, toNumber, toStringValue };
