/**
 * Gamepad/Controller Input System
 *
 * Uses the standard browser Gamepad API for flight control.
 * Works with Xbox, PlayStation, and generic USB/Bluetooth controllers.
 * Also works on Android Chrome with Bluetooth gamepads.
 *
 * Standard mapping (Xbox layout):
 *   Left stick X  -> Yaw (turn left/right)
 *   Left stick Y  -> Pitch (nose up/down)
 *   Right stick X -> Roll
 *   Right stick Y -> Fine throttle adjust
 *   Right trigger -> Throttle (0-100%)
 *   Left trigger  -> Reverse thrust
 *   A / Cross     -> Ping sensors
 *   B / Circle    -> Toggle contact list
 *   X / Square    -> Request docking
 *   Y / Triangle  -> Emergency stop
 *   D-pad Up/Down -> Cycle contacts
 *   Start         -> Toggle autopilot
 *   Back/Select   -> Toggle HUD
 */

import { wsClient } from "./ws-client.js";
import { stateManager } from "./state-manager.js";

const DEADZONE = 0.15;
const POLL_MS = 16; // ~60Hz
const COMMAND_THROTTLE_MS = 100; // Don't send orientation faster than 10Hz
const ROTATION_SCALE = 5; // degrees per poll at full stick deflection
const PITCH_SCALE = 3; // pitch is more sensitive, use smaller scale

class GamepadInput {
  constructor() {
    this._gamepadIndex = null;
    this._pollInterval = null;
    this._connected = false;
    this._lastCommandTime = 0;
    this._currentThrottle = 0;
    this._buttonStates = {}; // Track button press/release for edge detection
    this._onConnect = null;
    this._onDisconnect = null;
  }

  start() {
    this._onConnect = (e) => this._handleConnect(e);
    this._onDisconnect = (e) => this._handleDisconnect(e);
    window.addEventListener("gamepadconnected", this._onConnect);
    window.addEventListener("gamepaddisconnected", this._onDisconnect);

    // Check if already connected (page refresh with controller plugged in)
    const gamepads = navigator.getGamepads?.() || [];
    for (let i = 0; i < gamepads.length; i++) {
      if (gamepads[i]) {
        this._gamepadIndex = i;
        this._connected = true;
        this._startPolling();
        document.dispatchEvent(
          new CustomEvent("gamepad-connected", {
            detail: { name: gamepads[i].id },
          })
        );
        console.log(`Gamepad already connected: ${gamepads[i].id}`);
        break;
      }
    }
  }

  stop() {
    this._stopPolling();
    window.removeEventListener("gamepadconnected", this._onConnect);
    window.removeEventListener("gamepaddisconnected", this._onDisconnect);
    this._connected = false;
    this._onConnect = null;
    this._onDisconnect = null;
  }

  get connected() {
    return this._connected;
  }

  _handleConnect(e) {
    this._gamepadIndex = e.gamepad.index;
    this._connected = true;
    this._startPolling();
    console.log(`Gamepad connected: ${e.gamepad.id}`);
    document.dispatchEvent(
      new CustomEvent("gamepad-connected", {
        detail: { name: e.gamepad.id },
      })
    );
  }

  _handleDisconnect(e) {
    if (e.gamepad.index === this._gamepadIndex) {
      this._connected = false;
      this._stopPolling();
      this._buttonStates = {};
      this._currentThrottle = 0;
      console.log("Gamepad disconnected");
      document.dispatchEvent(new CustomEvent("gamepad-disconnected"));
    }
  }

  _startPolling() {
    if (this._pollInterval) return;
    this._pollInterval = setInterval(() => this._poll(), POLL_MS);
  }

  _stopPolling() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }

  _applyDeadzone(value) {
    if (Math.abs(value) < DEADZONE) return 0;
    // Rescale so output starts at 0 after deadzone
    const sign = value > 0 ? 1 : -1;
    return sign * ((Math.abs(value) - DEADZONE) / (1 - DEADZONE));
  }

  _poll() {
    const gamepads = navigator.getGamepads?.();
    if (!gamepads) return;
    const gp = gamepads[this._gamepadIndex];
    if (!gp) return;

    const now = Date.now();

    // --- AXES: Flight control ---
    const yaw = this._applyDeadzone(gp.axes[0] || 0); // Left stick X
    const pitch = this._applyDeadzone(-(gp.axes[1] || 0)); // Left stick Y (inverted)
    const roll = this._applyDeadzone(gp.axes[2] || 0); // Right stick X

    // Triggers for throttle: RT (button 7) = forward, LT (button 6) = reverse
    const rightTrigger = gp.buttons[7]?.value || 0;
    const leftTrigger = gp.buttons[6]?.value || 0;
    const throttle = Math.max(0, Math.min(1, rightTrigger - leftTrigger));

    // Send orientation if any axis is deflected and enough time has elapsed
    if (
      (yaw !== 0 || pitch !== 0 || roll !== 0) &&
      now - this._lastCommandTime > COMMAND_THROTTLE_MS
    ) {
      // Read current heading from state manager (same pattern as keyboard-flight.js)
      const nav = stateManager.getNavigation();
      const currentHeading = nav?.heading || {};

      const newYaw =
        ((currentHeading.yaw || 0) + yaw * ROTATION_SCALE) % 360;
      const newPitch = Math.max(
        -90,
        Math.min(90, (currentHeading.pitch || 0) + pitch * PITCH_SCALE)
      );
      const newRoll = Math.max(
        -180,
        Math.min(180, (currentHeading.roll || 0) + roll * PITCH_SCALE)
      );

      wsClient
        .sendShipCommand("set_orientation", {
          pitch: newPitch,
          yaw: newYaw < 0 ? newYaw + 360 : newYaw,
          roll: newRoll,
        })
        .catch((err) => {
          console.warn("Gamepad: orientation command failed:", err.message);
        });
      this._lastCommandTime = now;
    }

    // Send throttle if changed significantly (>5% change)
    if (Math.abs(throttle - this._currentThrottle) > 0.05) {
      this._currentThrottle = throttle;
      wsClient.sendShipCommand("set_thrust", { thrust: throttle }).catch((err) => {
        console.warn("Gamepad: throttle command failed:", err.message);
      });
    }

    // --- BUTTONS: Actions (edge-triggered) ---
    // A / Cross (0) -> Ping sensors
    this._checkButton(gp, 0, () => {
      wsClient.sendShipCommand("ping_sensors", {}).catch((err) => {
        console.warn("Gamepad: ping_sensors failed:", err.message);
      });
    });

    // B / Circle (1) -> Toggle contact list (dispatch DOM event for UI)
    this._checkButton(gp, 1, () => {
      document.dispatchEvent(new CustomEvent("gamepad-toggle-contacts"));
    });

    // X / Square (2) -> Request docking
    this._checkButton(gp, 2, () => {
      wsClient.sendShipCommand("request_docking", {}).catch((err) => {
        console.warn("Gamepad: request_docking failed:", err.message);
      });
    });

    // Y / Triangle (3) -> Emergency stop
    this._checkButton(gp, 3, () => {
      wsClient.sendShipCommand("emergency_stop", {}).catch((err) => {
        console.warn("Gamepad: emergency_stop failed:", err.message);
      });
    });

    // D-pad Up (12) -> Cycle contact forward
    this._checkButton(gp, 12, () => {
      this._cycleContact(1);
    });

    // D-pad Down (13) -> Cycle contact backward
    this._checkButton(gp, 13, () => {
      this._cycleContact(-1);
    });

    // Start (9) -> Toggle autopilot
    this._checkButton(gp, 9, () => {
      wsClient
        .sendShipCommand("autopilot", { program: "all_stop", g_level: 1.0 })
        .catch((err) => {
          console.warn("Gamepad: autopilot toggle failed:", err.message);
        });
    });

    // Back/Select (8) -> Toggle HUD (dispatch DOM event for UI)
    this._checkButton(gp, 8, () => {
      document.dispatchEvent(new CustomEvent("gamepad-toggle-hud"));
    });
  }

  /**
   * Edge-triggered button check. Calls callback on rising edge only
   * (button was not pressed last poll, is pressed now).
   */
  _checkButton(gp, index, callback) {
    const pressed = gp.buttons[index]?.pressed || false;
    const wasPressed = this._buttonStates[index] || false;

    if (pressed && !wasPressed) {
      callback();
    }

    this._buttonStates[index] = pressed;
  }

  /**
   * Cycle through sensor contacts by direction (+1 forward, -1 backward).
   * Uses the same stateManager.getContacts() pattern as the keyboard shortcuts
   * in main.js.
   */
  _cycleContact(direction) {
    const contacts = stateManager.getContacts();
    if (!contacts || contacts.length === 0) return;

    const sensorContacts = document.querySelector("sensor-contacts");
    const currentId = sensorContacts?.getSelectedContact?.() || null;

    let nextIndex = 0;
    if (currentId) {
      const currentIndex = contacts.findIndex(
        (c) => (c.contact_id || c.id) === currentId
      );
      nextIndex =
        (currentIndex + direction + contacts.length) % contacts.length;
    }

    const nextId = contacts[nextIndex].contact_id || contacts[nextIndex].id;
    sensorContacts?._selectContact?.(nextId);
  }
}

// Singleton
export const gamepadInput = new GamepadInput();
