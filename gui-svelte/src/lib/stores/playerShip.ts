/**
 * playerShip store — tracks the active player ship ID.
 * Also keeps wsClient.setActiveShipId() in sync to avoid circular deps.
 */

import { writable } from "svelte/store";
import { wsClient } from "../ws/wsClient.js";
import { startPolling, stopPolling } from "./gameState.js";

const _playerShipId = writable<string | null>(null);

// Keep wsClient ship ID in sync (needed for sendShipCommand)
_playerShipId.subscribe((id) => {
  wsClient.setActiveShipId(id);
  if (id) {
    startPolling(id);
  } else {
    // Still poll without ship ID — server will return minimal state
    startPolling(null);
  }
});

export const playerShipId = {
  subscribe: _playerShipId.subscribe,
  set: (id: string | null) => _playerShipId.set(id),
};

/** Call once at startup to connect and begin polling. */
export function initializeConnection(): void {
  wsClient.addEventListener("status_change", (e) => {
    const { status } = (e as CustomEvent<{ status: string }>).detail;
    if (status === "connected") {
      // Resume polling when reconnected
      const currentId = (() => {
        let val: string | null = null;
        const unsub = _playerShipId.subscribe((v) => { val = v; });
        unsub();
        return val;
      })();
      startPolling(currentId);
    } else if (status === "disconnected") {
      stopPolling();
    }
  });

  wsClient.connect().catch((err) => {
    console.error("[wsClient] Initial connect failed:", err);
  });
}
