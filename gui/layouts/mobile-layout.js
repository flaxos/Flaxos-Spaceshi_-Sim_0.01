/**
 * Mobile Layout Module
 * Phase 6: Mobile Optimization
 * 
 * Provides a tab-based mobile interface with persistent control zones.
 * Automatically activates on screens <= 768px.
 */

const MOBILE_BREAKPOINT = 768;

// Tab configuration - each tab groups related panels
const MOBILE_TABS = [
  {
    id: "nav",
    label: "NAV",
    icon: "🧭",
    panels: ["nav-panel", "status-panel", "autopilot-panel"]
  },
  {
    id: "sen",
    label: "SEN",
    icon: "📡",
    panels: ["sensors-panel", "targeting-panel", "tactical-panel"]
  },
  {
    id: "wpn",
    label: "WPN",
    icon: "🎯",
    panels: ["weapons-panel", "weapon-ctrl-panel"]
  },
  {
    id: "log",
    label: "LOG",
    icon: "📋",
    panels: ["event-log-panel", "command-panel", "mission-panel"]
  },
  {
    id: "sys",
    label: "SYS",
    icon: "⚙️",
    panels: ["systems-panel", "scenario-panel", "thrust-input-panel"]
  }
];

class MobileLayout {
  constructor() {
    this._active = false;
    this._currentTab = "nav";
    this._tabBar = null;
    this._controlZone = null;
    this._swipeStartX = 0;
    this._swipeStartY = 0;
    this._mediaQuery = null;
    this._originalStyles = new Map();
  }

  /**
   * Initialize mobile layout system
   * Sets up media query listener and initial state
   */
  init() {
    // Set up media query for responsive detection
    this._mediaQuery = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);
    this._mediaQuery.addEventListener("change", (e) => this._handleBreakpoint(e));

    // Check initial state
    this._handleBreakpoint(this._mediaQuery);

    console.log("Mobile layout initialized");
  }

  /**
   * Handle breakpoint changes
   */
  _handleBreakpoint(e) {
    if (e.matches && !this._active) {
      this._activateMobile();
    } else if (!e.matches && this._active) {
      this._deactivateMobile();
    }
  }

  /**
   * Activate mobile layout
   */
  _activateMobile() {
    if (this._active) return;
    this._active = true;

    console.log("Activating mobile layout");

    // Add mobile class to body
    document.body.classList.add("mobile-layout-active");

    // Create mobile UI elements
    this._createTabBar();
    this._createControlZone();

    // Hide desktop quick actions
    const quickActions = document.getElementById("quick-actions");
    if (quickActions) {
      this._originalStyles.set(quickActions, quickActions.style.display);
      quickActions.style.display = "none";
    }

    // Show initial tab
    this._showTab(this._currentTab);

    // Set up swipe gestures
    this._setupSwipeGestures();

    // Dispatch event
    window.dispatchEvent(new CustomEvent("mobile:activated"));
  }

  /**
   * Deactivate mobile layout
   */
  _deactivateMobile() {
    if (!this._active) return;
    this._active = false;

    console.log("Deactivating mobile layout");

    // Remove mobile class
    document.body.classList.remove("mobile-layout-active");

    // Remove mobile UI elements
    this._tabBar?.remove();
    this._tabBar = null;
    this._controlZone?.remove();
    this._controlZone = null;

    // Restore quick actions
    const quickActions = document.getElementById("quick-actions");
    if (quickActions && this._originalStyles.has(quickActions)) {
      quickActions.style.display = this._originalStyles.get(quickActions);
    }

    // Show all panels
    this._showAllPanels();

    // Dispatch event
    window.dispatchEvent(new CustomEvent("mobile:deactivated"));
  }

  /**
   * Create the tab bar UI
   */
  _createTabBar() {
    this._tabBar = document.createElement("nav");
    this._tabBar.id = "mobile-tab-bar";
    this._tabBar.className = "mobile-tab-bar";
    this._tabBar.innerHTML = MOBILE_TABS.map(tab => `
      <button class="mobile-tab ${tab.id === this._currentTab ? "active" : ""}" 
              data-tab="${tab.id}"
              aria-label="${tab.label}">
        <span class="tab-icon">${tab.icon}</span>
        <span class="tab-label">${tab.label}</span>
      </button>
    `).join("");

    // Add click handlers
    this._tabBar.querySelectorAll(".mobile-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        this._showTab(btn.dataset.tab);
      });
    });

    // Insert after connection bar
    const connectionBar = document.getElementById("connection-bar");
    connectionBar?.after(this._tabBar);
  }

  /**
   * Create the persistent control zone
   */
  _createControlZone() {
    this._controlZone = document.createElement("div");
    this._controlZone.id = "mobile-control-zone";
    this._controlZone.className = "mobile-control-zone";
    this._controlZone.innerHTML = `
      <div class="control-zone-content">
        <div class="touch-controls-container">
          <touch-throttle id="mobile-throttle"></touch-throttle>
          <touch-joystick id="mobile-joystick"></touch-joystick>
        </div>
        <div class="quick-actions-mobile">
          <button class="mobile-action-btn" data-action="fire" aria-label="Fire">🚀</button>
          <button class="mobile-action-btn" data-action="lock" aria-label="Lock Target">🎯</button>
          <button class="mobile-action-btn" data-action="autopilot" aria-label="Autopilot">🤖</button>
          <button class="mobile-action-btn" data-action="ping" aria-label="Ping Sensors">📡</button>
        </div>
      </div>
    `;

    // Add action button handlers
    this._controlZone.querySelectorAll(".mobile-action-btn").forEach(btn => {
      btn.addEventListener("click", () => this._handleQuickAction(btn.dataset.action));
    });

    // Append to body
    document.body.appendChild(this._controlZone);
  }

  /**
   * Show a specific tab
   */
  _showTab(tabId) {
    this._currentTab = tabId;

    // Update tab bar active state
    this._tabBar?.querySelectorAll(".mobile-tab").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.tab === tabId);
    });

    // Get panels for this tab
    const tabConfig = MOBILE_TABS.find(t => t.id === tabId);
    if (!tabConfig) return;

    // Hide all panels, show only current tab's panels
    const grid = document.getElementById("interface-grid");
    if (!grid) return;

    const allPanels = grid.querySelectorAll("flaxos-panel");
    allPanels.forEach(panel => {
      const panelClass = Array.from(panel.classList).find(c => c.endsWith("-panel"));
      if (panelClass) {
        const shouldShow = tabConfig.panels.includes(panelClass);
        panel.style.display = shouldShow ? "" : "none";
      }
    });

    // Dispatch tab change event
    window.dispatchEvent(new CustomEvent("mobile:tab_change", { detail: { tab: tabId } }));
  }

  /**
   * Show all panels (when deactivating mobile)
   */
  _showAllPanels() {
    const grid = document.getElementById("interface-grid");
    if (!grid) return;

    const allPanels = grid.querySelectorAll("flaxos-panel");
    allPanels.forEach(panel => {
      panel.style.display = "";
    });
  }

  /**
   * Set up swipe gestures for tab navigation
   */
  _setupSwipeGestures() {
    const grid = document.getElementById("interface-grid");
    if (!grid) return;

    grid.addEventListener("touchstart", (e) => {
      this._swipeStartX = e.touches[0].clientX;
      this._swipeStartY = e.touches[0].clientY;
    }, { passive: true });

    grid.addEventListener("touchend", (e) => {
      if (!this._active) return;

      const deltaX = e.changedTouches[0].clientX - this._swipeStartX;
      const deltaY = e.changedTouches[0].clientY - this._swipeStartY;

      // Only trigger if horizontal swipe is dominant
      if (Math.abs(deltaX) > 50 && Math.abs(deltaX) > Math.abs(deltaY) * 1.5) {
        const currentIndex = MOBILE_TABS.findIndex(t => t.id === this._currentTab);
        if (deltaX > 0 && currentIndex > 0) {
          // Swipe right - previous tab
          this._showTab(MOBILE_TABS[currentIndex - 1].id);
        } else if (deltaX < 0 && currentIndex < MOBILE_TABS.length - 1) {
          // Swipe left - next tab
          this._showTab(MOBILE_TABS[currentIndex + 1].id);
        }
      }
    }, { passive: true });
  }

  /**
   * Handle quick action button press
   */
  _handleQuickAction(action) {
    const wsClient = window.flaxosApp?.wsClient;
    if (!wsClient) return;

    switch (action) {
      case "fire":
        wsClient.send("fire_weapon", { weapon: "torpedo" });
        break;
      case "lock":
        // Toggle lock on selected contact
        const contacts = window.flaxosApp?.stateManager?.getContacts();
        if (contacts && contacts.length > 0) {
          wsClient.send("lock_target", { target_id: contacts[0].id });
        }
        break;
      case "autopilot":
        wsClient.send("autopilot", { program: "hold" });
        break;
      case "ping":
        wsClient.send("ping_sensors", {});
        break;
    }

    // Visual feedback
    const btn = this._controlZone?.querySelector(`[data-action="${action}"]`);
    if (btn) {
      btn.classList.add("pressed");
      setTimeout(() => btn.classList.remove("pressed"), 150);
    }
  }

  /**
   * Check if mobile layout is currently active
   */
  isActive() {
    return this._active;
  }

  /**
   * Get current tab
   */
  getCurrentTab() {
    return this._currentTab;
  }

  /**
   * Manually switch to a tab
   */
  switchTab(tabId) {
    if (this._active && MOBILE_TABS.some(t => t.id === tabId)) {
      this._showTab(tabId);
    }
  }
}

// Export singleton
const mobileLayout = new MobileLayout();
export { MobileLayout, mobileLayout, MOBILE_TABS, MOBILE_BREAKPOINT };
