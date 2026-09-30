import { get, writable } from "svelte/store";
import { wsClient } from "../ws/wsClient.js";
import { crewSession } from "./crewSession.js";
import { playerShipId } from "./playerShip.js";
import { startPolling } from "./gameState.js";

export interface SharedMission {
  available?: boolean;
  name?: string;
  mission_status?: string;
  status?: string;
  mission_epoch?: number;
  current_scenario_id?: string | null;
  success_message?: string;
  failure_message?: string;
}

const _mission = writable<SharedMission | null>(null);
export const missionState = { subscribe: _mission.subscribe };
let generation = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
let active = false;

async function poll(gen: number): Promise<void> {
  if (gen !== generation || !active) return;
  try {
    const response = await wsClient.send("get_mission", {}) as { ok?: boolean; mission?: SharedMission };
    if (gen !== generation || response?.ok === false || !response?.mission) return;
    const previous = get(_mission);
    if (previous?.mission_epoch !== undefined && response.mission.mission_epoch !== previous.mission_epoch) {
      startPolling(get(playerShipId));
    }
    _mission.set(response.mission);
  } catch { /* disconnected/read failures are retried by the current generation */ }
  finally {
    // Terminal outcomes remain observable; keep polling to notice a shared reset.
    if (gen === generation && active) timer = setTimeout(() => poll(gen), 1000);
  }
}

export function refreshSharedMission(): void {
  generation++;
  if (timer) clearTimeout(timer);
  timer = null;
  _mission.set(null);
  if (active) poll(generation);
}

crewSession.subscribe(session => {
  const nextActive = session.connected && session.registered;
  if (nextActive === active) return;
  active = nextActive;
  refreshSharedMission();
});

wsClient.addEventListener("mission_changed", refreshSharedMission);
