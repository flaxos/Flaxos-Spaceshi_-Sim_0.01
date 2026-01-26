/**
 * Station Manager - Multi-Crew Station Architecture
 * Inspired by Empty Epsilon / Bridge Commander
 *
 * Supports distributing UI components across multiple devices/screens
 * for cooperative bridge crew gameplay.
 */

// Station definitions with their associated panels
const STATION_CONFIG = {
  CAPTAIN: {
    id: "captain",
    label: "Captain",
    icon: "captain",
    description: "Command overview - all systems visible",
    panels: [
      "scenario-panel", "mission-panel", "status-panel", "nav-panel",
      "sensors-panel", "tactical-panel", "targeting-panel", "weapons-panel",
      "autopilot-panel", "event-log-panel"
    ],
    color: "#ffd700"
  },
  HELM: {
    id: "helm",
    label: "Helm",
    icon: "helm",
    description: "Navigation and flight control",
    panels: [
      "helm-requests-panel", "nav-panel", "heading-panel", "throttle-panel", "rcs-panel",
      "autopilot-panel", "flight-computer-panel", "position-heading-panel"
    ],
    color: "#00aaff"
  },
  NAVIGATION: {
    id: "navigation",
    label: "Navigation",
    icon: "nav",
    description: "Tactical map and course plotting",
    panels: [
      "nav-panel", "tactical-panel", "sensors-panel", "flight-computer-panel",
      "position-heading-panel", "autopilot-panel"
    ],
    color: "#00ff88"
  },
  TACTICAL: {
    id: "tactical",
    label: "Tactical",
    icon: "tactical",
    description: "Sensors, targeting, and weapons",
    panels: [
      "sensors-panel", "tactical-panel", "targeting-panel", "weapons-panel",
      "weapon-ctrl-panel"
    ],
    color: "#ff4444"
  },
  WEAPONS: {
    id: "weapons",
    label: "Weapons",
    icon: "weapons",
    description: "Fire control and weapons systems",
    panels: [
      "weapons-panel", "weapon-ctrl-panel", "targeting-panel", "tactical-panel"
    ],
    color: "#ff6600"
  },
  ENGINEERING: {
    id: "engineering",
    label: "Engineering",
    icon: "engineering",
    description: "Power and systems management",
    panels: [
      "status-panel", "systems-panel", "thrust-input-panel", "event-log-panel"
    ],
    color: "#ffaa00"
  },
  COMMUNICATIONS: {
    id: "communications",
    label: "Comms",
    icon: "comms",
    description: "Communications and mission objectives",
    panels: [
      "event-log-panel", "command-panel", "mission-panel", "sensors-panel"
    ],
    color: "#aa00ff"
  }
};

class StationManager {
  constructor() {
    this._currentStation = null;
    this._stationBar = null;
    this._isStationMode = false;
  }

  /**
   * Initialize station manager
   */
  init() {
    // Check URL for station parameter
    const params = new URLSearchParams(window.location.search);
    const stationParam = params.get("station");

    if (stationParam && STATION_CONFIG[stationParam.toUpperCase()]) {
      this.setStation(stationParam.toUpperCase());
    }

    // Create station selector if not in station mode
    if (!this._currentStation) {
      this._createStationSelector();
    }

    console.log("Station manager initialized");
  }

  /**
   * Create station selector bar
   */
  _createStationSelector() {
    // Check if already exists
    if (document.getElementById("station-selector")) return;

    this._stationBar = document.createElement("div");
    this._stationBar.id = "station-selector";
    this._stationBar.innerHTML = `
      <style>
        #station-selector {
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          background: var(--bg-panel, #12121a);
          border-top: 1px solid var(--border-default, #2a2a3a);
          padding: 8px 16px;
          display: flex;
          align-items: center;
          gap: 8px;
          z-index: 1000;
          flex-wrap: wrap;
        }

        #station-selector .label {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-right: 8px;
        }

        #station-selector .station-btn {
          padding: 8px 16px;
          background: var(--bg-input, #1a1a24);
          border: 2px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-secondary, #888899);
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
          min-height: 40px;
        }

        #station-selector .station-btn:hover {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }

        #station-selector .station-btn.active {
          border-color: var(--station-color, #00aaff);
          background: rgba(0, 170, 255, 0.2);
          color: var(--text-bright, #ffffff);
        }

        #station-selector .all-btn {
          margin-left: auto;
          background: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
          border-color: var(--status-info, #00aaff);
        }

        #station-selector .all-btn:hover {
          filter: brightness(1.1);
        }

        /* Adjust main content when station bar is visible */
        body.station-mode #interface-grid {
          padding-bottom: 70px;
        }

        /* Station header when in station mode */
        .station-header {
          position: fixed;
          top: 50px;
          left: 0;
          right: 0;
          background: var(--bg-panel, #12121a);
          border-bottom: 2px solid var(--station-color, #00aaff);
          padding: 8px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          z-index: 999;
        }

        .station-header .station-name {
          font-size: 1rem;
          font-weight: 600;
          color: var(--station-color, #00aaff);
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .station-header .station-desc {
          font-size: 0.75rem;
          color: var(--text-dim, #555566);
        }

        .station-header .exit-btn {
          padding: 6px 12px;
          background: transparent;
          border: 1px solid var(--text-dim, #555566);
          border-radius: 4px;
          color: var(--text-dim, #555566);
          font-size: 0.7rem;
          cursor: pointer;
        }

        .station-header .exit-btn:hover {
          border-color: var(--text-primary, #e0e0e0);
          color: var(--text-primary, #e0e0e0);
        }

        body.station-mode #interface-grid {
          margin-top: 40px;
        }
      </style>
      <span class="label">Station:</span>
      ${Object.values(STATION_CONFIG).map(station => `
        <button class="station-btn" data-station="${station.id}" style="--station-color: ${station.color};" title="${station.description}">
          ${station.label}
        </button>
      `).join("")}
      <button class="station-btn all-btn" data-station="all">All Panels</button>
    `;

    document.body.appendChild(this._stationBar);
    document.body.classList.add("station-mode");

    // Add event listeners
    this._stationBar.querySelectorAll(".station-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const stationId = btn.dataset.station;
        if (stationId === "all") {
          this.showAllPanels();
        } else {
          this.setStation(stationId.toUpperCase());
        }
      });
    });
  }

  /**
   * Set the current station and filter panels
   */
  setStation(stationId) {
    const station = STATION_CONFIG[stationId];
    if (!station) {
      console.warn(`Unknown station: ${stationId}`);
      return;
    }

    this._currentStation = station;
    this._isStationMode = true;

    // Update URL
    const url = new URL(window.location);
    url.searchParams.set("station", station.id);
    window.history.replaceState({}, "", url);

    // Update station bar buttons
    if (this._stationBar) {
      this._stationBar.querySelectorAll(".station-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.station === station.id);
      });
    }

    // Filter panels
    this._filterPanels(station.panels);

    // Add/update station header
    this._createStationHeader(station);

    console.log(`Station set to: ${station.label}`);

    // Dispatch event
    window.dispatchEvent(new CustomEvent("station:change", {
      detail: { station: station.id, config: station }
    }));
  }

  /**
   * Show all panels (captain mode / single player)
   */
  showAllPanels() {
    this._currentStation = null;
    this._isStationMode = false;

    // Update URL
    const url = new URL(window.location);
    url.searchParams.delete("station");
    window.history.replaceState({}, "", url);

    // Update station bar buttons
    if (this._stationBar) {
      this._stationBar.querySelectorAll(".station-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.station === "all");
      });
    }

    // Show all panels
    const grid = document.getElementById("interface-grid");
    if (grid) {
      grid.querySelectorAll("flaxos-panel").forEach(panel => {
        panel.style.display = "";
      });
    }

    // Remove station header
    const header = document.getElementById("station-header");
    if (header) header.remove();

    console.log("Showing all panels");

    // Dispatch event
    window.dispatchEvent(new CustomEvent("station:change", {
      detail: { station: "all", config: null }
    }));
  }

  /**
   * Filter visible panels based on station configuration
   */
  _filterPanels(allowedPanels) {
    const grid = document.getElementById("interface-grid");
    if (!grid) return;

    grid.querySelectorAll("flaxos-panel").forEach(panel => {
      const panelClass = Array.from(panel.classList).find(c => c.endsWith("-panel"));
      if (panelClass) {
        const shouldShow = allowedPanels.includes(panelClass);
        panel.style.display = shouldShow ? "" : "none";
      }
    });
  }

  /**
   * Create station header bar
   */
  _createStationHeader(station) {
    let header = document.getElementById("station-header");

    if (!header) {
      header = document.createElement("div");
      header.id = "station-header";
      header.className = "station-header";
      document.body.appendChild(header);
    }

    header.style.setProperty("--station-color", station.color);
    header.innerHTML = `
      <div>
        <div class="station-name">${station.label} Station</div>
        <div class="station-desc">${station.description}</div>
      </div>
      <button class="exit-btn" id="exit-station-btn">Exit Station View</button>
    `;

    header.querySelector("#exit-station-btn").addEventListener("click", () => {
      this.showAllPanels();
    });
  }

  /**
   * Get current station
   */
  getCurrentStation() {
    return this._currentStation;
  }

  /**
   * Check if in station mode
   */
  isStationMode() {
    return this._isStationMode;
  }

  /**
   * Get station configuration
   */
  getStationConfig(stationId) {
    return STATION_CONFIG[stationId?.toUpperCase()] || null;
  }

  /**
   * Get all station configurations
   */
  getAllStations() {
    return STATION_CONFIG;
  }

  /**
   * Generate URL for a specific station
   */
  getStationURL(stationId) {
    const url = new URL(window.location);
    url.searchParams.set("station", stationId.toLowerCase());
    return url.toString();
  }
}

// Export singleton
const stationManager = new StationManager();
export { StationManager, stationManager, STATION_CONFIG };
