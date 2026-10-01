import { isCommandRejected } from "./ws/commandResponse.js";

export interface ShipStation {
  station: string;
  claimed: boolean;
  player?: string;
}

export interface LobbyShip {
  id: string;
  name?: string;
  class?: string;
  faction?: string;
  stations?: ShipStation[];
}

interface LobbySnapshot {
  ships: LobbyShip[];
}

type SendCommand = (cmd: string, args: Record<string, unknown>) => Promise<unknown>;

function commandData(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || isCommandRejected(value)) throw new Error("Lobby read rejected");
  const envelope = value as Record<string, unknown>;
  if (envelope.success === false) throw new Error("Lobby read rejected");
  const data = envelope.response ?? envelope.data ?? envelope;
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Invalid lobby response");
  if (isCommandRejected(data) || (data as Record<string, unknown>).success === false) throw new Error("Lobby read rejected");
  return data as Record<string, unknown>;
}

/** One read-only, completion-paced loop for the visible, connected lobby.
 * Manual refresh shares the current request; retired requests never publish
 * snapshots, send the next stage, or schedule another timer. */
export function createLobbyRefresh(options: {
  send: SendCommand;
  onSnapshot: (snapshot: LobbySnapshot) => void;
  onUnavailable: () => void;
  onLoading: (loading: boolean) => void;
}) {
  let active = false;
  let destroyed = false;
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let flight: Promise<void> | null = null;

  function clearTimer() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  async function read(gen: number): Promise<void> {
    const current = () => active && !destroyed && gen === generation;
    try {
      const response = await options.send("list_ships", {});
      if (!current()) return;
      const data = commandData(response);
      if (!Array.isArray(data.ships) || !data.ships.every(ship => ship && typeof ship.id === "string")) {
        throw new Error("Invalid fleet response");
      }
      const fleet = data.ships as LobbyShip[];
      const stationReads = await Promise.allSettled(fleet.map(async ship => {
        const stationResponse = await options.send("station_status", { ship: ship.id });
        if (!current()) return { ...ship, stations: undefined };
        const stations = commandData(stationResponse).stations;
        if (!Array.isArray(stations) || !stations.every(row => row && typeof row.station === "string" && typeof row.claimed === "boolean")) {
          throw new Error("Invalid occupancy response");
        }
        return { ...ship, stations: stations as ShipStation[] };
      }));
      const ships = stationReads.map(result => {
        if (result.status === "rejected") throw result.reason;
        return result.value;
      });
      if (current()) options.onSnapshot({ ships });
    } catch {
      if (current()) options.onUnavailable();
    } finally {
      if (current()) {
        flight = null;
        options.onLoading(false);
        timer = setTimeout(() => { timer = null; void refresh(); }, 2000);
      }
    }
  }

  function refresh(): Promise<void> {
    if (!active || destroyed) return Promise.resolve();
    if (flight) return flight;
    clearTimer();
    options.onLoading(true);
    flight = read(generation);
    return flight;
  }

  function retire() {
    generation++;
    clearTimer();
    flight = null;
    options.onLoading(false);
  }

  return {
    refresh,
    setActive(next: boolean) {
      if (destroyed || next === active) return;
      active = next;
      retire();
      if (active) void refresh();
    },
    restart() {
      if (destroyed) return;
      retire();
      if (active) void refresh();
    },
    destroy() {
      active = false;
      destroyed = true;
      retire();
    },
  };
}
