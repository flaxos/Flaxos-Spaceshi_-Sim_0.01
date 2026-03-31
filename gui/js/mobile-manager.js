/**
 * Mobile Detection & Layout Manager — Phase 6: Mobile Optimization
 * Detects mobile devices, toggles `mobile-layout-active` on <body>,
 * and manages the mobile tab bar, control zone, and touch controls.
 */
import { wsClient } from "./ws-client.js";
import { stateManager } from "./state-manager.js";

// View definitions for the mobile tab bar
const MOBILE_VIEWS = [
  { id: "helm",        icon: "\u2B21", label: "HELM" },
  { id: "tactical",    icon: "\u2295", label: "TAC" },
  { id: "ops",         icon: "\u25C8", label: "OPS" },
  { id: "engineering", icon: "\u2699", label: "ENG" },
  { id: "fleet",       icon: "\u2B22", label: "FLEET" },
  { id: "mission",     icon: "\uD83D\uDCCB", label: "MISSION" },
];

// Quick action button definitions
const QUICK_ACTIONS = [
  { id: "fire",   label: "\u2316", title: "Fire Railgun" },
  { id: "lock",   label: "\uD83D\uDD12", title: "Lock/Unlock Target" },
  { id: "ping",   label: "\uD83D\uDCE1", title: "Active Sensor Ping" },
  { id: "ap",     label: "AP",   title: "Autopilot On/Off" },
];

class MobileManager {
  constructor() {
    this._active = false;
    this._mediaQuery = null;
    this._tabBar = null;
    this._controlZone = null;
    this._activeView = "helm";
    this._orientationHandler = null;
  }

  /**
   * Initialize mobile detection and layout switching.
   * Call once during app startup.
   */
  init() {
    this._mediaQuery = window.matchMedia("(max-width: 768px)");
    // Check initial state
    this._onMediaChange(this._mediaQuery);

    // Listen for viewport changes (resize, orientation)
    this._mediaQuery.addEventListener("change", (e) => this._onMediaChange(e));

    // Orientation change fallback for older Android browsers
    this._orientationHandler = () => {
      // Re-evaluate after orientation settles
      setTimeout(() => this._onMediaChange(this._mediaQuery), 100);
    };
    window.addEventListener("orientationchange", this._orientationHandler);
  }

  /**
   * Whether mobile layout is currently active.
   * @returns {boolean}
   */
  isMobile() {
    return this._active;
  }

  /**
   * Handle media query match/unmatch.
   * @param {MediaQueryList|MediaQueryListEvent} mq
   */
  _onMediaChange(mq) {
    const shouldBeActive = mq.matches || this._hasTouchOnly();

    if (shouldBeActive && !this._active) {
      this._activate();
    } else if (!shouldBeActive && this._active) {
      this._deactivate();
    }
  }

  /**
   * Heuristic: device has touch but no fine pointer (likely phone/tablet).
   * Used as a secondary signal alongside the width media query.
   */
  _hasTouchOnly() {
    return (
      "ontouchstart" in window &&
      !window.matchMedia("(pointer: fine)").matches
    );
  }

  /**
   * Activate mobile layout: add body class, create mobile DOM.
   */
  _activate() {
    this._active = true;
    document.body.classList.add("mobile-layout-active");

    // Hide desktop controls
    const bridgeControls = document.getElementById("bridge-controls");
    if (bridgeControls) bridgeControls.style.display = "none";
    const desktopTabs = document.getElementById("view-tabs");
    if (desktopTabs) desktopTabs.style.display = "none";

    // Create mobile DOM elements
    this._createTabBar();
    this._createControlZone();

    // Sync active view with desktop state
    const desktopTabs2 = document.getElementById("view-tabs");
    if (desktopTabs2?.activeView) {
      this._switchView(desktopTabs2.activeView);
    }

    console.log("Mobile layout activated");
  }

  /**
   * Deactivate mobile layout: remove body class, destroy mobile DOM.
   */
  _deactivate() {
    this._active = false;
    document.body.classList.remove("mobile-layout-active");

    // Restore desktop controls
    const bridgeControls = document.getElementById("bridge-controls");
    if (bridgeControls) bridgeControls.style.display = "";
    const desktopTabs = document.getElementById("view-tabs");
    if (desktopTabs) desktopTabs.style.display = "";

    // Remove mobile DOM
    this._removeTabBar();
    this._removeControlZone();

    console.log("Mobile layout deactivated");
  }

  /**
   * Create the sticky top tab bar for view switching.
   */
  _createTabBar() {
    if (this._tabBar) return;

    const bar = document.createElement("div");
    bar.className = "mobile-tab-bar";
    bar.id = "mobile-tab-bar";

    MOBILE_VIEWS.forEach((view) => {
      const tab = document.createElement("button");
      tab.className = `mobile-tab${view.id === this._activeView ? " active" : ""}`;
      tab.dataset.view = view.id;
      tab.innerHTML = `
        <span class="tab-icon">${view.icon}</span>
        <span class="tab-label">${view.label}</span>
      `;
      tab.addEventListener("click", () => this._switchView(view.id));
      bar.appendChild(tab);
    });

    // Insert before #app content (after body opening)
    const app = document.getElementById("app");
    if (app) {
      app.insertBefore(bar, app.firstChild);
    } else {
      document.body.insertBefore(bar, document.body.firstChild);
    }

    this._tabBar = bar;
  }

  _removeTabBar() {
    if (this._tabBar) {
      this._tabBar.remove();
      this._tabBar = null;
    }
  }

  /**
   * Create the fixed bottom control zone with touch controls and quick actions.
   */
  _createControlZone() {
    if (this._controlZone) return;

    const zone = document.createElement("div");
    zone.className = "mobile-control-zone";
    zone.id = "mobile-control-zone";

    zone.innerHTML = `
      <div class="control-zone-content">
        <div class="touch-controls-container">
          <touch-throttle></touch-throttle>
          <touch-joystick></touch-joystick>
        </div>
        <div class="quick-actions-mobile">
          ${QUICK_ACTIONS.map((a) => `
            <button class="mobile-action-btn" data-action="${a.id}" title="${a.title}">
              ${a.label}
            </button>
          `).join("")}
        </div>
      </div>
    `;

    // Wire quick action buttons
    zone.querySelectorAll(".mobile-action-btn").forEach((btn) => {
      btn.addEventListener("click", () => this._handleQuickAction(btn.dataset.action));
    });

    document.body.appendChild(zone);
    this._controlZone = zone;
  }

  _removeControlZone() {
    if (this._controlZone) {
      this._controlZone.remove();
      this._controlZone = null;
    }
  }

  /**
   * Switch the active view (syncs both mobile tabs and desktop view containers).
   * @param {string} viewId
   */
  _switchView(viewId) {
    this._activeView = viewId;

    // Update mobile tab bar active state
    if (this._tabBar) {
      this._tabBar.querySelectorAll(".mobile-tab").forEach((tab) => {
        tab.classList.toggle("active", tab.dataset.view === viewId);
      });
    }

    // Drive the desktop view-tabs component to actually switch views
    // This triggers its view-change event which toggles view-container.active
    const desktopTabs = document.getElementById("view-tabs");
    if (desktopTabs) {
      desktopTabs.activeView = viewId;
    }
  }

  /**
   * Handle quick action button presses.
   * @param {string} action
   */
  _handleQuickAction(action) {
    switch (action) {
      case "fire":
        wsClient.sendShipCommand("fire", {}).catch((err) => {
          console.warn("Mobile fire failed:", err.message);
        });
        break;

      case "lock": {
        // Toggle target lock on current selected contact
        const contacts = stateManager.getContacts();
        if (contacts && contacts.length > 0) {
          const targeting = stateManager.getTargeting();
          if (targeting?.locked) {
            wsClient.sendShipCommand("unlock_target", {}).catch((err) => {
              console.warn("Unlock failed:", err.message);
            });
          } else {
            const targetId = contacts[0]?.contact_id || contacts[0]?.id;
            if (targetId) {
              wsClient.sendShipCommand("lock_target", { target: targetId }).catch((err) => {
                console.warn("Lock failed:", err.message);
              });
            }
          }
        }
        break;
      }

      case "ping":
        wsClient.sendShipCommand("active_scan", {}).catch((err) => {
          console.warn("Active scan failed:", err.message);
        });
        break;

      case "ap": {
        // Toggle autopilot
        const nav = stateManager.getNavigation();
        const apActive = nav?.autopilot_program || nav?.autopilot?.program;
        if (apActive) {
          wsClient.sendShipCommand("disengage_autopilot", {}).catch((err) => {
            console.warn("AP disengage failed:", err.message);
          });
        } else {
          wsClient.sendShipCommand("autopilot", { program: "all_stop", g_level: 1.0 }).catch((err) => {
            console.warn("AP engage failed:", err.message);
          });
        }
        break;
      }
    }
  }
}

const mobileManager = new MobileManager();

export { mobileManager };
