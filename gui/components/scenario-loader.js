/**
 * Scenario Loader & Fleet Lobby Panel
 * List and load available scenarios, or join an active fleet.
 */

import { wsClient } from "../js/ws-client.js";

class ScenarioLoader extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._scenarios = [];
    this._ships = [];
    this._selectedScenario = null;
    this._statusHandler = null;
    this._isLoading = false;
    this._activeScenario = null; // name of currently running scenario
    this._isCaptain = false;
  }

  connectedCallback() {
    this.render();
    this._setupInteraction();
    this._bindConnectionStatus();
    this._refreshAll();
  }

  disconnectedCallback() {
    if (this._statusHandler) {
      wsClient.removeEventListener("status_change", this._statusHandler);
      this._statusHandler = null;
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .list-container {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-bottom: 16px;
          max-height: 250px;
          overflow-y: auto;
        }

        .list-item {
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          transition: all 0.1s ease;
        }

        .list-item.clickable {
          cursor: pointer;
        }

        .list-item.clickable:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--border-active, #3a3a4a);
        }

        .list-item.selected {
          background: rgba(0, 170, 255, 0.1);
          border-color: var(--status-info, #00aaff);
        }

        .item-name {
          font-weight: 600;
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 4px;
        }

        .item-desc {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .station-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 4px;
          margin-top: 8px;
        }

        .station-btn {
          padding: 4px;
          font-size: 0.65rem;
          text-transform: uppercase;
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          background: var(--bg-dark, #111118);
          color: var(--text-secondary, #888899);
          cursor: pointer;
          text-align: center;
        }

        .station-btn:hover {
          background: var(--bg-hover, #22222e);
        }

        .station-btn.vacant {
          color: var(--status-nominal, #00ff88);
          border-color: rgba(0, 255, 136, 0.3);
        }
        
        .station-btn.vacant:hover {
          background: rgba(0, 255, 136, 0.1);
          border-color: var(--status-nominal, #00ff88);
        }

        .station-btn.occupied {
          color: var(--status-critical, #ff4444);
          border-color: rgba(255, 68, 68, 0.3);
          cursor: not-allowed;
          opacity: 0.7;
        }

        .buttons {
          display: flex;
          gap: 8px;
        }

        .btn {
          flex: 1;
          padding: 10px 16px;
          border-radius: 6px;
          font-size: 0.85rem;
          cursor: pointer;
          min-height: 44px;
        }

        .load-btn {
          background: var(--status-info, #00aaff);
          border: none;
          color: var(--bg-primary, #0a0a0f);
          font-weight: 600;
        }

        .load-btn:hover:not(:disabled) {
          filter: brightness(1.1);
        }

        .load-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .refresh-btn {
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-primary, #e0e0e0);
        }

        .refresh-btn:hover {
          background: var(--bg-hover, #22222e);
        }

        .status-box {
          margin-top: 12px;
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

        .loading, .empty-state {
          text-align: center;
          padding: 24px;
          color: var(--text-dim, #555566);
          font-style: italic;
        }

        .view-toggle {
          display: flex;
          gap: 8px;
          margin-bottom: 12px;
        }

        .view-btn {
          background: transparent;
          border: none;
          color: var(--text-secondary);
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          cursor: pointer;
          padding: 4px 8px;
          border-bottom: 2px solid transparent;
        }

        .view-btn.active {
          color: var(--status-info);
          border-bottom-color: var(--status-info);
        }
      </style>

      <div class="view-toggle" id="view-toggle" style="display: none;">
        <button class="view-btn active" data-view="lobby">Fleet Lobby</button>
        <button class="view-btn" data-view="missions">Missions</button>
      </div>

      <div class="section-title" id="main-title">Checking Server State...</div>
      
      <div class="list-container" id="main-list">
        <div class="loading">Connecting...</div>
      </div>

      <div class="buttons" id="action-buttons" style="display: none;">
        <button class="btn load-btn" id="load-btn" disabled>Load Selected</button>
        <button class="btn refresh-btn" id="refresh-btn">🔄</button>
      </div>

      <div class="status-box" id="status-box">Ready</div>
    `;
  }

  _setupInteraction() {
    this.shadowRoot.getElementById("load-btn").addEventListener("click", () => this._loadScenario());
    this.shadowRoot.getElementById("refresh-btn").addEventListener("click", () => this._refreshAll());
    
    // View toggler
    const toggleBtns = this.shadowRoot.querySelectorAll(".view-btn");
    toggleBtns.forEach(btn => {
      btn.addEventListener("click", (e) => {
        toggleBtns.forEach(b => b.classList.remove("active"));
        e.target.classList.add("active");
        const view = e.target.dataset.view;
        this._renderView(view);
      });
    });
  }

  _bindConnectionStatus() {
    this._statusHandler = (event) => {
      if (event.detail.status === "connected" && !this._isLoading) {
        this._refreshAll();
      }
    };
    wsClient.addEventListener("status_change", this._statusHandler);
  }

  _setStatus(message, variant = "") {
    const statusBox = this.shadowRoot.getElementById("status-box");
    if (!statusBox) return;
    statusBox.textContent = message || "";
    statusBox.className = `status-box ${variant}`;
  }

  async _refreshAll() {
    if (wsClient.status !== "connected") {
      this._setStatus("Connecting...", "warning");
      try {
        await wsClient.connect();
      } catch (err) {
        this._setStatus("Disconnected", "error");
        return;
      }
    }

    if (this._isLoading) return;
    this._isLoading = true;
    
    const list = this.shadowRoot.getElementById("main-list");
    list.innerHTML = '<div class="loading">Loading fleet status...</div>';

    try {
      // Check ships and detect active scenario
      const shipsResp = await wsClient.send("list_ships", {});
      this._ships = (shipsResp && shipsResp.success && shipsResp.data.ships) ? shipsResp.data.ships : [];

      // Check current session to determine if we are captain
      const statusResp = await wsClient.send("my_status", {});
      this._isCaptain = (
        statusResp && statusResp.success
        && statusResp.data && statusResp.data.station === "captain"
      );

      // Detect active scenario from server state
      const stateResp = await wsClient.send("get_state", {});
      this._activeScenario = (stateResp && stateResp.active_scenario) || null;

      // Check available missions
      const scResp = await wsClient.send("list_scenarios", {});
      this._scenarios = (scResp && scResp.ok !== false && scResp.scenarios) ? scResp.scenarios : [];

      // Fetch station status for each ship
      for (const ship of this._ships) {
        const sResp = await wsClient.send("station_status", { ship: ship.id });
        if (sResp && sResp.success) {
          ship.stations = sResp.data.stations;
        } else {
          ship.stations = [];
        }
      }

      this._isLoading = false;

      const hasShips = this._ships.length > 0;
      const viewToggle = this.shadowRoot.getElementById("view-toggle");

      if (hasShips) {
        viewToggle.style.display = "flex";
        // Default to lobby when ships exist
        const activeBtn = this.shadowRoot.querySelector(".view-btn.active");
        if (!activeBtn || activeBtn.dataset.view !== "lobby") {
          this.shadowRoot.querySelectorAll(".view-btn").forEach(b => b.classList.remove("active"));
          this.shadowRoot.querySelector(".view-btn[data-view='lobby']").classList.add("active");
        }
        this._renderView("lobby");
      } else {
        viewToggle.style.display = "none";
        this.shadowRoot.querySelectorAll(".view-btn").forEach(b => b.classList.remove("active"));
        this.shadowRoot.querySelector(".view-btn[data-view='missions']").classList.add("active");
        this._renderView("missions");
      }

    } catch (error) {
      this._isLoading = false;
      this._setStatus(`Error: ${error.message}`, "error");
    }
  }

  _renderView(view) {
    const list = this.shadowRoot.getElementById("main-list");
    const actions = this.shadowRoot.getElementById("action-buttons");
    const title = this.shadowRoot.getElementById("main-title");

    if (view === "missions") {
      const hasActiveShips = this._ships.length > 0;
      const loadBtn = this.shadowRoot.getElementById("load-btn");

      if (hasActiveShips) {
        // Mission is active — show status instead of full picker
        title.textContent = "Mission Active";
        actions.style.display = "flex";
        loadBtn.style.display = "";
        loadBtn.textContent = this._isCaptain ? "Load New Mission" : "Load Selected";

        const scenarioLabel = this._activeScenario || "Unknown Mission";
        list.innerHTML = `
          <div class="list-item selected">
            <div class="item-name">${scenarioLabel}</div>
            <div class="item-desc">
              ${this._ships.length} ship(s) in simulation.
              ${this._isCaptain ? "As captain, you may load a new mission." : "Only the captain can change the mission."}
            </div>
          </div>
        `;

        if (!this._isCaptain) {
          loadBtn.disabled = true;
          loadBtn.title = "Only the captain can load a new mission";
          return;
        }

        // Captain can still pick a new scenario below the active banner
        if (this._scenarios.length > 0) {
          list.innerHTML += `<div class="section-title" style="margin-top:12px">Replace With</div>`;
          list.innerHTML += this._scenarios.map(sc => {
            const isSelected = sc.id === this._selectedScenario;
            return `
              <div class="list-item clickable ${isSelected ? 'selected' : ''}" data-id="${sc.id}">
                <div class="item-name">${sc.name || sc.id}</div>
                <div class="item-desc">${sc.description || sc.mission_description || ''}</div>
              </div>
            `;
          }).join("");
        }

        loadBtn.disabled = !this._selectedScenario;
        list.querySelectorAll(".list-item.clickable").forEach(item => {
          item.addEventListener("click", () => {
            this._selectedScenario = item.dataset.id;
            this._renderView("missions");
          });
        });
        return;
      }

      // No active ships — normal scenario picker
      title.textContent = "Available Missions";
      actions.style.display = "flex";
      loadBtn.style.display = "";
      loadBtn.textContent = "Load Selected";

      if (this._scenarios.length === 0) {
        list.innerHTML = '<div class="empty-state">No missions found.</div>';
        return;
      }

      list.innerHTML = this._scenarios.map(sc => {
        const isSelected = sc.id === this._selectedScenario;
        return `
          <div class="list-item clickable ${isSelected ? 'selected' : ''}" data-id="${sc.id}">
            <div class="item-name">${sc.name || sc.id}</div>
            <div class="item-desc">${sc.description || sc.mission_description || ''}</div>
          </div>
        `;
      }).join("");

      loadBtn.disabled = !this._selectedScenario;
      list.querySelectorAll(".list-item").forEach(item => {
        item.addEventListener("click", () => {
          this._selectedScenario = item.dataset.id;
          this._renderView("missions");
        });
      });
    } else if (view === "lobby") {
      title.textContent = "Fleet Lobby - Join a Station";
      actions.style.display = "flex";
      this.shadowRoot.getElementById("load-btn").style.display = "none"; // Hide load btn in lobby

      if (this._ships.length === 0) {
        list.innerHTML = '<div class="empty-state">No active fleet out there.</div>';
        return;
      }

      list.innerHTML = this._ships.map(ship => {
        const stationsHtml = (ship.stations || []).map(st => {
          const isVacant = !st.claimed;
          const statusClass = isVacant ? "vacant" : "occupied";
          const display = isVacant ? "JOIN" : (st.player || "TAKEN");
          return `<button class="station-btn ${statusClass}" data-ship="${ship.id}" data-station="${st.station}" ${!isVacant ? 'disabled' : ''}>
            ${st.station}<br/><b>${display}</b>
          </button>`;
        }).join("");

        return `
          <div class="list-item">
            <div class="item-name">${ship.name || ship.id}</div>
            <div class="item-desc">${ship.class || 'Unknown Class'}</div>
            <div class="station-grid">
              ${stationsHtml}
            </div>
          </div>
        `;
      }).join("");

      list.querySelectorAll(".station-btn.vacant").forEach(btn => {
        btn.addEventListener("click", (e) => {
          this._joinStation(btn.dataset.ship, btn.dataset.station);
        });
      });
    }
  }

  async _joinStation(shipId, stationName) {
    this._setStatus(`Joining ${stationName} on ${shipId}...`, "info");
    try {
      // 1. Assign to ship
      const assignResp = await wsClient.send("assign_ship", { ship: shipId });
      if (!assignResp.success) throw new Error(assignResp.message);

      // 2. Claim station
      const claimResp = await wsClient.send("claim_station", { station: stationName, ship: shipId });
      if (!claimResp.success) throw new Error(claimResp.message);

      this._setStatus(`Joined ${stationName}!`, "success");
      
      // Dispatch an event so the rest of the GUI knows
      this.dispatchEvent(new CustomEvent("scenario-loaded", {
        detail: { assignedShip: shipId, station: stationName },
        bubbles: true
      }));

      // Collapse the loader panel
      const panel = this.closest('flaxos-panel');
      if (panel) panel.setAttribute('collapsed', '');
      
      this._refreshAll();
    } catch (err) {
      this._setStatus(`Failed to join: ${err.message}`, "error");
    }
  }

  async _loadScenario() {
    if (!this._selectedScenario) return;
    this._setStatus(`Loading ${this._selectedScenario}...`, "info");

    try {
      const response = await wsClient.send("load_scenario", { scenario: this._selectedScenario });

      // Check for permission denial (mission-active guard)
      if (response && response.ok === false) {
        const errMsg = response.error || "Unknown error";
        const isPermission = errMsg.toLowerCase().includes("captain") || errMsg.toLowerCase().includes("mission already");
        this._setStatus(errMsg, isPermission ? "warning" : "error");
        return;
      }

      if (response && response.ok !== false) {
        this._setStatus(`Loaded: ${this._selectedScenario}`, "success");

        this.dispatchEvent(new CustomEvent("scenario-loaded", {
          detail: response,
          bubbles: true,
        }));

        this._selectedScenario = null;
        this.shadowRoot.getElementById("load-btn").disabled = true;

        // Refresh to show the newly loaded fleet in the lobby
        this._refreshAll();
      } else {
        this._setStatus(`Failed: ${response?.error || 'Unknown'}`, "error");
      }
    } catch (error) {
      this._setStatus(`Error: ${error.message}`, "error");
    }
  }
}

customElements.define("scenario-loader", ScenarioLoader);
export { ScenarioLoader };
