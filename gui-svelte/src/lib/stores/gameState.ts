/**
 * gameState store — primary simulation state.
 * Polls get_state at 200ms using a generation-based setTimeout chain
 * Each poll chain owns its generation. Retired requests cannot publish state
 * or prevent a new ship/session from starting its own chain.
 */

import { writable, derived } from "svelte/store";
import { wsClient } from "../ws/wsClient.js";
import { selectedTargetId } from "./selectedTarget.js";
import { selectedScienceContactId } from "./scienceUi.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type GameState = Record<string, any>;

const POLL_MS = 200;

const _gameState = writable<GameState>({});
let _generation = 0;
let _lastFullState: GameState = {};
let _hasFullState = false;
let _stateTimer: ReturnType<typeof setTimeout> | null = null;
let _eventGeneration = 0;
let _eventTimer: ReturnType<typeof setTimeout> | null = null;
let _lastEventId = 0;

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
  if (gen !== _generation) return;

  try {
    // Console and UI share a server delta baseline on this socket. Every UI
    // read must be self-contained, even when another reader consumed a change.
    const params: Record<string, unknown> = { full: true };
    if (shipId) params.ship = shipId;

    const response = await wsClient.send("get_state", params) as GameState;
    if (gen !== _generation || !response || response.ok === false) return;

    // A mission reset can retain the ship ID while restarting simulation time.
    const epochChanged = typeof response.mission_epoch === "number"
      && typeof _lastFullState.mission_epoch === "number" && response.mission_epoch !== _lastFullState.mission_epoch;
    if (epochChanged || (typeof response.t === "number" && typeof _lastFullState.t === "number" && response.t < _lastFullState.t)) {
      _clearState();
      _startEventPolling();
    }

    let merged: GameState;
    if (response._delta) {
      if (!_hasFullState) return; // wait for a snapshot instead of merging another session's delta
      // server.main deltas replace changed top-level fields, including state.
      merged = { ..._lastFullState, ...response };
      delete merged._delta;
    } else {
      merged = response;
      _hasFullState = true;
    }

    _lastFullState = merged;
    _gameState.set(merged);
  } catch {
    // silently skip failed polls
  } finally {
    if (gen === _generation) {
      _stateTimer = setTimeout(() => _fetchState(gen, shipId), POLL_MS);
    }
  }
}

export function startPolling(shipId?: string | null): void {
  _generation++;
  if (_stateTimer) clearTimeout(_stateTimer);
  _stateTimer = null;
  _clearState();
  _startEventPolling();
  const gen = _generation;
  _fetchState(gen, shipId);
}

export function stopPolling(): void {
  _generation++; // invalidates running chain
  if (_stateTimer) clearTimeout(_stateTimer);
  _stateTimer = null;
  _clearState();
  _stopEventPolling();
}

function _clearState(): void {
  _lastFullState = {};
  _hasFullState = false;
  _gameState.set({});
  selectedTargetId.clear();
  selectedScienceContactId.set("");
}

// ── Event polling (mirrors StateManager._fetchEvents) ─────────────────────

const _events = writable<GameState[]>([]);

async function _fetchEvents(gen: number): Promise<void> {
  if (gen !== _eventGeneration) return;
  try {
    // The server returns a recent, station-filtered window; `since` is not a
    // supported cursor. EventLogBuffer IDs increase even while time is paused.
    const response = await wsClient.send("get_events", {}) as {
      ok: boolean;
      events: GameState[];
    };
    if (gen !== _eventGeneration) return;
    if (response?.ok && Array.isArray(response.events)) {
      const seen = new Set<number>();
      const newEvents = response.events.filter(event => {
        if (!Number.isSafeInteger(event.id) || event.id <= _lastEventId || seen.has(event.id)) return false;
        seen.add(event.id);
        return true;
      });
      for (const event of newEvents) {
        _lastEventId = Math.max(_lastEventId, event.id);
      }
      if (newEvents.length > 0) {
        _events.update((prev) => {
          const combined = [...prev, ...newEvents];
          return combined.length > 1000 ? combined.slice(-1000) : combined;
        });
      }
    }
  } catch { /* silently skip */ }
  finally {
    if (gen === _eventGeneration) _eventTimer = setTimeout(() => _fetchEvents(gen), 1000);
  }
}

function _stopEventPolling(): void {
  _eventGeneration++;
  if (_eventTimer) clearTimeout(_eventTimer);
  _eventTimer = null;
  // Ship/station changes, disconnects and observed mission epochs invalidate
  // both the cursor and pending replies. A reconnect can reach a new server
  // whose IDs start over; a mission reset keeps IDs monotonic on this server.
  _lastEventId = 0;
  _events.set([]);
}

function _startEventPolling(): void {
  _stopEventPolling();
  if (wsClient.status === "connected") _fetchEvents(_eventGeneration);
}

// ── Derived helpers ───────────────────────────────────────────────────────

/** Extract the player ship state from game state. */
export const shipState = derived(_gameState, ($gs) => {
  if ($gs.state) return $gs.state;
  if ($gs.ship && typeof $gs.ship === "object") return $gs.ship;
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
