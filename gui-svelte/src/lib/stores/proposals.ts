/**
 * proposals store — derived per-station proposal queues and auto-system states.
 * No extra polling — shipState already polls at 200ms.
 */

import { derived } from "svelte/store";
import { shipState } from "./gameState.js";

export interface Proposal {
  id: string;
  action: string;
  confidence: number;
  reason?: string;
  time_remaining?: number;
  total_time?: number;
  crew_efficiency?: number;
  target_id?: string;
  target?: string;
  auto_execute?: boolean;
  urgent: boolean;
}

export type StationKey =
  | "tactical"
  | "engineering"
  | "ops"
  | "comms"
  | "science"
  | "fleet";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeProposals(raw: unknown): Proposal[] {
  if (!Array.isArray(raw)) return [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (raw as any[])
    .filter((p) => p && typeof p === "object")
    .map((p) => {
      const timeRemaining =
        p.time_remaining != null ? Number(p.time_remaining) : undefined;
      return {
        id: String(p.proposal_id ?? p.id ?? ""),
        action: String(p.description ?? p.action ?? ""),
        confidence: Number(p.confidence ?? 0),
        reason: p.reason != null ? String(p.reason) : undefined,
        time_remaining: timeRemaining,
        total_time: p.total_time != null ? Number(p.total_time) : 30,
        crew_efficiency:
          p.crew_efficiency != null ? Number(p.crew_efficiency) : undefined,
        target_id: p.target_id != null ? String(p.target_id) : undefined,
        target: p.target != null ? String(p.target) : undefined,
        auto_execute: Boolean(p.auto_execute),
        urgent: timeRemaining != null ? timeRemaining < 5 : false,
      };
    });
}

export const proposals = derived(shipState, ($ship) => ({
  tactical: normalizeProposals($ship?.auto_tactical?.proposals),
  engineering: normalizeProposals($ship?.auto_engineering?.proposals),
  ops: normalizeProposals($ship?.auto_ops?.proposals),
  comms: normalizeProposals($ship?.auto_comms?.proposals),
  science: normalizeProposals($ship?.auto_science?.proposals),
  fleet: normalizeProposals($ship?.auto_fleet?.proposals),
}));

export const autoSystems = derived(shipState, ($ship) => ({
  tactical: {
    enabled: Boolean($ship?.auto_tactical?.enabled),
    engagement_mode: String($ship?.auto_tactical?.engagement_mode ?? "weapons_hold"),
  },
  engineering: {
    enabled: Boolean($ship?.auto_engineering?.enabled),
  },
  ops: {
    enabled: Boolean($ship?.auto_ops?.enabled),
    mode: String($ship?.auto_ops?.mode ?? "manual"),
  },
  comms: {
    enabled: Boolean($ship?.auto_comms?.enabled),
  },
  science: {
    enabled: Boolean($ship?.auto_science?.enabled),
  },
  fleet: {
    enabled: Boolean($ship?.auto_fleet?.enabled),
  },
}));
