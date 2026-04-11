/**
 * State Manager
 * Manages simulation state synchronization and distribution to components
 */

import { wsClient } from "./ws-client.js";

class StateManager extends EventTarget {
  constructor() {
    super();
    this._state = {};
    this._events = [];
    this._subscribers = new Map();
    this._lastFullState = null;
    this._lastStateUpdate = 0;
    this._lastEventTime = 0;
    this._playerShipId = null;

    // Configuration
    this.config = {
      statePollMs: 200,      // Poll state every 200ms (5Hz)
      eventPollMs: 1000,     // Poll events every 1s
      autoPoll: true,        // Start polling on connect
    };

    // Update Throttling
    this._updateQueued = false;
    this._pendingState = null;
    this._pollTimer = null;
    this._eventTimer = null;
    this._pollGeneration = 0;
  }

  setPlayerShipId(shipId) {
    if (this._playerShipId === shipId) return;
    this._playerShipId = shipId;
    console.log("[StateManager] Player ship ID set to:", shipId);
    this._fetchState();
  }

  getPlayerShipId() {
    return this._playerShipId;
  }

  init() {
    wsClient.addEventListener("status_change", (e) => {
      if (e.detail.status === "connected" && this.config.autoPoll) {
        this.startPolling();
      } else if (e.detail.status === "disconnected") {
        this.stopPolling();
      }
    });

    if (wsClient.status === "connected" && this.config.autoPoll) {
      this.startPolling();
    }
  }

  startPolling() {
    this.config.autoPoll = true;
    this._pollGeneration++;
    if (this._pollTimer) clearTimeout(this._pollTimer);
    if (this._eventTimer) clearTimeout(this._eventTimer);
    const gen = this._pollGeneration;
    this._fetchState(gen);
    this._fetchEvents(gen);
  }

  stopPolling() {
    this.config.autoPoll = false;
    if (this._pollTimer) clearTimeout(this._pollTimer);
    if (this._eventTimer) clearTimeout(this._eventTimer);
    this._pollTimer = null;
    this._eventTimer = null;
  }

  async _fetchState(gen) {
    if (!this.config.autoPoll || gen !== this._pollGeneration) return;
    try {
      const params = {};
      if (this._playerShipId) params.ship = this._playerShipId;

      const response = await wsClient.send("get_state", params);

      if (response && response.ok !== false) {
        // Auto-detect player ship if not set
        if (!this._playerShipId) {
          if (response.ship) {
            this._playerShipId = response.ship;
          } else if (Array.isArray(response.ships) && response.ships.length > 0) {
            this._playerShipId = response.ships[0]?.id;
          }
        }

        let merged;
        const prev = this._lastFullState || {};

        if (response._delta) {
          merged = { ...prev, ...response };
          ["state", "projectiles", "torpedoes", "ships"].forEach(key => {
            if (response[key] && prev[key]) {
               if (Array.isArray(response[key])) {
                 merged[key] = response[key];
               } else if (typeof response[key] === "object" && typeof prev[key] === "object") {
                 merged[key] = { ...prev[key], ...response[key] };
               }
            }
          });
          delete merged._delta;
        } else {
          merged = response;
        }

        this._lastFullState = merged;
        this._updateState(merged);
      }
    } catch (error) {
      // Ignore polling errors
    } finally {
      if (this.config.autoPoll && gen === this._pollGeneration) {
        this._pollTimer = setTimeout(() => this._fetchState(gen), this.config.statePollMs);
      }
    }
  }

  async _fetchEvents(gen) {
    if (!this.config.autoPoll || gen !== this._pollGeneration) return;
    try {
      const response = await wsClient.send("get_events", { since: this._lastEventTime });
      if (response && response.ok && Array.isArray(response.events)) {
        for (const event of response.events) {
          if (event.t > this._lastEventTime) {
            this._lastEventTime = event.t;
          }
          this._handleEvent(event);
        }
      }
    } catch (error) {
      // Silently fail events
    } finally {
      if (this.config.autoPoll && gen === this._pollGeneration) {
        this._eventTimer = setTimeout(() => this._fetchEvents(gen), this.config.eventPollMs);
      }
    }
  }

  _handleEvent(event) {
    this._events.push(event);
    this.dispatchEvent(new CustomEvent("event", { detail: event }));
    while (this._events.length > 1000) {
      this._events.shift();
    }
  }

  _shallowFreeze(obj) {
    if (obj === null || typeof obj !== "object") return obj;
    return Object.freeze(obj);
  }

  _updateState(newState) {
    this._pendingState = newState;
    if (this._updateQueued) return;

    this._updateQueued = true;
    requestAnimationFrame(() => {
      const startTime = performance.now();
      const oldState = this._state;
      const state = this._pendingState;
      
      this._state = this._shallowFreeze(state);
      this._updateQueued = false;
      this._pendingState = null;
      this._lastStateUpdate = Date.now();

      // Detect which top-level keys changed for surgical updates
      const changes = this._detectChanges(oldState, state);
      if (changes.length === 0) return;

      // Global event
      this.dispatchEvent(new CustomEvent("state_update", { 
        detail: { state, changes } 
      }));

      // Notify targeted subscribers
      // Use a Map to deduplicate callbacks if they subscribe to multiple changed keys
      const callbacksToNotify = new Map();
      
      for (const key of changes) {
        const subs = this._subscribers.get(key);
        if (subs) {
          for (const cb of subs) {
            if (!callbacksToNotify.has(cb)) {
              callbacksToNotify.set(cb, key);
            }
          }
        }
      }

      // Handle glob subscribers
      const globSubs = this._subscribers.get("*");
      if (globSubs) {
        for (const cb of globSubs) {
          if (!callbacksToNotify.has(cb)) {
            callbacksToNotify.set(cb, "*");
          }
        }
      }

      // Fire notifications
      for (const [cb, key] of callbacksToNotify) {
        try {
          cb(this._getNestedValue(state, key), key, state);
        } catch (error) {
          console.error(`[StateManager] Subscriber error for ${key}:`, error);
        }
      }

      const duration = performance.now() - startTime;
      if (duration > 32) {
        console.warn(`[StateManager] Slow frame: ${duration.toFixed(1)}ms. UI stutter possible.`);
      }
    });
  }

  _detectChanges(oldState, newState) {
    const changes = [];
    const allKeys = new Set([...Object.keys(oldState || {}), ...Object.keys(newState || {})]);
    
    for (const key of allKeys) {
      if (oldState?.[key] !== newState?.[key]) {
        changes.push(key);
      }
    }

    // Surgical check for "state" envelope (most common)
    if (changes.includes("state")) {
      const oldSub = oldState?.state || {};
      const newSub = newState?.state || {};
      if (typeof oldSub === "object" && typeof newSub === "object" && !Array.isArray(oldSub) && !Array.isArray(newSub)) {
        const subKeys = new Set([...Object.keys(oldSub), ...Object.keys(newSub)]);
        for (const sk of subKeys) {
          if (!changes.includes(sk) && oldSub[sk] !== newSub[sk]) {
            changes.push(sk);
          }
        }
      }
    }
    
    return changes;
  }

  _getNestedValue(obj, path) {
    if (path === "*") return obj;
    let val = path.split(".").reduce((o, k) => o?.[k], obj);
    
    // Fallback to "state" envelope
    if (val === undefined && obj?.state && typeof obj.state === "object") {
      val = path.split(".").reduce((o, k) => o?.[k], obj.state);
    }

    // NORMALIZE VECTORS: If the value looks like a vector object {x,y,z}, convert to array [x,y,z]
    if (val && typeof val === "object" && !Array.isArray(val)) {
      if (val.x !== undefined || val.y !== undefined || val.z !== undefined) {
        return [val.x || 0, val.y || 0, val.z || 0];
      }
    }

    return val;
  }

  subscribe(key, callback) {
    if (!this._subscribers.has(key)) {
      this._subscribers.set(key, new Set());
    }
    this._subscribers.get(key).add(callback);

    // Initial value
    const value = this._getNestedValue(this._state, key);
    if (value !== undefined) {
      try {
        callback(value, key, this._state);
      } catch (e) {}
    }

    return () => {
      this._subscribers.get(key)?.delete(callback);
    };
  }

  getState(key = null) {
    if (key === null) return this._state;
    return this._getNestedValue(this._state, key);
  }

  getShipState() {
    const state = this._state;
    if (state.state) return state.state;
    if (state.ship) return state.ship;
    
    const ships = state.ships;
    if (Array.isArray(ships) && ships.length > 0) {
      if (this._playerShipId) {
        const playerShip = ships.find(s => s.id === this._playerShipId);
        if (playerShip) return playerShip;
      }
      return ships[0];
    } else if (ships && typeof ships === "object") {
      if (this._playerShipId && ships[this._playerShipId]) return ships[this._playerShipId];
      const keys = Object.keys(ships);
      if (keys.length > 0) return ships[keys[0]];
    }
    
    return state; // Final fallback
  }

  getContacts() {
    const ship = this.getShipState();
    if (ship?.systems?.sensors?.contacts) return ship.systems.sensors.contacts;
    if (ship?.systems?.sensors?.active?.contacts) return ship.systems.sensors.active.contacts;
    if (ship?.systems?.sensors?.passive?.contacts) return ship.systems.sensors.passive.contacts;
    return ship?.sensors?.contacts || ship?.contacts || [];
  }

  getSensors() {
    const ship = this.getShipState();
    const sysSensors = ship?.systems?.sensors;
    if (sysSensors && typeof sysSensors === "object") return sysSensors;
    return ship?.sensors || {};
  }

  getTargeting() {
    const ship = this.getShipState();
    return ship?.targeting || ship?.systems?.targeting || ship?.target || null;
  }

  getWeapons() {
    const ship = this.getShipState();
    const sysWeapons = ship?.systems?.weapons;
    if (sysWeapons && typeof sysWeapons === "object") return sysWeapons;
    return ship?.weapons || {};
  }

  getCombat() {
    const ship = this.getShipState();
    const sysCombat = ship?.systems?.combat;
    if (sysCombat && typeof sysCombat === "object") return sysCombat;
    
    const weapons = this.getWeapons();
    if (weapons?.truth_weapons) return weapons;
    
    return ship?.combat || null;
  }

  getNavigation() {
    const ship = this.getShipState();

    // Normalize position/velocity via _getNestedValue (handles {x,y,z} → [x,y,z])
    const position = this._getNestedValue(ship, "position") || [0, 0, 0];
    const velocity = this._getNestedValue(ship, "velocity") || [0, 0, 0];

    // Heading with roll
    const heading = ship?.orientation
      ? { pitch: ship.orientation.pitch || 0, yaw: ship.orientation.yaw || 0, roll: ship.orientation.roll || 0 }
      : ship?.heading || { pitch: 0, yaw: 0 };

    // Thrust: normalize to 0-1
    const propulsion = ship?.systems?.propulsion;
    let thrust = 0;
    if (propulsion?.throttle !== undefined) {
      thrust = propulsion.throttle;
    } else if (ship?.thrust_level !== undefined) {
      thrust = ship.thrust_level;
    } else if (typeof ship?.thrust === "number") {
      thrust = ship.thrust;
    } else if (ship?.thrust && typeof ship.thrust === "object") {
      const tx = ship.thrust.x || 0, ty = ship.thrust.y || 0, tz = ship.thrust.z || 0;
      const mag = Math.sqrt(tx*tx + ty*ty + tz*tz);
      thrust = (propulsion?.max_thrust > 0) ? mag / propulsion.max_thrust : (mag > 1 ? mag / 100 : mag);
    }
    thrust = Math.max(0, Math.min(1, thrust));

    // Autopilot with detail fields
    let autopilot = null;
    if (ship?.systems?.navigation) {
      const nav = ship.systems.navigation;
      const apState = nav.autopilot_state || nav.autopilotState || null;
      autopilot = {
        mode: nav.mode || "manual",
        enabled: nav.autopilot_enabled || false,
        target: nav.target || null,
        phase: nav.phase || (typeof apState === "string" ? apState : apState?.phase) || null,
        range: apState?.distance ?? nav.target_range ?? null,
        distance: apState?.distance ?? null,
        closingSpeed: apState?.closing_speed ?? null,
        eta: apState?.eta ?? null,
      };
    } else if (ship?.autopilot) {
      autopilot = ship.autopilot;
    }

    return { position, velocity, heading, thrust, autopilot };
  }

  getSystems() {
    const ship = this.getShipState();
    return ship?.systems || ship?.power_system?.systems || {};
  }

  getThermal() {
    const ship = this.getShipState();
    return ship?.thermal || ship?.systems?.thermal || null;
  }

  getProjectiles() {
    return this._state?.projectiles || [];
  }

  getTorpedoes() {
    return this._state?.torpedoes || [];
  }

  getPower() {
    const ship = this.getShipState();
    return ship?.systems?.power || ship?.power || ship?.ops || {};
  }

  getStateAge() {
    return Date.now() - this._lastStateUpdate;
  }
}

const stateManager = new StateManager();
export { StateManager, stateManager };
