import { get, writable } from "svelte/store";
import { wsClient } from "../ws/wsClient.js";
import { describeCommandFailure, isCommandRejected } from "../ws/commandResponse.js";
import { playerShipId } from "./playerShip.js";
import { startPolling } from "./gameState.js";

export interface CrewSession {
  connected: boolean;
  registered: boolean;
  shipId: string | null;
  station: string | null;
  needsRejoin: boolean;
  busy: boolean;
  error: string;
}

const _session = writable<CrewSession>({
  connected: false, registered: false, shipId: null, station: null,
  needsRejoin: false, busy: false, error: "",
});
export const crewSession = { subscribe: _session.subscribe };

let connectionGeneration = 0;
let refreshSequence = 0;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let initialized = false;

function unwrap(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || isCommandRejected(value)) return null;
  const envelope = value as Record<string, unknown>;
  const data = envelope.response ?? envelope.data ?? envelope;
  return data && typeof data === "object" ? data as Record<string, unknown> : null;
}

function applyAssignment(shipId: string | null, station: string | null): void {
  const old = get(_session);
  _session.update(s => ({ ...s, shipId, station }));
  if (get(playerShipId) !== shipId) playerShipId.set(shipId);
  else if (old.station !== station && wsClient.status === "connected") startPolling(shipId);
}

/** Session fields from my_status, rather than claim-button intent, are authoritative. */
export async function refreshCrewSession(): Promise<CrewSession | null> {
  const gen = connectionGeneration;
  const seq = ++refreshSequence;
  if (!get(_session).connected) return null;
  try {
    const response = await wsClient.send("my_status", {});
    if (gen !== connectionGeneration || seq !== refreshSequence) return null;
    const data = unwrap(response);
    if (!data) {
      applyAssignment(null, null);
      _session.update(s => ({ ...s, error: describeCommandFailure(response, "Unable to verify crew session") }));
      return null;
    }
    const session = get(_session);
    if (!session.needsRejoin) {
      applyAssignment(typeof data.ship_id === "string" ? data.ship_id : null,
        typeof data.station === "string" ? data.station : null);
    }
    return get(_session);
  } catch (error) {
    if (gen === connectionGeneration && seq === refreshSequence) {
      _session.update(s => ({ ...s, error: error instanceof Error ? error.message : String(error) }));
    }
    return null;
  }
}

async function registerAndPoll(gen: number): Promise<void> {
  try {
    const response = await wsClient.send("register_client", { client_name: "bridge-gui" });
    if (gen !== connectionGeneration) return;
    if (isCommandRejected(response)) throw new Error(describeCommandFailure(response, "Registration rejected"));
    _session.update(s => ({ ...s, registered: true, error: "" }));
    await refreshCrewSession();
  } catch (error) {
    if (gen === connectionGeneration) _session.update(s => ({ ...s, error: error instanceof Error ? error.message : String(error) }));
  }
  if (gen === connectionGeneration && get(_session).connected) {
    pollTimer = setTimeout(() => pollSession(gen), 2000);
  }
}

async function pollSession(gen: number): Promise<void> {
  if (gen !== connectionGeneration || !get(_session).connected) return;
  if (!get(_session).registered) { await registerAndPoll(gen); return; }
  await refreshCrewSession();
  if (gen === connectionGeneration) pollTimer = setTimeout(() => pollSession(gen), 2000);
}

function disconnectSession(): void {
  connectionGeneration++;
  refreshSequence++;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
  const old = get(_session);
  _session.set({ connected: false, registered: false, shipId: null, station: null,
    needsRejoin: old.needsRejoin || !!old.shipId || !!old.station, busy: false, error: "" });
  playerShipId.set(null);
}

function connectSession(): void {
  if (get(_session).connected) return;
  const gen = ++connectionGeneration;
  _session.update(s => ({ ...s, connected: true, registered: false, busy: false, error: "" }));
  registerAndPoll(gen);
}

export function initializeCrewSession(): void {
  if (initialized) return;
  initialized = true;
  wsClient.addEventListener("status_change", e => {
    const status = (e as CustomEvent<{ status: string }>).detail.status;
    if (status === "connected") connectSession();
    else if (status === "disconnected") disconnectSession();
  });
  wsClient.addEventListener("connection_status", e => {
    const connected = (e as CustomEvent<{ tcp_connected?: boolean }>).detail.tcp_connected;
    if (connected === false) disconnectSession();
    else if (connected === true && wsClient.status === "connected") connectSession();
  });
  wsClient.addEventListener("mission_changed", () => { void refreshCrewSession(); });
  if (wsClient.status === "connected") connectSession();
}

/** Only an explicit player action assigns and claims a station after reconnect. */
export async function joinCrewStation(shipId: string, station: string): Promise<boolean> {
  const gen = connectionGeneration;
  if (!get(_session).registered || get(_session).busy) return false;
  _session.update(s => ({ ...s, busy: true, error: "" }));
  try {
    const assigned = await wsClient.send("assign_ship", { ship: shipId });
    if (gen !== connectionGeneration) return false;
    if (isCommandRejected(assigned)) throw new Error(describeCommandFailure(assigned, "Ship assignment rejected"));
    const claimed = await wsClient.send("claim_station", { ship: shipId, station });
    if (gen !== connectionGeneration) return false;
    if (isCommandRejected(claimed)) throw new Error(describeCommandFailure(claimed, "Station claim rejected"));
    _session.update(s => ({ ...s, needsRejoin: false }));
    const verified = await refreshCrewSession();
    if (!verified || verified.shipId !== shipId || verified.station !== station) throw new Error("Station claim could not be verified. Refresh the lobby and try again.");
    return true;
  } catch (error) {
    if (gen === connectionGeneration) {
      _session.update(s => ({ ...s, error: error instanceof Error ? error.message : String(error) }));
      await refreshCrewSession();
    }
    return false;
  } finally {
    if (gen === connectionGeneration) _session.update(s => ({ ...s, busy: false }));
  }
}

export async function releaseCrewStation(): Promise<void> {
  const gen = connectionGeneration;
  if (get(_session).busy) return;
  _session.update(s => ({ ...s, busy: true, error: "" }));
  try {
    const response = await wsClient.send("release_station", {});
    if (gen !== connectionGeneration) return;
    if (isCommandRejected(response)) throw new Error(describeCommandFailure(response, "Station release rejected"));
    await refreshCrewSession();
  } catch (error) {
    if (gen === connectionGeneration) _session.update(s => ({ ...s, error: error instanceof Error ? error.message : String(error) }));
  } finally {
    if (gen === connectionGeneration) _session.update(s => ({ ...s, busy: false }));
  }
}
