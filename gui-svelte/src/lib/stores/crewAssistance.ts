import { derived, writable } from "svelte/store";
import { crewSession } from "./crewSession.js";
import { missionState } from "./missionState.js";
import { wsClient } from "../ws/wsClient.js";

export interface CrewAssistance {
  ship_id: string;
  stations: Array<{ station: string; claimed: boolean; player?: string | null }>;
  crew_assistance: {
    mission_epoch: number;
    simulation_running: boolean;
    worker_running: boolean;
    ship_eligible: boolean;
    thermal_available: boolean;
    stations: Array<{ station: string; active: boolean; competence: number }>;
  };
}

const snapshot = writable<CrewAssistance | null>(null);
export const crewAssistance = { subscribe: snapshot.subscribe };

/** These existing Tycho docking missions share the same station guide. */
export function isDockingGuideScenario(scenarioId: string | null | undefined): boolean {
  return scenarioId === "01_tutorial_intercept" || scenarioId === "07_docking_test";
}

/** Mounted by the existing docking guidance panel. Retired sessions/epochs
 * cannot publish a late occupancy response or keep its poll chain alive. */
export function watchCrewAssistance(): () => void {
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let previousKey = "";
  async function poll(gen: number, ship: string, epoch: number | undefined): Promise<void> {
    try {
      const response = await wsClient.send("station_status", { ship }) as { ok?: boolean; response?: CrewAssistance };
      if (gen !== generation) return;
      const data = response.response;
      if (response.ok !== false && data?.ship_id === ship
          && Array.isArray(data.stations) && Array.isArray(data.crew_assistance?.stations)
          && (epoch === undefined || data.crew_assistance.mission_epoch === epoch)) {
        snapshot.set(data);
      } else snapshot.set(null);
    } catch { if (gen === generation) snapshot.set(null); }
    finally { if (gen === generation) timer = setTimeout(() => poll(gen, ship, epoch), 1000); }
  }
  const unsubscribe = derived([crewSession, missionState], ([session, mission]) => ({ session, mission }))
    .subscribe(({ session, mission }) => {
      const ship = session.shipId;
      const key = session.connected && session.registered && !session.needsRejoin && ship && session.station
        && isDockingGuideScenario(mission?.current_scenario_id)
        ? `${ship}:${session.station}:${mission.mission_epoch}` : "";
      if (key === previousKey) return;
      previousKey = key;
      generation++;
      if (timer) clearTimeout(timer);
      timer = null;
      snapshot.set(null);
      if (key && ship) void poll(generation, ship, mission?.mission_epoch);
    });
  return () => {
    unsubscribe(); generation++;
    if (timer) clearTimeout(timer);
    snapshot.set(null);
  };
}

export function stationCoverage(data: CrewAssistance | null, station: string): string {
  const human = data?.stations.find(row => row.station === station);
  if (!human) return "Coverage unavailable";
  if (human.claimed) return `Human: ${human.player || "crew member"}`;
  const cpu = data?.crew_assistance.stations.find(row => row.station === station);
  if (!data?.crew_assistance.ship_eligible || !cpu?.active || !(cpu.competence > 0)) return "Unstaffed";
  if (station === "helm") return "CPU seat is passive — approve a navigation program";
  if (station === "engineering" && !data.crew_assistance.thermal_available) return "CPU registered — no thermal system fitted";
  return data.crew_assistance.worker_running ? "CPU heat-sink watch" : "CPU heat-sink watch waiting";
}
