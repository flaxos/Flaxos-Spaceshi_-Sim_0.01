/**
 * gameState store — primary simulation state.
 * Polls get_state at 200ms using a generation-based setTimeout chain
 * (same pattern as state-manager.js) so reconnect never spawns duplicate chains.
 */

import { writable, derived } from "svelte/store";
import { wsClient } from "../ws/wsClient.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type GameState = Record<string, any>;

const POLL_MS = 200;

const _gameState = writable<GameState>({});
let _generation = 0;
let _lastFullState: GameState = {};
let _isFetching = false;
let _lastEventTime = 0;

// ── Deep merge (mirrors StateManager._deepMerge) ──────────────────────────

function _deepMerge(target: GameState, source: GameState): GameState {
  if (source === null || typeof source !== "object") return source as GameState;
  if (Array.isArray(source)) return source;

  const output = { ...target };
  for (const key in source) {
    if (!Object.prototype.hasOwnProperty.call(source, key)) continue;
    const val = source[key];
    if (
      val !== null &&
      typeof val === "object" &&
      !Array.isArray(val) &&
      target[key] &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      output[key] = _deepMerge(target[key] as GameState, val as GameState);
    } else {
      output[key] = val;
    }
  }
  return output;
}

// ── Poll loop ─────────────────────────────────────────────────────────────

async function _fetchState(gen: number, shipId?: string | null): Promise<void> {
  if (gen !== _generation || _isFetching) return;
  _isFetching = true;

  try {
    const params: Record<string, unknown> = {};
    if (shipId) params.ship = shipId;

    const response = await wsClient.send("get_state", params) as GameState;
    if (!response || response.ok === false) return;

    let merged: GameState;
    if (response._delta) {
      merged = _deepMerge(_lastFullState, response);
      delete merged._delta;
    } else {
      merged = response;
    }

    _lastFullState = merged;
    _gameState.set(merged);
  } catch {
    // silently skip failed polls
  } finally {
    _isFetching = false;
    if (gen === _generation) {
      setTimeout(() => _fetchState(gen, shipId), POLL_MS);
    }
  }
}

export function startPolling(shipId?: string | null): void {
  _generation++;
  const gen = _generation;
  _fetchState(gen, shipId);
}

export function stopPolling(): void {
  _generation++; // invalidates running chain
}

// ── Event polling (mirrors StateManager._fetchEvents) ─────────────────────

const _events = writable<GameState[]>([]);

async function _fetchEvents(gen: number): Promise<void> {
  if (gen !== _generation) return;
  try {
    const response = await wsClient.send("get_events", { since: _lastEventTime }) as {
      ok: boolean;
      events: GameState[];
    };
    if (response?.ok && Array.isArray(response.events)) {
      for (const event of response.events) {
        if ((event.t as number) > _lastEventTime) _lastEventTime = event.t as number;
      }
      if (response.events.length > 0) {
        _events.update((prev) => {
          const combined = [...prev, ...response.events];
          return combined.length > 1000 ? combined.slice(-1000) : combined;
        });
      }
    }
  } catch { /* silently skip */ }
  finally {
    if (gen === _generation) setTimeout(() => _fetchEvents(gen), 1000);
  }
}

// Start event polling when WS connects
wsClient.addEventListener("status_change", (e) => {
  const detail = (e as CustomEvent<{ status: string }>).detail;
  if (detail.status === "connected") {
    _generation++;
    const gen = _generation;
    _fetchEvents(gen);
  }
});

// ── Derived helpers ───────────────────────────────────────────────────────

/** Extract the player ship state from game state. */
export const shipState = derived(_gameState, ($gs) => {
  if ($gs.state) return $gs.state;
  if ($gs.ship) return $gs.ship;
  const ships = $gs.ships;
  if (Array.isArray(ships) && ships.length > 0) return ships[0];
  if (ships && typeof ships === "object") {
    const keys = Object.keys(ships);
    if (keys.length > 0) return ships[keys[0]];
  }
  return $gs;
});

export const gameState = { subscribe: _gameState.subscribe };
export const events = { subscribe: _events.subscribe };
export { _deepMerge };
