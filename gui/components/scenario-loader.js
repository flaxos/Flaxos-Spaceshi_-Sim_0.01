/**
 * Scenario Loader Panel
 * List and load available scenarios
 */

import { wsClient } from "../js/ws-client.js";

class ScenarioLoader extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._scenarios = [];
    this._selectedScenario = null;
    this._currentScenario = null;
    this._statusHandler = null;
    // Debounce and loading state
    this._isLoadingScenarios = false;
    this._isLoadingScenario = false;
    this._lastRefreshTime = 0;
    this._refreshDebounceMs = 500;
  }

  connectedCallback() {
    this.render();
    this._setupInteraction();
    this._bindConnectionStatus();
    this._loadScenarios();
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

        .scenario-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-bottom: 16px;
          max-height: 200px;
          overflow-y: auto;
        }

        .scenario-item {
          padding: 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.1s ease;
        }

        .scenario-item:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--border-active, #3a3a4a);
        }

        .scenario-item.selected {
          background: rgba(0, 170, 255, 0.1);
          border-color: var(--status-info, #00aaff);
        }

        .scenario-item.current {
          border-color: var(--status-nominal, #00ff88);
        }

        .scenario-item.current::before {
          content: '▶ ';
          color: var(--status-nominal, #00ff88);
        }

        .scenario-name {
          font-weight: 600;
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 4px;
        }

        .scenario-desc {
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .scenario-error {
          color: var(--status-critical, #ff4444);
          font-style: italic;
        }

        .connection-hint {
          margin-bottom: 10px;
          padding: 8px 10px;
          border-radius: 6px;
          font-size: 0.75rem;
          background: rgba(255, 170, 0, 0.12);
          color: var(--status-warning, #ffaa00);
        }

        .connection-hint.connected {
          display: none;
        }

        .connection-hint.connecting {
          background: rgba(0, 170, 255, 0.12);
          color: var(--status-info, #00aaff);
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

        .status-box.info {
          color: var(--status-info, #00aaff);
        }

        .status-box.warning {
          color: var(--status-warning, #ffaa00);
        }

        .status-box.error {
          color: var(--status-critical, #ff4444);
        }

        .status-box.success {
          color: var(--status-nominal, #00ff88);
        }

        .loading {
          text-align: center;
          padding: 24px;
          color: var(--text-dim, #555566);
        }

        .empty-state {
          text-align: center;
          padding: 24px;
          color: var(--text-dim, #555566);
          font-style: italic;
        }

        .difficulty {
          display: inline-block;
          margin-right: 8px;
        }

        .difficulty-star {
          color: var(--status-warning, #ffaa00);
        }
      </style>

      <div class="section-title">Available Missions</div>
      <div class="connection-hint connected" id="connection-hint"></div>
      <div class="scenario-list" id="scenario-list">
        <div class="loading">Loading scenarios...</div>
      </div>

      <div class="buttons">
        <button class="btn load-btn" id="load-btn" disabled>Load Selected</button>
        <button class="btn refresh-btn" id="refresh-btn">🔄</button>
      </div>

      <div class="status-box" id="status-box">
        No scenario loaded
      </div>
    `;
  }

  _setupInteraction() {
    this.shadowRoot.getElementById("load-btn").addEventListener("click", () => {
      this._loadScenario();
    });

    this.shadowRoot.getElementById("refresh-btn").addEventListener("click", () => {
      this._loadScenarios();
    });
  }

  _bindConnectionStatus() {
    this._statusHandler = (event) => {
      this._updateConnectionHint(event.detail.status);
    };
    wsClient.addEventListener("status_change", this._statusHandler);
    this._updateConnectionHint(wsClient.status);
  }

  _updateConnectionHint(status = wsClient.status) {
    const hint = this.shadowRoot.getElementById("connection-hint");
    if (!hint) return;

    hint.classList.remove("connected", "connecting", "disconnected");
    if (status === "connected") {
      hint.classList.add("connected");
      hint.textContent = "";
      return;
    }

    if (status === "connecting") {
      hint.classList.add("connecting");
      hint.textContent = "Connecting to server…";
      return;
    }

    hint.classList.add("disconnected");
    hint.textContent = "Disconnected from server; can’t load scenarios yet.";
  }

  _setStatus(message, variant = "") {
    const statusBox = this.shadowRoot.getElementById("status-box");
    if (!statusBox) return;
    statusBox.textContent = message || "";
    statusBox.classList.remove("info", "warning", "error", "success");
    if (variant) {
      statusBox.classList.add(variant);
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }

  async _loadScenarios() {
    const list = this.shadowRoot.getElementById("scenario-list");
    const refreshBtn = this.shadowRoot.getElementById("refresh-btn");

    // Debounce: prevent rapid refresh clicks
    const now = Date.now();
    if (now - this._lastRefreshTime < this._refreshDebounceMs) {
      return;
    }
    this._lastRefreshTime = now;

    // Prevent concurrent scenario list requests
    if (this._isLoadingScenarios) {
      return;
    }

    if (wsClient.status !== "connected") {
      list.innerHTML = '<div class="empty-state">Disconnected from server.</div>';
      this._setStatus("Disconnected from server.", "warning");
      this._updateConnectionHint(wsClient.status);
      this._showMessage("Cannot load scenarios while disconnected.", "warning");
      try {
        await wsClient.connect();
      } catch (error) {
        this._showMessage(`Connection failed: ${error.message}`, "error");
      }
      if (wsClient.status !== "connected") {
        this._setStatus("Unable to load scenarios while disconnected.", "error");
        return;
      }
    }

    this._isLoadingScenarios = true;
    if (refreshBtn) refreshBtn.disabled = true;
    list.innerHTML = '<div class="loading">Loading scenarios...</div>';

    try {
      const response = await wsClient.send("list_scenarios", {});

      if (response && response.ok !== false && Array.isArray(response.scenarios)) {
        this._scenarios = response.scenarios;
        this._renderScenarios();
      } else {
        const errorMsg = response?.error || "No scenarios found";
        list.innerHTML = '<div class="empty-state">No scenarios found</div>';
        this._setStatus(`Failed to load scenarios: ${errorMsg}`, "error");
        this._showMessage(`Scenario list failed: ${errorMsg}`, "error");
      }
    } catch (error) {
      list.innerHTML = `<div class="empty-state">Failed to load scenarios: ${error.message}</div>`;
      this._setStatus(`Failed to load scenarios: ${error.message}`, "error");
      this._showMessage(`Scenario list failed: ${error.message}`, "error");
    } finally {
      this._isLoadingScenarios = false;
      if (refreshBtn) refreshBtn.disabled = false;
    }
  }

  _renderScenarios() {
    const list = this.shadowRoot.getElementById("scenario-list");

    if (this._scenarios.length === 0) {
      list.innerHTML = '<div class="empty-state">No scenarios available</div>';
      return;
    }

    list.innerHTML = this._scenarios.map(scenario => {
      const isSelected = scenario.id === this._selectedScenario;
      const isCurrent = scenario.id === this._currentScenario;
      const classes = [
        "scenario-item",
        isSelected ? "selected" : "",
        isCurrent ? "current" : ""
      ].filter(Boolean).join(" ");

      const difficulty = this._getDifficultyStars(scenario);

      return `
        <div class="${classes}" data-id="${scenario.id}">
          <div class="scenario-name">
            ${difficulty ? `<span class="difficulty">${difficulty}</span>` : ''}
            ${scenario.name || scenario.id}
          </div>
          <div class="scenario-desc ${scenario.error ? 'scenario-error' : ''}">
            ${scenario.error || scenario.description || scenario.mission_description || 'No description'}
          </div>
        </div>
      `;
    }).join("");

    // Add click handlers
    list.querySelectorAll(".scenario-item").forEach(item => {
      item.addEventListener("click", () => {
        this._selectScenario(item.dataset.id);
      });
    });
  }

  _getDifficultyStars(scenario) {
    // Infer difficulty from name or explicit property
    const name = (scenario.name || "").toLowerCase();
    let stars = 1;

    if (name.includes("tutorial") || name.includes("basic")) stars = 1;
    else if (name.includes("combat") || name.includes("intercept")) stars = 2;
    else if (name.includes("escort") || name.includes("defend")) stars = 3;
    else if (scenario.difficulty) stars = scenario.difficulty;

    return '<span class="difficulty-star">★</span>'.repeat(stars);
  }

  _selectScenario(id) {
    this._selectedScenario = id;
    this._renderScenarios();
    this._updateLoadButton();
  }

  _updateLoadButton() {
    const loadBtn = this.shadowRoot.getElementById("load-btn");
    loadBtn.disabled = !this._selectedScenario;
  }

  async _loadScenario() {
    if (!this._selectedScenario) return;

    // Prevent concurrent scenario loads
    if (this._isLoadingScenario) {
      return;
    }

    const loadBtn = this.shadowRoot.getElementById("load-btn");

    if (wsClient.status !== "connected") {
      this._setStatus("Disconnected from server.", "warning");
      this._updateConnectionHint(wsClient.status);
      this._showMessage("Cannot load scenario while disconnected.", "warning");
      try {
        await wsClient.connect();
      } catch (error) {
        this._showMessage(`Connection failed: ${error.message}`, "error");
      }
      if (wsClient.status !== "connected") {
        this._setStatus("Unable to load scenario while disconnected.", "error");
        return;
      }
    }

    this._isLoadingScenario = true;
    loadBtn.disabled = true;
    this._setStatus(`Loading ${this._selectedScenario}...`, "info");

    try {
      const response = await wsClient.send("load_scenario", {
        scenario: this._selectedScenario
      });

      if (response && response.ok !== false) {
        this._currentScenario = this._selectedScenario;

        // Build status message
        let statusMsg = `Loaded: ${this._selectedScenario} (${response.ships_loaded} ships)`;
        if (response.auto_assigned) {
          statusMsg += ` - Assigned to ${response.assigned_ship}`;
        }
        this._setStatus(statusMsg, "success");

        console.log("Scenario loaded:", {
          scenario: this._selectedScenario,
          shipsLoaded: response.ships_loaded,
          playerShipId: response.player_ship_id,
          autoAssigned: response.auto_assigned,
          assignedShip: response.assigned_ship,
          station: response.station
        });

        // Dispatch event for other components
        this.dispatchEvent(new CustomEvent("scenario-loaded", {
          detail: {
            scenario: this._selectedScenario,
            shipsLoaded: response.ships_loaded,
            playerShipId: response.player_ship_id,
            autoAssigned: response.auto_assigned,
            assignedShip: response.assigned_ship,
            station: response.station,
            mission: response.mission
          },
          bubbles: true
        }));

        this._renderScenarios();
      } else {
        const errorMsg = response?.error || 'Unknown error';
        this._setStatus(`Failed: ${errorMsg}`, "error");
        this._showMessage(`Scenario load failed: ${errorMsg}`, "error");
      }
    } catch (error) {
      this._setStatus(`Error: ${error.message}`, "error");
      this._showMessage(`Scenario load failed: ${error.message}`, "error");
    } finally {
      this._isLoadingScenario = false;
      loadBtn.disabled = false;
    }
  }

  /**
   * Get currently loaded scenario ID
   */
  getCurrentScenario() {
    return this._currentScenario;
  }
}

customElements.define("scenario-loader", ScenarioLoader);
export { ScenarioLoader };
