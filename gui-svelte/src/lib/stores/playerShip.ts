/**
 * playerShip store — tracks the active player ship ID.
 * Also keeps wsClient.setActiveShipId() in sync to avoid circular deps.
 */

import { get, writable } from "svelte/store";
import { wsClient } from "../ws/wsClient.js";
import { startPolling, stopPolling } from "./gameState.js";
import { selectedTargetId } from "./selectedTarget.js";
import { selectedScienceContactId } from "./scienceUi.js";

const _playerShipId = writable<string | null>(null);

// Keep wsClient ship ID in sync (needed for sendShipCommand)
_playerShipId.subscribe((id) => {
  wsClient.setActiveShipId(id);
  selectedTargetId.clear();
  selectedScienceContactId.set("");
  if (wsClient.status === "connected") startPolling(id);
  else stopPolling();
});

export const playerShipId = {
  subscribe: _playerShipId.subscribe,
  set: (id: string | null) => _playerShipId.set(id),
};

let initialized = false;

/** Call once at startup. The session store owns authoritative assignment. */
export function initializeConnection(): void {
  if (initialized) return;
  initialized = true;
  wsClient.addEventListener("status_change", (e) => {
    const { status } = (e as CustomEvent<{ status: string }>).detail;
    if (status === "connected") {
      startPolling(get(_playerShipId));
    } else if (status === "disconnected") {
      _playerShipId.set(null);
      wsClient.setActiveShipId(null);
      stopPolling();
    }
  });

  wsClient.connect().catch((err) => {
    console.error("[wsClient] Initial connect failed:", err);
  });
}
