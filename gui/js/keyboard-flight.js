/**
 * Keyboard Flight Controls — WASD/QE + Shift/Ctrl desktop flight for MANUAL tier.
 *
 * Keybindings:
 *   W/S   = pitch up/down (+/-5 deg relative)
 *   A/D   = yaw left/right (-/+5 deg relative)
 *   Q/E   = roll left/right (-/+5 deg relative)
 *   Shift = throttle up (+10% per 200ms while held)
 *   Ctrl  = throttle down (-10% per 200ms while held)
 *   Space = fire selected weapon
 *   Tab   = cycle target
 *   X     = all stop
 *   T     = lock/unlock toggle
 *
 * Only active when window.controlTier === "manual" and focus is not on an input.
 * Imports wsClient and stateManager from existing modules.
 */

import { wsClient } from "./ws-client.js";
import { stateManager } from "./state-manager.js";

const ROTATION_DELTA = 5;        // degrees per keypress
const THROTTLE_DELTA = 0.1;      // 10% per tick
const THROTTLE_INTERVAL = 200;   // ms between throttle ticks while held

// Track held keys and intervals
let _active = false;
let _throttleUpInterval = null;
let _throttleDownInterval = null;
let _hintShown = false;
let _hintElement = null;
let _boundKeyDown = null;
let _boundKeyUp = null;
let _boundTierChange = null;

/** Check if the active element is an input that should capture keyboard events. */
function _isInputFocused() {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName?.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  const inner = el.shadowRoot?.activeElement;
  const innerTag = inner?.tagName?.toLowerCase();
  return innerTag === "input" || innerTag === "textarea" || innerTag === "select";
}

/** Get current ship orientation from state manager. */
function _getOrientation() {
  const nav = stateManager.getNavigation();
  const h = nav?.heading || {};
  return {
    pitch: h.pitch || 0,
    yaw: h.yaw || 0,
    roll: h.roll || 0,
  };
}

/** Get current throttle from state manager. */
function _getThrottle() {
  const ship = stateManager.getShipState();
  const prop = ship?.systems?.propulsion || {};
  const nav = stateManager.getNavigation();
  return prop.throttle ?? nav?.thrust ?? 0;
}

/** Send a relative orientation change. */
function _rotateBy(dPitch, dYaw, dRoll) {
  const cur = _getOrientation();
  const pitch = Math.max(-90, Math.min(90, cur.pitch + dPitch));
  const yaw = ((cur.yaw + dYaw) % 360 + 360) % 360;
  const roll = Math.max(-180, Math.min(180, cur.roll + dRoll));
  wsClient.sendShipCommand("set_orientation", { pitch, yaw, roll }).catch((err) => {
    console.warn("Keyboard flight: orientation command failed:", err.message);
  });
}

/** Send an absolute throttle value. */
function _setThrottle(value) {
  const clamped = Math.max(0, Math.min(1, value));
  wsClient.sendShipCommand("set_thrust", { thrust: clamped }).catch((err) => {
    console.warn("Keyboard flight: throttle command failed:", err.message);
  });
}

/** Increment throttle by THROTTLE_DELTA. */
function _throttleUp() {
  const cur = _getThrottle();
  _setThrottle(cur + THROTTLE_DELTA);
}

/** Decrement throttle by THROTTLE_DELTA. */
function _throttleDown() {
  const cur = _getThrottle();
  _setThrottle(cur - THROTTLE_DELTA);
}

/** Show a key hints overlay on first MANUAL tier activation. */
function _showHints() {
  if (_hintShown) return;
  _hintShown = true;

  const el = document.createElement("div");
  el.id = "keyboard-flight-hints";
  el.innerHTML = `
    <style>
      #keyboard-flight-hints {
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9000;
        background: rgba(10, 10, 15, 0.92);
        border: 1px solid #ff8800;
        border-radius: 4px;
        padding: 12px 20px;
        font-family: var(--font-mono, 'JetBrains Mono', monospace);
        font-size: 0.75rem;
        color: #ff8800;
        text-align: center;
        pointer-events: none;
        animation: kfhFadeIn 0.3s ease;
        box-shadow: 0 0 20px rgba(255, 136, 0, 0.15);
      }
      @keyframes kfhFadeIn {
        from { opacity: 0; transform: translateX(-50%) translateY(10px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
      }
      .kfh-row { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
      .kfh-key { color: #fff; font-weight: 600; }
      .kfh-dim { color: #aa7700; }
    </style>
    <div class="kfh-row">
      <span><span class="kfh-key">W/S</span> <span class="kfh-dim">Pitch</span></span>
      <span><span class="kfh-key">A/D</span> <span class="kfh-dim">Yaw</span></span>
      <span><span class="kfh-key">Q/E</span> <span class="kfh-dim">Roll</span></span>
      <span><span class="kfh-key">Shift/Ctrl</span> <span class="kfh-dim">Throttle</span></span>
      <span><span class="kfh-key">Space</span> <span class="kfh-dim">Fire</span></span>
      <span><span class="kfh-key">Tab</span> <span class="kfh-dim">Cycle Target</span></span>
    </div>
    <div style="margin-top:6px; font-size:0.6rem; color:#886600;">Press any key to dismiss</div>
  `;
  document.body.appendChild(el);
  _hintElement = el;
}

/** Dismiss the hints overlay. */
function _dismissHints() {
  if (_hintElement) {
    _hintElement.remove();
    _hintElement = null;
  }
}

/** Handle keydown events for flight controls. */
function _onKeyDown(event) {
  if (!_active) return;
  if (_isInputFocused()) return;

  // Dismiss hints on any keypress
  _dismissHints();

  const key = event.key;

  switch (key) {
    case "w": case "W":
      event.preventDefault();
      _rotateBy(ROTATION_DELTA, 0, 0);
      break;
    case "s": case "S":
      event.preventDefault();
      _rotateBy(-ROTATION_DELTA, 0, 0);
      break;
    case "a": case "A":
      event.preventDefault();
      _rotateBy(0, -ROTATION_DELTA, 0);
      break;
    case "d": case "D":
      event.preventDefault();
      _rotateBy(0, ROTATION_DELTA, 0);
      break;
    case "q": case "Q":
      event.preventDefault();
      _rotateBy(0, 0, -ROTATION_DELTA);
      break;
    case "e": case "E":
      event.preventDefault();
      _rotateBy(0, 0, ROTATION_DELTA);
      break;
    case "Shift":
      event.preventDefault();
      if (!_throttleUpInterval) {
        _throttleUp(); // immediate first tick
        _throttleUpInterval = setInterval(_throttleUp, THROTTLE_INTERVAL);
      }
      break;
    case "Control":
      event.preventDefault();
      if (!_throttleDownInterval) {
        _throttleDown(); // immediate first tick
        _throttleDownInterval = setInterval(_throttleDown, THROTTLE_INTERVAL);
      }
      break;
    case " ": // Space — fire
      event.preventDefault();
      wsClient.sendShipCommand("fire", {}).catch((err) => {
        console.warn("Keyboard flight: fire failed:", err.message);
      });
      break;
    // Tab and X and T are handled by main.js global shortcuts already,
    // but we stop propagation prevention so they still work.
    default:
      // Let other keys pass through to main.js handler
      return;
  }
}

/** Handle keyup events — clear throttle intervals. */
function _onKeyUp(event) {
  if (!_active) return;

  if (event.key === "Shift" && _throttleUpInterval) {
    clearInterval(_throttleUpInterval);
    _throttleUpInterval = null;
  }
  if (event.key === "Control" && _throttleDownInterval) {
    clearInterval(_throttleDownInterval);
    _throttleDownInterval = null;
  }
}

/** Activate keyboard flight controls. */
function _activate() {
  if (_active) return;
  _active = true;
  _showHints();
  console.log("Keyboard flight controls: ACTIVE");
}

/** Deactivate keyboard flight controls. */
function _deactivate() {
  if (!_active) return;
  _active = false;
  _dismissHints();
  // Clear any held throttle intervals
  if (_throttleUpInterval) { clearInterval(_throttleUpInterval); _throttleUpInterval = null; }
  if (_throttleDownInterval) { clearInterval(_throttleDownInterval); _throttleDownInterval = null; }
  console.log("Keyboard flight controls: INACTIVE");
}

/** Handle tier changes — activate on "manual", deactivate on others. */
function _onTierChange(event) {
  const tier = event.detail?.tier;
  if (tier === "manual") {
    _activate();
  } else {
    _deactivate();
  }
}

/** Initialize keyboard flight controls. Call once during app init. */
function init() {
  _boundKeyDown = _onKeyDown;
  _boundKeyUp = _onKeyUp;
  _boundTierChange = _onTierChange;

  document.addEventListener("keydown", _boundKeyDown);
  document.addEventListener("keyup", _boundKeyUp);
  document.addEventListener("tier-change", _boundTierChange);

  // If already on manual tier at init time, activate immediately
  if (window.controlTier === "manual") {
    _activate();
  }
}

/** Tear down keyboard flight controls. */
function destroy() {
  _deactivate();
  if (_boundKeyDown) { document.removeEventListener("keydown", _boundKeyDown); _boundKeyDown = null; }
  if (_boundKeyUp) { document.removeEventListener("keyup", _boundKeyUp); _boundKeyUp = null; }
  if (_boundTierChange) { document.removeEventListener("tier-change", _boundTierChange); _boundTierChange = null; }
}

export { init, destroy };
