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
import { stationManager } from "./station-manager.js";
// Phase 8: Inter-Station Communication
import "../components/helm-requests.js";
import { helmRequests } from "./helm-requests.js";
// Sprint B: Navigation loop - set_course and autopilot
import "../components/set-course-control.js";
import "../components/autopilot-status.js";

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

  // Listen for scenario load to set player ship ID
  document.addEventListener("scenario-loaded", (e) => {
    const { playerShipId, scenario, shipsLoaded, mission } = e.detail;
    if (playerShipId) {
      stateManager.setPlayerShipId(playerShipId);
      console.log(`Scenario "${scenario}" loaded with ${shipsLoaded} ships, player: ${playerShipId}`);
    }
    showSystemMessage("success", `Scenario "${scenario}" loaded`, "Mission Ready");
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
  // Escape - close modals, clear focus
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
