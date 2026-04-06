/**
 * Flaxos Spaceship Sim - GUI Main Entry Point
 * Phase 1: Foundation & Transport Layer
 */

import { wsClient } from "./ws-client.js";
import { stateManager } from "./state-manager.js";
// Phase 1: Foundation
import "../components/connection-status.js";
import "../components/panel.js";
// Phase 2: Text Interface
import "../components/event-log.js";
import "../components/command-prompt.js";
import "../components/system-message.js";
// Phase 3: Status Displays
import "../components/ship-status.js";
import "../components/sensor-contacts.js";
import "../components/targeting-display.js";
import "../components/weapons-status.js";
import "../components/firing-solution-display.js";
// Phase 4: Visual Controls
import "../components/rcs-controls.js";
import "../components/weapon-controls.js";
import "../components/system-toggles.js";
import "../components/power-management.js";
import "../components/quick-actions.js";
import "../components/tactical-map.js";
// Phase 5: Integration
import "../components/scenario-loader.js";
import "../components/mission-objectives.js";
// Phase 7: Enhanced Navigation & Multi-Crew
import "../components/maneuver-planner.js";
import { helmRequests } from "./helm-requests.js";
// Sprint B: Navigation loop - autopilot
import "../components/autopilot-status.js";
// View-based layout
import "../components/view-tabs.js";
import "../components/status-bar.js";
import "../components/flight-computer-panel.js";
// Phase 9: Station & Control Tier System
import "../components/station-selector.js";
import "../components/tier-selector.js";
// Phase 10: Helm Completion
import "../components/helm-queue-panel.js";
import "../components/docking-panel.js";
// GUI Refactor: Merged panels
import "../components/flight-data-panel.js";
import "../components/manual-flight-panel.js";
import "../components/helm-workflow-strip.js";
// Phase 11: Tactical Completion
import "../components/subsystem-selector.js";
import "../components/threat-board.js";
import "../components/combat-log.js";
// Phase 12: Engineering & Power
import "../components/power-profile-selector.js";
import "../components/power-draw-display.js";
import "../components/crew-panel.js";
import "../components/crew-roster-panel.js";
import "../components/subsystem-status.js";
// Thermal Management
import "../components/thermal-display.js";
// Phase 13: Fleet Commander Console
import "../components/fleet-roster.js";
import "../components/formation-control.js";
import "../components/fleet-orders.js";
import "../components/fleet-fire-control.js";
import "../components/shared-contacts.js";
import "../components/fleet-tactical-display.js";
// Ops Station Controls
import "../components/ops-control-panel.js";
// Drone Bay Control
import "../components/drone-control-panel.js";
// ECM Electronic Warfare
import "../components/ecm-control-panel.js";
// ECCM Counter-Jamming
import "../components/eccm-control-panel.js";
// ARCADE tier ECM frequency-matching mini-game
import "../components/ecm-frequency-game.js";
// ARCADE tier sensor sweep radar game
import "../components/sensor-sweep-game.js";
// Torpedo System
import "../components/torpedo-status.js";
// Engineering Station Controls
import "../components/engineering-control-panel.js";
// Comms Station Controls
import "../components/comms-control-panel.js";
// Crew Fatigue System
import "../components/crew-fatigue-display.js";
// Science Station Analysis
import "../components/science-analysis-panel.js";
// MANUAL tier raw sensor diagnostics
import "../components/sensor-analysis-manual.js";
// Tutorial System
import "../components/tutorial-overlay.js";
// Inter-station messaging
import "../components/station-chat.js";
// Mission comms choices (branching dialogue)
import "../components/comms-choice-panel.js";
// Campaign hub (persistent campaign state between missions)
import "../components/campaign-hub.js";
// Scenario editor (EDITOR view)
import "../components/scenario-editor.js";
// Boarding Actions (Phase 3B)
import "../components/boarding-panel.js";
// Multi-target tracking
import "../components/multi-track-panel.js";
// ARCADE tier lock minigame
import "../components/targeting-lock-game.js";
// ARCADE tier railgun charge timing game
import "../components/weapons-charge-game.js";
// ARCADE tier flight stability balance game
import "../components/helm-balance-game.js";
// ARCADE tier damage control pipe puzzle
import "../components/damage-control-game.js";
// ARCADE tier reactor balance game
import "../components/reactor-balance-game.js";
// ARCADE tier radiator deploy game
import "../components/radiator-deploy-game.js";
// ARCADE tier PDC threat triage radial game
import "../components/pdc-threat-game.js";
// ARCADE tier munition configuration loadout panel
import "../components/munition-config-game.js";
// Target damage assessment
import "../components/target-assessment.js";
// Damage visualization
import { damageStateManager } from "./damage-state-manager.js";
// Ship Class Editor
import "../components/ship-editor.js";
// RCS Thruster Visualization (MANUAL/RAW tier)
import "../components/rcs-thruster-display.js";
// Keyboard flight controls (MANUAL tier)
import * as keyboardFlight from "./keyboard-flight.js";
// Phase 6: Mobile optimization
import { mobileManager } from "./mobile-manager.js";
import "../components/touch-throttle.js";
import "../components/touch-joystick.js";

// App state
const app = {
  initialized: false,
  currentScenarioId: null,
  // Game state machine: "lobby" | "playing" | "ended"
  gameState: "lobby",
  // next_scenario from mission YAML (for mission progression)
  nextScenarioId: null,
  config: {
    wsUrl: null, // Auto-detect
    autoConnect: true,
    debugMode: false
  }
};

/**
 * Transition the app game state and update the body class accordingly.
 * Valid states: "lobby", "playing", "ended".
 * @param {string} newState
 */
function setGameState(newState) {
  const validStates = ["lobby", "playing", "ended"];
  if (!validStates.includes(newState)) return;
  const oldState = app.gameState;
  if (oldState === newState) return;

  app.gameState = newState;
  document.body.classList.remove("state-lobby", "state-playing", "state-ended");
  document.body.classList.add(`state-${newState}`);
  console.log(`Game state: ${oldState} -> ${newState}`);
}

/**
 * Initialize the application
 */
async function init() {
  if (app.initialized) return;

  console.log("Flaxos Spaceship Sim GUI - Initializing...");

  // Parse URL parameters for config
  const params = new URLSearchParams(window.location.search);
  if (params.has("ws")) {
    app.config.wsUrl = params.get("ws");
  }
  if (params.has("debug")) {
    app.config.debugMode = true;
  }
  if (params.has("noauto")) {
    app.config.autoConnect = false;
  }

  // Configure WebSocket client
  if (app.config.wsUrl) {
    wsClient.url = app.config.wsUrl;
  }

  // Set up global event listeners
  setupGlobalEvents();

  // Initialize state manager
  stateManager.init();

  // Initialize damage visualization (reacts to subsystem_health in telemetry)
  damageStateManager.init();

  // Initialize mobile layout detection and touch controls
  mobileManager.init();

  // Initialize keyboard flight controls (activates in MANUAL tier)
  keyboardFlight.init();

  // Debug mode logging
  if (app.config.debugMode) {
    enableDebugLogging();
  }

  // Auto-connect if enabled
  if (app.config.autoConnect) {
    try {
      await wsClient.connect();
      console.log("Connected to WebSocket bridge");
    } catch (error) {
      console.warn("Auto-connect failed, manual connection required:", error.message);
    }
  }

  app.initialized = true;
  console.log("GUI initialized");

  // Set initial game state to lobby (dims game panels until scenario loads)
  setGameState("lobby");

  // Dispatch ready event
  window.dispatchEvent(new CustomEvent("app:ready", { detail: app }));
}

/**
 * Set up global event listeners
 */
function setupGlobalEvents() {
  // Connection status changes
  wsClient.addEventListener("status_change", (e) => {
    const { status, oldStatus } = e.detail;
    console.log(`Connection: ${oldStatus} → ${status}`);

    // Update body class for global styling
    document.body.classList.remove("ws-connected", "ws-connecting", "ws-disconnected");
    document.body.classList.add(`ws-${status}`);
  });

  // TCP connection status
  wsClient.addEventListener("connection_status", (e) => {
    const { tcp_connected, tcp_host, tcp_port } = e.detail;
    console.log(`TCP: ${tcp_connected ? "connected" : "disconnected"} (${tcp_host}:${tcp_port})`);

    document.body.classList.toggle("tcp-connected", tcp_connected);
    document.body.classList.toggle("tcp-disconnected", !tcp_connected);
  });

  // Server errors
  wsClient.addEventListener("server_error", (e) => {
    console.error("Server error:", e.detail);
    showSystemMessage("error", e.detail.error || "Server error");
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", handleKeyboardShortcut);

  // Tutorial highlight: glow the panel containing the highlighted component
  document.addEventListener("tutorial-highlight", (e) => {
    // Remove any existing highlight
    document.querySelectorAll("flaxos-panel.tutorial-highlight").forEach(
      p => p.classList.remove("tutorial-highlight")
    );
    const selector = e.detail?.selector;
    if (selector) {
      const el = document.querySelector(selector);
      const panel = el?.closest("flaxos-panel");
      if (panel) panel.classList.add("tutorial-highlight");
    }
  });

  document.addEventListener("scenario-loaded", (e) => {
    const { playerShipId, scenario, shipsLoaded, autoAssigned, assignedShip, station, mission } = e.detail;
    const targetShipId = assignedShip || playerShipId;

    // Track scenario ID for mission retry
    if (scenario) {
      app.currentScenarioId = scenario;
    }

    // Track next_scenario from mission data for mission progression
    app.nextScenarioId = (mission && mission.next_scenario) || null;

    // Transition to playing state -- game panels become active
    setGameState("playing");

    if (targetShipId) {
      stateManager.setPlayerShipId(targetShipId);
      if (scenario) {
        console.log(`Scenario "${scenario}" loaded with ${shipsLoaded} ships, player: ${targetShipId}`);
      } else {
        console.log(`Joined active Fleet: Assigned to ship ${targetShipId} as ${station || "crew"}`);
      }
      if (autoAssigned) {
        console.log(`Auto-assigned to ship ${targetShipId} as ${station || "captain"}`);
      }
    } else {
      console.warn(`Scenario loaded or joined but no player ship ID received`);
    }

    if (scenario) {
      showSystemMessage("success", `Scenario "${scenario}" loaded`, "Mission Ready");
    } else {
      showSystemMessage("success", `Station ${station} claimed on ${targetShipId}`, "Station Joined");
    }
  });

  // Mission event notifications
  stateManager.addEventListener("event", (e) => {
    const event = e.detail || {};
    const eventType = event.type || "";
    if (!eventType.toLowerCase().includes("mission")) {
      return;
    }

    const payload = event.data || {};
    const mission = payload.mission || {};
    const status = payload.mission_status || mission.mission_status || mission.status;
    const title = payload.name || mission.name || "Mission Update";
    const message = payload.message || (status ? `Mission status: ${status}` : "Mission event received.");
    const severity = status === "success" ? "success" : status === "failure" ? "error" : "info";

    showSystemMessage(severity, message, title);

    // Show full-screen overlay on mission completion
    if (eventType === "mission_complete" && (status === "success" || status === "failure")) {
      setGameState("ended");

      // Fetch latest mission status to get next_scenario (event payload may not include it)
      wsClient.send("get_mission", {}).then((resp) => {
        if (resp?.ok && resp.mission?.next_scenario) {
          app.nextScenarioId = resp.mission.next_scenario;
        }
        showMissionCompleteOverlay(status, message, title);
      }).catch(() => {
        // Fall back to overlay without next mission data
        showMissionCompleteOverlay(status, message, title);
      });
    }
  });
}

/**
 * Enable debug logging for all WebSocket events
 */
function enableDebugLogging() {
  console.log("Debug mode enabled");

  wsClient.addEventListener("response", (e) => {
    console.log("Response:", e.detail);
  });

  wsClient.addEventListener("event", (e) => {
    console.log("Event:", e.detail);
  });

  wsClient.addEventListener("message", (e) => {
    console.log("Message:", e.detail);
  });

  wsClient.addEventListener("latency", (e) => {
    console.log(`Latency: ${e.detail.latency}ms`);
  });
}

/**
 * Handle keyboard shortcuts
 */
function handleKeyboardShortcut(event) {
  // Don't capture when typing in inputs
  const tag = event.target.tagName?.toLowerCase();
  const isInput = tag === "input" || tag === "textarea" || tag === "select";
  const isComposedInput = event.composedPath().some(el => {
    const t = el.tagName?.toLowerCase();
    return t === "input" || t === "textarea" || t === "select";
  });

  // Escape - always handle: close modals, clear focus
  if (event.key === "Escape") {
    dismissMissionOverlay();
    document.activeElement?.blur();
  }

  // Ctrl+Shift+D - toggle debug
  if (event.ctrlKey && event.shiftKey && event.key === "D") {
    event.preventDefault();
    app.config.debugMode = !app.config.debugMode;
    if (app.config.debugMode) {
      enableDebugLogging();
    }
    console.log(`Debug mode: ${app.config.debugMode ? "ON" : "OFF"}`);
  }

  // Skip remaining shortcuts if in an input field
  if (isInput || isComposedInput) return;

  // T - Select/cycle targets
  if (event.key === "T" || event.key === "t") {
    event.preventDefault();
    const sensorContacts = document.querySelector("sensor-contacts");
    if (sensorContacts) {
      const contacts = stateManager.getContacts();
      if (contacts && contacts.length > 0) {
        const currentId = sensorContacts.getSelectedContact?.() || null;
        let nextIndex = 0;
        if (currentId) {
          const currentIndex = contacts.findIndex(c => (c.contact_id || c.id) === currentId);
          nextIndex = (currentIndex + 1) % contacts.length;
        }
        const nextId = contacts[nextIndex].contact_id || contacts[nextIndex].id;
        sensorContacts._selectContact?.(nextId);
      }
    }
  }

  // F - Fire selected weapon
  if (event.key === "F" || event.key === "f") {
    event.preventDefault();
    wsClient.sendShipCommand("fire", {}).catch(err => {
      console.warn("Fire command failed:", err.message);
    });
  }

  // X - All Stop (emergency velocity kill)
  if (event.key === "X" || event.key === "x") {
    event.preventDefault();
    wsClient.sendShipCommand("autopilot", { program: "all_stop", g_level: 1.0 }).then(r => {
      if (r?.ok) showSystemMessage("success", "All stop engaged");
      else showSystemMessage("error", r?.error || "All stop failed");
    }).catch(err => {
      console.warn("All stop failed:", err.message);
    });
  }
}

/**
 * Show a system message (toast notification)
 * @param {string} type - Message type: info, success, warning, error, critical
 * @param {string} message - Message text
 * @param {string} title - Optional title
 */
function showSystemMessage(type, message, title = "") {
  const container = document.getElementById("system-messages");
  if (!container) return null;
  return container.show({ type, text: message, title });
}

/**
 * Show full-screen mission completion overlay.
 * @param {string} status - "success" or "failure"
 * @param {string} message - Result message from mission YAML
 * @param {string} missionName - Mission name for the header
 */
function showMissionCompleteOverlay(status, message, missionName) {
  // Remove existing overlay if present (prevent duplicates)
  dismissMissionOverlay();

  const isSuccess = status === "success";
  const overlay = document.createElement("div");
  overlay.id = "mission-complete-overlay";

  const accent = isSuccess ? "#00ff88" : "#ff4444";
  const accentDim = isSuccess ? "rgba(0, 255, 136, 0.08)" : "rgba(255, 68, 68, 0.08)";
  const accentGlow = isSuccess ? "rgba(0, 255, 136, 0.15)" : "rgba(255, 68, 68, 0.15)";
  const heading = isSuccess ? "MISSION COMPLETE" : "MISSION FAILED";
  const icon = isSuccess ? "\u2713" : "\u2717";

  // Build the button row: RETRY + optional NEXT MISSION + LOBBY
  const hasNext = isSuccess && app.nextScenarioId;
  const nextBtnHtml = hasNext
    ? `<button class="mco-btn mco-next" style="background: ${accent}; border-color: ${accent}; color: #000;">NEXT MISSION</button>`
    : "";

  overlay.innerHTML = `
    <div class="mco-backdrop"></div>
    <div class="mco-card">
      <div class="mco-icon" style="color: ${accent}; text-shadow: 0 0 30px ${accentGlow};">${icon}</div>
      <h1 class="mco-heading" style="color: ${accent};">${heading}</h1>
      <p class="mco-mission-name">${missionName || ""}</p>
      <div class="mco-message">${message || ""}</div>
      <div class="mco-buttons">
        <button class="mco-btn mco-retry" style="border-color: ${accent}; color: ${accent};">RETRY</button>
        ${nextBtnHtml}
        <button class="mco-btn mco-lobby">RETURN TO LOBBY</button>
      </div>
      <p class="mco-hint">Press ESC to dismiss</p>
    </div>
  `;

  // Inject scoped styles
  const style = document.createElement("style");
  style.textContent = `
    #mission-complete-overlay {
      position: fixed;
      inset: 0;
      z-index: 10000;
      display: flex;
      align-items: center;
      justify-content: center;
      animation: mcoFadeIn 0.3s ease;
    }
    @keyframes mcoFadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    .mco-backdrop {
      position: absolute;
      inset: 0;
      background: rgba(0, 0, 0, 0.85);
    }
    .mco-card {
      position: relative;
      text-align: center;
      padding: 48px 56px;
      max-width: 520px;
      width: 90vw;
      background: ${accentDim};
      border: 1px solid ${accent};
      border-radius: 12px;
      box-shadow: 0 0 60px ${accentGlow}, inset 0 0 40px ${accentGlow};
    }
    .mco-icon {
      font-size: 4rem;
      font-weight: 700;
      margin-bottom: 8px;
    }
    .mco-heading {
      font-family: var(--font-mono, "JetBrains Mono", monospace);
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: 0.15em;
      margin: 0 0 8px;
    }
    .mco-mission-name {
      font-size: 0.85rem;
      color: var(--text-secondary, #888899);
      margin: 0 0 20px;
    }
    .mco-message {
      font-size: 0.9rem;
      color: var(--text-primary, #e0e0e0);
      line-height: 1.6;
      white-space: pre-line;
      margin-bottom: 32px;
    }
    .mco-buttons {
      display: flex;
      gap: 12px;
      justify-content: center;
    }
    .mco-btn {
      padding: 12px 28px;
      font-family: var(--font-mono, "JetBrains Mono", monospace);
      font-size: 0.85rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s ease;
      min-width: 160px;
    }
    .mco-retry {
      background: transparent;
      border: 1px solid;
    }
    .mco-retry:hover {
      background: ${accentGlow};
    }
    .mco-lobby {
      background: var(--bg-input, #1a1a24);
      border: 1px solid var(--border-default, #2a2a3a);
      color: var(--text-primary, #e0e0e0);
    }
    .mco-lobby:hover {
      background: var(--bg-hover, #22222e);
      border-color: var(--border-active, #3a3a4a);
    }
    .mco-next {
      font-weight: 700;
    }
    .mco-next:hover {
      filter: brightness(1.15);
    }
    .mco-hint {
      font-size: 0.7rem;
      color: var(--text-dim, #555566);
      margin: 20px 0 0;
    }
  `;
  overlay.prepend(style);

  // Wire buttons
  overlay.querySelector(".mco-retry").addEventListener("click", () => {
    retryCurrentMission();
  });
  const nextBtn = overlay.querySelector(".mco-next");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      loadNextMission();
    });
  }
  overlay.querySelector(".mco-lobby").addEventListener("click", () => {
    returnToLobby();
  });

  // Click backdrop to dismiss
  overlay.querySelector(".mco-backdrop").addEventListener("click", () => {
    dismissMissionOverlay();
  });

  document.body.appendChild(overlay);
}

/**
 * Dismiss the mission completion overlay if visible.
 */
function dismissMissionOverlay() {
  const overlay = document.getElementById("mission-complete-overlay");
  if (overlay) {
    overlay.remove();
  }
}

/**
 * Retry the current mission by reloading the same scenario.
 */
function retryCurrentMission() {
  const scenarioId = app.currentScenarioId;
  if (!scenarioId) {
    showSystemMessage("warning", "No scenario to retry", "Retry");
    dismissMissionOverlay();
    return;
  }

  dismissMissionOverlay();
  showSystemMessage("info", `Reloading ${scenarioId}...`, "Retry");
  wsClient.send("load_scenario", { scenario: scenarioId }).then((resp) => {
    if (resp && resp.ok !== false) {
      document.dispatchEvent(new CustomEvent("scenario-loaded", {
        detail: resp,
        bubbles: true,
      }));
    } else {
      showSystemMessage("error", resp?.error || "Failed to reload scenario", "Retry");
    }
  }).catch((err) => {
    showSystemMessage("error", `Retry failed: ${err.message}`, "Retry");
  });
}

/**
 * Load the next mission in the campaign chain (if available).
 */
function loadNextMission() {
  const nextId = app.nextScenarioId;
  if (!nextId) {
    showSystemMessage("warning", "No next mission available", "Next Mission");
    dismissMissionOverlay();
    return;
  }

  dismissMissionOverlay();
  showSystemMessage("info", `Loading next mission: ${nextId}...`, "Next Mission");
  wsClient.send("load_scenario", { scenario: nextId }).then((resp) => {
    if (resp && resp.ok !== false) {
      document.dispatchEvent(new CustomEvent("scenario-loaded", {
        detail: resp,
        bubbles: true,
      }));
    } else {
      showSystemMessage("error", resp?.error || "Failed to load next mission", "Next Mission");
    }
  }).catch((err) => {
    showSystemMessage("error", `Next mission failed: ${err.message}`, "Next Mission");
  });
}

/**
 * Return to the scenario lobby: switch to mission view and expand the loader.
 */
function returnToLobby() {
  dismissMissionOverlay();
  setGameState("lobby");

  // Switch to the mission view tab
  const viewTabs = document.getElementById("view-tabs");
  if (viewTabs) {
    viewTabs.activeView = "mission";
  }

  // Expand the scenario-loader panel (remove collapsed attribute)
  const loaderPanel = document.querySelector(".mis-scenario-panel");
  if (loaderPanel) {
    loaderPanel.removeAttribute("collapsed");
  }

  // Trigger a refresh on the scenario-loader component
  const loader = document.querySelector("scenario-loader");
  if (loader && typeof loader._refreshAll === "function") {
    loader._refreshAll();
  }
}

/**
 * Send a command to the server (convenience wrapper)
 */
async function sendCommand(cmd, args = {}) {
  try {
    const response = await wsClient.send(cmd, args);
    return response;
  } catch (error) {
    console.error(`Command failed: ${cmd}`, error);
    showSystemMessage("error", `Command failed: ${error.message}`);
    return null;
  }
}

// Register modules globally for cross-module access (e.g., ws-client needs stateManager)
window._flaxosModules = {
  wsClient,
  stateManager
};

// Export for global access
window.flaxosApp = {
  wsClient,
  stateManager,
  helmRequests,
  mobileManager,
  sendCommand,
  showSystemMessage,
  setGameState,
  get gameState() { return app.gameState; },
  get nextScenarioId() { return app.nextScenarioId; },
  get isMobile() { return mobileManager.isMobile(); },
  config: app.config
};

// Initialize on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
