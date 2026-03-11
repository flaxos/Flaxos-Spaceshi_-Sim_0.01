/**
 * Station Selector Component
 * Handles the register -> assign_ship -> claim_station flow for multi-crew.
 * Fixes BUG-003: GUI previously skipped the registration handshake entirely.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

// Station roles must match server-side enum values
const STATIONS = [
  { id: "captain",         label: "CAPTAIN",         color: "#ffcc00" },
  { id: "helm",            label: "HELM",            color: "#00aaff" },
  { id: "tactical",        label: "TACTICAL",        color: "#ff4444" },
  { id: "ops",             label: "OPS",             color: "#00ff88" },
  { id: "engineering",     label: "ENGINEERING",     color: "#ff8800" },
  { id: "comms",           label: "COMMS",           color: "#aa88ff" },
  { id: "fleet_commander", label: "FLEET COMMANDER", color: "#ff66cc" },
];

class StationSelector extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this._registered = false;
    this._assignedShipId = null;
    this._claimedStation = null;
    this._clientId = null;
    this._statusPollInterval = null;
    this._isProcessing = false;
  }

  connectedCallback() {
    this.render();
    this._bindEvents();
    this._setupButtons();
    this._updateDisplay();

    // If already connected, kick off registration immediately
    if (wsClient.isConnected) {
      this._beginRegistration();
    }
  }

  disconnectedCallback() {
    this._unbindEvents();
    this._stopPolling();
  }

  _bindEvents() {
    this._onStatusChange = () => {
      this._updateDisplay();
      // Auto-register when connection comes up
      if (wsClient.isConnected && !this._registered) {
        this._beginRegistration();
      }
    };

    this._onScenarioLoaded = (e) => {
      // A scenario was loaded -- try to assign ship if we are registered
      if (this._registered && !this._assignedShipId) {
        this._tryAssignShip();
      }
    };

    wsClient.addEventListener("status_change", this._onStatusChange);
    // Listen on document for scenario-loaded bubbling from scenario-loader
    document.addEventListener("scenario-loaded", this._onScenarioLoaded);
  }

  _unbindEvents() {
    wsClient.removeEventListener("status_change", this._onStatusChange);
    document.removeEventListener("scenario-loaded", this._onScenarioLoaded);
  }

  // -- Registration flow --------------------------------------------------

  async _beginRegistration() {
    if (this._isProcessing || this._registered) return;
    this._isProcessing = true;
    this._setStatus("Registering with server...", "info");

    try {
      const response = await wsClient.send("register_client", {
        client_name: "bridge-gui",
      });

      if (response && response.ok !== false) {
        this._registered = true;
        this._clientId = response.client_id || null;
        this._setStatus("Registered. Checking for ship assignment...", "info");
        await this._tryAssignShip();
        this._startPolling();
      } else {
        const msg = response?.error || "Registration rejected";
        this._setStatus(`Registration failed: ${msg}`, "error");
      }
    } catch (err) {
      this._setStatus(`Registration error: ${err.message}`, "error");
    } finally {
      this._isProcessing = false;
      this._updateDisplay();
    }
  }

  async _tryAssignShip() {
    const shipId = stateManager.getPlayerShipId();
    if (!shipId) {
      this._setStatus("Registered. Load a scenario to continue.", "info");
      return;
    }

    this._setStatus(`Assigning to ship ${shipId}...`, "info");

    try {
      const response = await wsClient.send("assign_ship", { ship_id: shipId });

      if (response && response.ok !== false) {
        this._assignedShipId = shipId;
        this._setStatus(`Assigned to ${shipId}. Select a station.`, "success");
      } else {
        const msg = response?.error || "Assignment rejected";
        this._setStatus(`Ship assignment failed: ${msg}`, "error");
      }
    } catch (err) {
      this._setStatus(`Ship assignment error: ${err.message}`, "error");
    }

    this._updateDisplay();
  }

  // -- Claim / Release -----------------------------------------------------

  async _claimStation(stationId) {
    if (this._isProcessing) return;
    this._isProcessing = true;
    this._setStatus(`Claiming ${stationId.toUpperCase()}...`, "info");

    try {
      const response = await wsClient.send("claim_station", {
        station: stationId,
      });

      if (response && response.ok !== false) {
        this._claimedStation = stationId;
        this._setStatus(`Station: ${stationId.toUpperCase()}`, "success");

        this.dispatchEvent(
          new CustomEvent("station-claimed", {
            detail: { station: stationId },
            bubbles: true,
          })
        );
      } else {
        const msg = response?.error || "Claim rejected";
        this._setStatus(`Claim failed: ${msg}`, "error");
      }
    } catch (err) {
      this._setStatus(`Claim error: ${err.message}`, "error");
    } finally {
      this._isProcessing = false;
      this._updateDisplay();
    }
  }

  async _releaseStation() {
    if (this._isProcessing || !this._claimedStation) return;
    this._isProcessing = true;
    const prev = this._claimedStation;
    this._setStatus("Releasing station...", "info");

    try {
      const response = await wsClient.send("release_station", {});

      if (response && response.ok !== false) {
        this._claimedStation = null;
        this._setStatus("Station released. Select a new station.", "info");

        this.dispatchEvent(
          new CustomEvent("station-released", {
            detail: { station: prev },
            bubbles: true,
          })
        );
      } else {
        const msg = response?.error || "Release rejected";
        this._setStatus(`Release failed: ${msg}`, "error");
      }
    } catch (err) {
      this._setStatus(`Release error: ${err.message}`, "error");
    } finally {
      this._isProcessing = false;
      this._updateDisplay();
    }
  }

  // -- Polling -------------------------------------------------------------

  _startPolling() {
    this._stopPolling();
    this._statusPollInterval = setInterval(() => this._pollStatus(), 5000);
  }

  _stopPolling() {
    if (this._statusPollInterval) {
      clearInterval(this._statusPollInterval);
      this._statusPollInterval = null;
    }
  }

  async _pollStatus() {
    if (!wsClient.isConnected) return;

    // If registered but not yet assigned to a ship, retry assignment
    // (stateManager may have auto-detected the player ship since last check)
    if (this._registered && !this._assignedShipId) {
      await this._tryAssignShip();
    }

    try {
      const response = await wsClient.send("my_status", {});
      if (response && response.ok !== false) {
        // Reconcile local state with server truth
        const serverStation = response.station || null;
        if (serverStation !== this._claimedStation) {
          this._claimedStation = serverStation;
          this._updateDisplay();
        }
        if (response.ship_id && response.ship_id !== this._assignedShipId) {
          this._assignedShipId = response.ship_id;
          this._updateDisplay();
        }
      }
    } catch {
      // Polling failures are non-critical; silently retry next cycle
    }
  }

  // -- Rendering -----------------------------------------------------------

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", system-ui, sans-serif);
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 12px;
        }

        .connection-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
        }

        .conn-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #555566;
          flex-shrink: 0;
          transition: all 0.3s ease;
        }

        .conn-dot.connected {
          background: #00ff88;
          box-shadow: 0 0 6px #00ff88;
        }

        .conn-dot.registered {
          background: #00aaff;
          box-shadow: 0 0 6px #00aaff;
        }

        .conn-label {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .station-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
          margin-bottom: 12px;
        }

        .station-btn {
          padding: 10px 8px;
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
          background: var(--bg-input, #1a1a24);
          color: var(--text-primary, #e0e0e0);
          font-family: inherit;
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          transition: all 0.15s ease;
          text-align: center;
        }

        .station-btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
        }

        .station-btn:disabled {
          opacity: 0.35;
          cursor: not-allowed;
        }

        .station-btn.active {
          border-width: 2px;
          font-weight: 700;
        }

        /* Full-width last item when odd count */
        .station-btn.full-width {
          grid-column: 1 / -1;
        }

        .release-btn {
          width: 100%;
          padding: 10px 16px;
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
          background: var(--bg-input, #1a1a24);
          color: var(--status-critical, #ff4444);
          font-family: inherit;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.1s ease;
          margin-bottom: 12px;
        }

        .release-btn:hover:not(:disabled) {
          background: rgba(255, 68, 68, 0.1);
          border-color: var(--status-critical, #ff4444);
        }

        .release-btn:disabled {
          opacity: 0.35;
          cursor: not-allowed;
        }

        .status-box {
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .status-box.info { color: var(--status-info, #00aaff); }
        .status-box.warning { color: var(--status-warning, #ffaa00); }
        .status-box.error { color: var(--status-critical, #ff4444); }
        .status-box.success { color: var(--status-nominal, #00ff88); }

        .claimed-badge {
          display: inline-block;
          padding: 4px 10px;
          border-radius: 4px;
          font-size: 0.8rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 12px;
        }

        .hidden {
          display: none;
        }
      </style>

      <div class="section-title">Crew Station</div>

      <div class="connection-row">
        <span class="conn-dot" id="conn-dot"></span>
        <span class="conn-label" id="conn-label">Disconnected</span>
      </div>

      <div id="claimed-badge" class="claimed-badge hidden"></div>

      <div class="station-grid" id="station-grid"></div>

      <button class="release-btn" id="release-btn" disabled>Release Station</button>

      <div class="status-box" id="status-box">Not registered</div>
    `;
  }

  _setupButtons() {
    // Build station buttons
    const grid = this.shadowRoot.getElementById("station-grid");
    grid.innerHTML = STATIONS.map((s, i) => {
      // Last item gets full width if odd count
      const fullWidth = i === STATIONS.length - 1 && STATIONS.length % 2 !== 0;
      return `<button class="station-btn${fullWidth ? " full-width" : ""}"
                      data-station="${s.id}"
                      disabled
                      style="--station-color: ${s.color}">${s.label}</button>`;
    }).join("");

    // Attach click handlers
    grid.querySelectorAll(".station-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._claimStation(btn.dataset.station);
      });
    });

    // Release button
    this.shadowRoot.getElementById("release-btn").addEventListener("click", () => {
      this._releaseStation();
    });
  }

  _updateDisplay() {
    const connDot = this.shadowRoot.getElementById("conn-dot");
    const connLabel = this.shadowRoot.getElementById("conn-label");
    const releaseBtn = this.shadowRoot.getElementById("release-btn");
    const badge = this.shadowRoot.getElementById("claimed-badge");

    if (!connDot) return; // not yet rendered

    // Connection indicator
    const connected = wsClient.isConnected;
    connDot.className = "conn-dot";
    if (connected && this._registered) {
      connDot.classList.add("registered");
      connLabel.textContent = this._assignedShipId
        ? `Ship: ${this._assignedShipId}`
        : "Registered (no ship)";
    } else if (connected) {
      connDot.classList.add("connected");
      connLabel.textContent = "Connected (not registered)";
    } else {
      connLabel.textContent = "Disconnected";
    }

    // Station buttons: only enabled when assigned to a ship
    const canClaim = this._registered && this._assignedShipId && !this._isProcessing;
    this.shadowRoot.querySelectorAll(".station-btn").forEach((btn) => {
      const stationId = btn.dataset.station;
      const isActive = stationId === this._claimedStation;

      btn.disabled = !canClaim || isActive;
      btn.classList.toggle("active", isActive);

      // Apply station color to active button border
      if (isActive) {
        const stationDef = STATIONS.find((s) => s.id === stationId);
        btn.style.borderColor = stationDef ? stationDef.color : "";
        btn.style.color = stationDef ? stationDef.color : "";
        btn.style.background = stationDef
          ? `rgba(${this._hexToRgb(stationDef.color)}, 0.12)`
          : "";
      } else {
        btn.style.borderColor = "";
        btn.style.color = "";
        btn.style.background = "";
      }
    });

    // Release button
    releaseBtn.disabled = !this._claimedStation || this._isProcessing;

    // Claimed badge
    if (this._claimedStation) {
      const stationDef = STATIONS.find((s) => s.id === this._claimedStation);
      badge.textContent = stationDef ? stationDef.label : this._claimedStation;
      badge.style.color = stationDef ? stationDef.color : "";
      badge.style.background = stationDef
        ? `rgba(${this._hexToRgb(stationDef.color)}, 0.15)`
        : "";
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }

  _setStatus(message, variant = "") {
    const box = this.shadowRoot.getElementById("status-box");
    if (!box) return;
    box.textContent = message;
    box.className = "status-box";
    if (variant) box.classList.add(variant);
  }

  /**
   * Convert a hex color like "#ff4444" to an "r, g, b" string for use
   * inside rgba().
   */
  _hexToRgb(hex) {
    const h = hex.replace("#", "");
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `${r}, ${g}, ${b}`;
  }

  // -- Public API ----------------------------------------------------------

  /** Returns the currently claimed station id, or null. */
  getClaimedStation() {
    return this._claimedStation;
  }

  /** Returns true if this client has completed registration. */
  isRegistered() {
    return this._registered;
  }
}

customElements.define("station-selector", StationSelector);
export { StationSelector };
