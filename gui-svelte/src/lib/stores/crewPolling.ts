import { get, derived } from "svelte/store";
import { crewSession, type CrewSession } from "./crewSession.js";
import { gameState } from "./gameState.js";
import { wsClient } from "../ws/wsClient.js";
import { isCommandRejected } from "../ws/commandResponse.js";
import { extractShipState, getLockedTargetId, getTargetingSummary } from "../../components/tactical/tacticalData.js";

/** Only server-confirmed permissions authorize background ship reads. */
export function canPollShipCommand(command: string, session: CrewSession = get(crewSession)): boolean {
  return wsClient.isConnected && session.connected && session.registered && !session.busy
    && !session.needsRejoin && !!session.shipId && !!session.station
    && session.availableCommands?.includes(command) === true;
}

/** Skipped, rejected, failed and retired reads have no displayable result. */
export async function pollShipCommand(command: string, args: Record<string, unknown> = {}): Promise<unknown | null> {
  const session = get(crewSession);
  if (!canPollShipCommand(command, session) || (args.ship != null && args.ship !== session.shipId)) return null;
  try {
    const response = await wsClient.sendShipCommand(command, { ...args, ship: session.shipId });
    const current = get(crewSession);
    return current.authorityRevision === session.authorityRevision && canPollShipCommand(command, current)
      && !isCommandRejected(response) ? response : null;
  } catch { return null; }
}

let lockKey = "";
let lockRevision = 0;
/** Local/nav selection never establishes a weapons lock. Track lock transitions as well as IDs. */
export const confirmedTargetLock = derived([gameState, crewSession], ([state, session]) => {
  const ship = extractShipState(state);
  const targeting = getTargetingSummary(ship);
  const lockedTarget = getLockedTargetId(ship);
  const key = JSON.stringify([session.authorityRevision, state.mission_epoch, targeting.lockState, lockedTarget]);
  if (key !== lockKey) { lockKey = key; lockRevision++; }
  const verified = wsClient.isConnected && session.connected && session.registered && !session.busy
    && !session.needsRejoin && !!session.shipId && !!session.station && session.availableCommands !== null;
  const targetId = verified && targeting.lockState === "locked" && lockedTarget ? lockedTarget : null;
  return { targetId, revision: lockRevision };
});

// Observe unlock/relock transitions even while no component is displaying the store.
confirmedTargetLock.subscribe(() => {});

export async function pollLockedShipCommand(command: string): Promise<unknown | null> {
  const lock = get(confirmedTargetLock);
  if (!lock.targetId) return null;
  const response = await pollShipCommand(command);
  return get(confirmedTargetLock).revision === lock.revision ? response : null;
}
