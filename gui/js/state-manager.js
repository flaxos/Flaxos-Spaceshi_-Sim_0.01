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
    this._pollInterval = null;
    this._eventPollInterval = null;
    this._lastStateUpdate = 0;
    this._lastEventUpdate = 0;
    this._playerShipId = null;  // Track player's ship ID

    // Configuration
    this.config = {
      statePollMs: 200,      // Poll state every 200ms
      eventPollMs: 500,      // Poll events every 500ms
      autoPoll: true,        // Start polling on connect
    };
  }

  /**
   * Set the player ship ID (called after scenario load or initial state)
   * @param {string} shipId - The player's ship ID
   */
  setPlayerShipId(shipId) {
    this._playerShipId = shipId;
    console.log("Player ship ID set to:", shipId);
    // Re-fetch state immediately with ship ID
    this._fetchState();
  }

  /**
   * Get the current player ship ID
   * @returns {string|null}
   */
  getPlayerShipId() {
    return this._playerShipId;
  }

  /**
   * Initialize the state manager
   */
  init() {
    // Listen for connection changes
    wsClient.addEventListener("status_change", (e) => {
      if (e.detail.status === "connected" && this.config.autoPoll) {
        this.startPolling();
      } else if (e.detail.status === "disconnected") {
        this.stopPolling();
      }
    });

    // Start polling if already connected
    if (wsClient.status === "connected" && this.config.autoPoll) {
      this.startPolling();
    }
  }

  /**
   * Start polling for state and events
   */
  startPolling() {
    this.stopPolling();

    // Poll state
    this._pollInterval = setInterval(() => {
      this._fetchState();
    }, this.config.statePollMs);

    // Poll events
    this._eventPollInterval = setInterval(() => {
      this._fetchEvents();
    }, this.config.eventPollMs);

    // Immediate first fetch
    this._fetchState();
    this._fetchEvents();
  }

  /**
   * Stop polling
   */
  stopPolling() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
    if (this._eventPollInterval) {
      clearInterval(this._eventPollInterval);
      this._eventPollInterval = null;
    }
  }

  /**
   * Fetch current state from server
   */
  async _fetchState() {
    try {
      // Include ship parameter if we have a player ship ID to get detailed state
      const params = {};
      if (this._playerShipId) {
        params.ship = this._playerShipId;
      }
      const response = await wsClient.send("get_state", params);
      if (response && response.ok !== false) {
        // Auto-detect player ship ID from first ship if not set
        if (!this._playerShipId && response.ships && response.ships.length > 0) {
          this._playerShipId = response.ships[0].id;
          console.log("Auto-detected player ship ID:", this._playerShipId);
        }
        this._updateState(response);
      }
    } catch (error) {
      // Ignore polling errors
    }
  }

  /**
   * Fetch events from server
   */
  async _fetchEvents() {
    try {
      const response = await wsClient.send("get_events", {});
      if (response && response.ok !== false && Array.isArray(response.events)) {
        this._processEvents(response.events);
      }
    } catch (error) {
      // Ignore polling errors
    }
  }

  /**
   * Update internal state and notify subscribers
   */
  _updateState(newState) {
    const oldState = this._state;
    this._state = newState;
    this._lastStateUpdate = Date.now();

    // Determine what changed
    const changes = this._detectChanges(oldState, newState);

    // Notify global listeners
    this.dispatchEvent(new CustomEvent("state_update", {
      detail: { state: newState, changes }
    }));

    // Notify specific subscribers
    for (const [key, callbacks] of this._subscribers) {
      if (changes.includes(key) || key === "*") {
        const value = this._getNestedValue(newState, key);
        callbacks.forEach(cb => {
          try {
            cb(value, key, newState);
          } catch (error) {
            console.error(`State subscriber error for ${key}:`, error);
          }
        });
      }
    }
  }

  /**
   * Process incoming events
   */
  _processEvents(events) {
    for (const event of events) {
      this._events.push(event);
      this.dispatchEvent(new CustomEvent("event", { detail: event }));
    }

    // Limit stored events
    while (this._events.length > 1000) {
      this._events.shift();
    }

    this._lastEventUpdate = Date.now();
  }

  /**
   * Detect which top-level keys changed
   */
  _detectChanges(oldState, newState) {
    const changes = [];
    const allKeys = new Set([
      ...Object.keys(oldState || {}),
      ...Object.keys(newState || {})
    ]);

    for (const key of allKeys) {
      if (JSON.stringify(oldState?.[key]) !== JSON.stringify(newState?.[key])) {
        changes.push(key);
      }
    }

    return changes;
  }

  /**
   * Get nested value from state
   */
  _getNestedValue(obj, path) {
    if (path === "*") return obj;
    return path.split(".").reduce((o, k) => o?.[k], obj);
  }

  /**
   * Subscribe to state changes
   * @param {string} key - State key to watch (use "*" for all changes)
   * @param {function} callback - Callback(value, key, fullState)
   * @returns {function} Unsubscribe function
   */
  subscribe(key, callback) {
    if (!this._subscribers.has(key)) {
      this._subscribers.set(key, new Set());
    }
    this._subscribers.get(key).add(callback);

    // Immediately call with current value
    const value = this._getNestedValue(this._state, key);
    if (value !== undefined) {
      try {
        callback(value, key, this._state);
      } catch (error) {
        console.error(`Initial subscriber call error for ${key}:`, error);
      }
    }

    return () => {
      this._subscribers.get(key)?.delete(callback);
    };
  }

  /**
   * Get current state value
   * @param {string} key - Optional key for nested value
   */
  getState(key = null) {
    if (key === null) return this._state;
    return this._getNestedValue(this._state, key);
  }

  /**
   * Get ship state (convenience)
   */
  getShipState() {
    // Handle different state structures
    const state = this._state;
    
    // If we have a detailed state response with "state" key (from get_state with ship param)
    if (state.state) return state.state;
    
    // If we have a "ship" key
    if (state.ship) return state.ship;
    
    // If we have a ships array, find player ship or use first
    if (state.ships && Array.isArray(state.ships) && state.ships.length > 0) {
      if (this._playerShipId) {
        const playerShip = state.ships.find(s => s.id === this._playerShipId);
        if (playerShip) return playerShip;
      }
      return state.ships[0];
    }
    
    return state;
  }

  /**
   * Get contacts (convenience)
   */
  getContacts() {
    const ship = this.getShipState();
    
    // Try systems.sensors.contacts first (standard location)
    if (ship?.systems?.sensors?.contacts) {
      return ship.systems.sensors.contacts;
    }
    
    // Try active/passive sensor contacts
    if (ship?.systems?.sensors?.active?.contacts) {
      return ship.systems.sensors.active.contacts;
    }
    if (ship?.systems?.sensors?.passive?.contacts) {
      return ship.systems.sensors.passive.contacts;
    }
    
    // Fallback to older formats
    return ship?.sensors?.contacts || ship?.contacts || [];
  }

  /**
   * Get sensor system state (convenience)
   */
  getSensors() {
    const ship = this.getShipState();
    return ship?.systems?.sensors || ship?.sensors || {};
  }

  /**
   * Get targeting info (convenience)
   */
  getTargeting() {
    const ship = this.getShipState();
    return ship?.systems?.targeting || ship?.targeting || ship?.target || null;
  }

  /**
   * Get weapons info (convenience)
   */
  getWeapons() {
    const ship = this.getShipState();
    return ship?.systems?.weapons || ship?.weapons || {};
  }

  /**
   * Get navigation info (convenience)
   */
  getNavigation() {
    const ship = this.getShipState();

    // Handle position - could be object {x,y,z} or array
    let position = [0, 0, 0];
    if (ship?.position) {
      if (Array.isArray(ship.position)) {
        position = ship.position;
      } else if (typeof ship.position === "object") {
        position = [ship.position.x || 0, ship.position.y || 0, ship.position.z || 0];
      }
    }

    // Handle velocity - could be object {x,y,z} or array
    let velocity = [0, 0, 0];
    if (ship?.velocity) {
      if (Array.isArray(ship.velocity)) {
        velocity = ship.velocity;
      } else if (typeof ship.velocity === "object") {
        velocity = [ship.velocity.x || 0, ship.velocity.y || 0, ship.velocity.z || 0];
      }
    }

    // Handle heading/orientation
    let heading = { pitch: 0, yaw: 0 };
    if (ship?.orientation) {
      heading = {
        pitch: ship.orientation.pitch || 0,
        yaw: ship.orientation.yaw || 0,
        roll: ship.orientation.roll || 0
      };
    } else if (ship?.heading) {
      heading = ship.heading;
    }

    // Handle thrust - prioritize propulsion system throttle (0-1 scalar)
    let thrust = 0;
    const propulsion = ship?.systems?.propulsion;
    
    // First, try to get throttle directly from propulsion system (most accurate)
    if (propulsion?.throttle !== undefined) {
      thrust = propulsion.throttle;
    } else if (ship?.thrust_level !== undefined) {
      thrust = ship.thrust_level;
    } else if (ship?.thrust !== undefined) {
      if (typeof ship.thrust === "number") {
        thrust = ship.thrust;
      } else if (typeof ship.thrust === "object") {
        // Calculate thrust magnitude from vector as fallback
        const tx = ship.thrust.x || 0;
        const ty = ship.thrust.y || 0;
        const tz = ship.thrust.z || 0;
        const magnitude = Math.sqrt(tx*tx + ty*ty + tz*tz);
        // Normalize to 0-1 range if we have max_thrust from propulsion system
        if (propulsion?.max_thrust && propulsion.max_thrust > 0) {
          thrust = magnitude / propulsion.max_thrust;
        } else if (magnitude > 1) {
          thrust = magnitude / 100; // Assume percentage if over 1
        } else {
          thrust = magnitude;
        }
      }
    }
    
    // Clamp to valid range
    thrust = Math.max(0, Math.min(1, thrust));

    // Get autopilot from navigation system
    let autopilot = null;
    if (ship?.systems?.navigation) {
      const nav = ship.systems.navigation;
      autopilot = {
        mode: nav.mode || "manual",
        enabled: nav.autopilot_enabled || false,
        target: nav.target || null,
        phase: nav.phase || null,
        range: nav.target_range || null,
      };
    } else if (ship?.autopilot) {
      autopilot = ship.autopilot;
    }

    return { position, velocity, heading, thrust, autopilot };
  }

  /**
   * Get systems info (convenience)
   */
  getSystems() {
    const ship = this.getShipState();
    return ship?.systems || ship?.power_system?.systems || {};
  }

  /**
   * Get power info (convenience)
   */
  getPower() {
    const ship = this.getShipState();
    return ship?.power || ship?.power_system || {};
  }

  /**
   * Time since last state update
   */
  getStateAge() {
    return Date.now() - this._lastStateUpdate;
  }

  /**
   * Check if state is fresh (< 1 second old)
   */
  isStateFresh() {
    return this.getStateAge() < 1000;
  }
}

// Export singleton
const stateManager = new StateManager();
export { StateManager, stateManager };
