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
import "../components/navigation-display.js";
import "../components/sensor-contacts.js";
import "../components/targeting-display.js";
import "../components/weapons-status.js";
import "../components/firing-solution-display.js";
// Phase 4: Visual Controls
import "../components/throttle-control.js";
import "../components/heading-control.js";
import "../components/rcs-controls.js";
import "../components/micro-rcs-control.js";
import "../components/position-heading-calculator.js";
import "../components/autopilot-control.js";
import "../components/weapon-controls.js";
import "../components/system-toggles.js";
import "../components/power-management.js";
import "../components/quick-actions.js";
import "../components/manual-thrust.js";
import "../components/tactical-map.js";
// Phase 5: Integration
import "../components/scenario-loader.js";
import "../components/mission-objectives.js";
// Phase 6: Mobile
import "../components/touch-throttle.js";
import "../components/touch-joystick.js";
import { mobileLayout } from "../layouts/mobile-layout.js";
import { initMobileGestures } from "./gestures.js";
// Phase 7: Enhanced Navigation & Multi-Crew
import "../components/flight-computer.js";
import "../components/maneuver-planner.js";
import { stationManager } from "./station-manager.js";
// Phase 8: Inter-Station Communication
import "../components/helm-requests.js";
import { helmRequests } from "./helm-requests.js";
// Sprint B: Navigation loop - set_course and autopilot
import "../components/set-course-control.js";
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
import "../components/delta-v-display.js";
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
// Helm Navigation Commands
import "../components/helm-navigation-panel.js";
// Helm Navigation Display (comprehensive nav readout)
import "../components/helm-nav-display.js";
// Ops Station Controls
import "../components/ops-control-panel.js";
// ECM Electronic Warfare
import "../components/ecm-control-panel.js";
// ECCM Counter-Jamming
import "../components/eccm-control-panel.js";
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
// Tutorial System
import "../components/tutorial-overlay.js";
// Inter-station messaging
import "../components/station-chat.js";
// Mission comms choices (branching dialogue)
import "../components/comms-choice-panel.js";
// Multi-target tracking
import "../components/multi-track-panel.js";

// App state
const app = {
  initialized: false,
  config: {
    wsUrl: null, // Auto-detect
    autoConnect: true,
    debugMode: false
  }
};

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

  // Initialize mobile layout (Phase 6)
  mobileLayout.init();
  initMobileGestures();

  // Initialize station manager (Phase 7)
  stationManager.init();

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
  mobileLayout,
  stationManager,
  helmRequests,
  sendCommand,
  showSystemMessage,
  config: app.config
};

// Initialize on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
