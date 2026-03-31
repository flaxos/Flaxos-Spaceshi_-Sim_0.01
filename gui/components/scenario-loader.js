/**
 * Scenario Loader — Game Menu System
 *
 * Four states:
 *   TITLE         — Title screen with NEW GAME / JOIN GAME
 *   MISSION_SELECT — Filterable grid of mission cards
 *   LOBBY         — Fleet lobby: pick a ship + station, captain starts
 *   POST_MISSION  — Results overlay (NEXT / REPLAY / MENU)
 */

import { wsClient } from "../js/ws-client.js";

const MENU_STATE = {
  TITLE: "title",
  MISSION_SELECT: "mission_select",
  LOBBY: "lobby",
  POST_MISSION: "post_mission",
};

// Difficulty ordering for sort
const DIFFICULTY_ORDER = {
  tutorial: 0,
  easy: 1,
  medium: 2,
  hard: 3,
  extreme: 4,
};

const DIFFICULTY_COLORS = {
  tutorial: "#00aaff",
  easy: "#00ff88",
  medium: "#ffaa00",
  hard: "#ff6644",
  extreme: "#ff2222",
};

const CATEGORY_LABELS = {
  tutorial: "TUTORIAL",
  combat: "COMBAT",
  stealth: "STEALTH",
  fleet: "FLEET",
  campaign: "CAMPAIGN",
};

class ScenarioLoader extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._scenarios = [];
    this._ships = [];
    this._selectedScenario = null;
    this._statusHandler = null;
    this._isLoading = false;
    this._activeScenario = null;
    this._isCaptain = false;
    this._menuState = MENU_STATE.TITLE;
    this._categoryFilter = "all";
    this._expandedCard = null; // scenario id with expanded briefing
  }

  connectedCallback() {
    this._render();
    this._bindConnectionStatus();
  }

  disconnectedCallback() {
    if (this._statusHandler) {
      wsClient.removeEventListener("status_change", this._statusHandler);
      this._statusHandler = null;
    }
  }

  _bindConnectionStatus() {
    this._statusHandler = (event) => {
      if (event.detail.status === "connected" && !this._isLoading) {
        // If we are on the lobby screen, refresh automatically
        if (this._menuState === MENU_STATE.LOBBY) {
          this._fetchAndRenderLobby();
        }
      }
    };
    wsClient.addEventListener("status_change", this._statusHandler);
  }

  _setMenuState(state) {
    this._menuState = state;
    this._render();
  }

  // ─── Rendering ──────────────────────────────────────────────────

  _render() {
    const root = this.shadowRoot;
    root.innerHTML = `<style>${this._styles()}</style>`;
    const container = document.createElement("div");
    container.className = "menu-root";

    switch (this._menuState) {
      case MENU_STATE.TITLE:
        container.appendChild(this._buildTitle());
        break;
      case MENU_STATE.MISSION_SELECT:
        container.appendChild(this._buildMissionSelect());
        break;
      case MENU_STATE.LOBBY:
        container.appendChild(this._buildLobby());
        break;
      case MENU_STATE.POST_MISSION:
        container.appendChild(this._buildPostMission());
        break;
    }

    root.appendChild(container);
  }

  // ─── TITLE SCREEN ───────────────────────────────────────────────

  _buildTitle() {
    const el = document.createElement("div");
    el.className = "title-screen";
    el.innerHTML = `
      <div class="title-content">
        <div class="title-glow"></div>
        <h1 class="game-title">FLAXOS SPACESHIP SIM</h1>
        <p class="game-subtitle">Hard Sci-Fi Tactical Bridge Simulator</p>
        <div class="title-buttons">
          <button class="btn btn-primary btn-large" id="btn-new-game">NEW GAME</button>
          <button class="btn btn-secondary btn-large" id="btn-join-game">JOIN GAME</button>
        </div>
        <div class="title-version">v0.01</div>
      </div>
    `;

    // Defer event binding until after DOM insertion
    requestAnimationFrame(() => {
      const newBtn = this.shadowRoot.getElementById("btn-new-game");
      const joinBtn = this.shadowRoot.getElementById("btn-join-game");
      if (newBtn) newBtn.addEventListener("click", () => this._onNewGame());
      if (joinBtn) joinBtn.addEventListener("click", () => this._onJoinGame());
    });

    return el;
  }

  async _onNewGame() {
    await this._ensureConnected();
    await this._fetchScenarios();
    this._setMenuState(MENU_STATE.MISSION_SELECT);
  }

  async _onJoinGame() {
    await this._ensureConnected();
    await this._fetchAndRenderLobby();
  }

  // ─── MISSION SELECT ─────────────────────────────────────────────

  _buildMissionSelect() {
    const el = document.createElement("div");
    el.className = "mission-select";

    // Back button
    const backBtn = document.createElement("button");
    backBtn.className = "btn btn-ghost btn-back";
    backBtn.textContent = "< BACK";
    backBtn.addEventListener("click", () => this._setMenuState(MENU_STATE.TITLE));
    el.appendChild(backBtn);

    // Header
    const header = document.createElement("h2");
    header.className = "section-header";
    header.textContent = "SELECT MISSION";
    el.appendChild(header);

    // Category filter tabs
    const categories = ["all", "tutorial", "combat", "stealth", "fleet", "campaign"];
    const filterBar = document.createElement("div");
    filterBar.className = "filter-bar";

    for (const cat of categories) {
      const btn = document.createElement("button");
      btn.className = `filter-btn ${this._categoryFilter === cat ? "active" : ""}`;
      btn.textContent = cat === "all" ? "ALL" : CATEGORY_LABELS[cat] || cat.toUpperCase();
      btn.addEventListener("click", () => {
        this._categoryFilter = cat;
        this._render();
      });
      filterBar.appendChild(btn);
    }
    el.appendChild(filterBar);

    // Sort scenarios by difficulty
    const sorted = [...this._scenarios].sort((a, b) => {
      const da = DIFFICULTY_ORDER[a.difficulty] ?? 99;
      const db = DIFFICULTY_ORDER[b.difficulty] ?? 99;
      return da - db;
    });

    // Filter by category
    const filtered = sorted.filter((sc) => {
      if (this._categoryFilter === "all") return true;
      return sc.category === this._categoryFilter;
    });

    // Mission cards grid
    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = this._scenarios.length === 0
        ? "No missions found. Check server connection."
        : "No missions in this category.";
      el.appendChild(empty);
    } else {
      const grid = document.createElement("div");
      grid.className = "mission-grid";

      for (const sc of filtered) {
        grid.appendChild(this._buildMissionCard(sc));
      }
      el.appendChild(grid);
    }

    return el;
  }

  _buildMissionCard(sc) {
    const card = document.createElement("div");
    const isSelected = sc.id === this._selectedScenario;
    const isExpanded = sc.id === this._expandedCard;
    card.className = `mission-card ${isSelected ? "selected" : ""} ${isExpanded ? "expanded" : ""}`;

    const diffColor = DIFFICULTY_COLORS[sc.difficulty] || "#888";
    const diffLabel = (sc.difficulty || "unknown").toUpperCase();
    const catLabel = CATEGORY_LABELS[sc.category] || (sc.category || "").toUpperCase();
    const playerLabel = sc.player_count ? `${sc.player_count} PLAYER${sc.player_count === "1" ? "" : "S"}` : "";

    card.innerHTML = `
      <div class="card-header">
        <span class="card-name">${sc.name || sc.id}</span>
        <div class="card-tags">
          <span class="tag tag-difficulty" style="--tag-color: ${diffColor}">${diffLabel}</span>
          ${catLabel ? `<span class="tag tag-category">${catLabel}</span>` : ""}
          ${playerLabel ? `<span class="tag tag-players">${playerLabel}</span>` : ""}
        </div>
      </div>
      <div class="card-desc">${sc.description || sc.mission_description || ""}</div>
      ${isExpanded && sc.briefing ? `
        <div class="card-briefing">
          <div class="briefing-label">MISSION BRIEFING</div>
          <div class="briefing-text">${this._escapeHtml(sc.briefing)}</div>
        </div>
      ` : ""}
      <div class="card-actions">
        ${sc.briefing ? `<button class="btn btn-ghost btn-small btn-expand">${isExpanded ? "HIDE BRIEFING" : "BRIEFING"}</button>` : ""}
        <button class="btn btn-primary btn-small btn-launch">LAUNCH</button>
      </div>
    `;

    // Click card body to select
    card.addEventListener("click", (e) => {
      if (e.target.closest(".btn-launch") || e.target.closest(".btn-expand")) return;
      this._selectedScenario = sc.id;
      this._render();
    });

    // Expand briefing
    const expandBtn = card.querySelector(".btn-expand");
    if (expandBtn) {
      expandBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this._expandedCard = this._expandedCard === sc.id ? null : sc.id;
        this._render();
      });
    }

    // Launch button
    const launchBtn = card.querySelector(".btn-launch");
    if (launchBtn) {
      launchBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this._loadScenario(sc.id);
      });
    }

    return card;
  }

  // ─── FLEET LOBBY ────────────────────────────────────────────────

  _buildLobby() {
    const el = document.createElement("div");
    el.className = "lobby-view";

    // Back button
    const backBtn = document.createElement("button");
    backBtn.className = "btn btn-ghost btn-back";
    backBtn.textContent = "< BACK";
    backBtn.addEventListener("click", () => this._setMenuState(MENU_STATE.TITLE));
    el.appendChild(backBtn);

    const header = document.createElement("h2");
    header.className = "section-header";
    header.textContent = "FLEET LOBBY";
    el.appendChild(header);

    if (this._activeScenario) {
      const scenarioTag = document.createElement("div");
      scenarioTag.className = "lobby-scenario-name";
      scenarioTag.textContent = `Mission: ${this._activeScenario}`;
      el.appendChild(scenarioTag);
    }

    if (this._ships.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No active fleet. Load a mission first.";

      const loadBtn = document.createElement("button");
      loadBtn.className = "btn btn-primary";
      loadBtn.textContent = "SELECT MISSION";
      loadBtn.addEventListener("click", () => this._onNewGame());

      el.appendChild(empty);
      el.appendChild(loadBtn);
      return el;
    }

    // Ship cards
    const shipGrid = document.createElement("div");
    shipGrid.className = "ship-grid";

    for (const ship of this._ships) {
      shipGrid.appendChild(this._buildShipCard(ship));
    }
    el.appendChild(shipGrid);

    // Captain start button
    if (this._isCaptain) {
      const startBtn = document.createElement("button");
      startBtn.className = "btn btn-primary btn-large start-mission-btn";
      startBtn.textContent = "START MISSION";
      startBtn.addEventListener("click", () => {
        // Collapse the loader panel and dispatch event
        this.dispatchEvent(new CustomEvent("scenario-loaded", {
          detail: { started: true },
          bubbles: true,
        }));
        const panel = this.closest("flaxos-panel");
        if (panel) panel.setAttribute("collapsed", "");
      });
      el.appendChild(startBtn);
    }

    // Refresh button
    const refreshBtn = document.createElement("button");
    refreshBtn.className = "btn btn-ghost btn-small refresh-btn";
    refreshBtn.textContent = "REFRESH";
    refreshBtn.addEventListener("click", () => this._fetchAndRenderLobby());
    el.appendChild(refreshBtn);

    return el;
  }

  _buildShipCard(ship) {
    const card = document.createElement("div");
    card.className = "ship-card";

    const stations = ship.stations || [];

    const stationDots = stations.map((st) => {
      const isVacant = !st.claimed;
      const cls = isVacant ? "vacant" : "occupied";
      const label = isVacant ? "JOIN" : (st.player || "TAKEN");
      return `<button class="station-slot ${cls}" data-ship="${ship.id}" data-station="${st.station}" ${!isVacant ? "disabled" : ""}>
        <span class="station-name">${st.station}</span>
        <span class="station-status">${label}</span>
      </button>`;
    }).join("");

    card.innerHTML = `
      <div class="ship-card-header">
        <span class="ship-name">${ship.name || ship.id}</span>
        <span class="ship-class">${ship.class || "Unknown"}</span>
        ${ship.faction ? `<span class="ship-faction">${ship.faction.toUpperCase()}</span>` : ""}
      </div>
      <div class="station-grid">${stationDots}</div>
    `;

    // Bind vacant station clicks
    requestAnimationFrame(() => {
      card.querySelectorAll(".station-slot.vacant").forEach((btn) => {
        btn.addEventListener("click", () => {
          this._joinStation(btn.dataset.ship, btn.dataset.station);
        });
      });
    });

    return card;
  }

  // ─── POST-MISSION ───────────────────────────────────────────────

  _buildPostMission() {
    const el = document.createElement("div");
    el.className = "post-mission";
    el.innerHTML = `
      <h2 class="section-header">MISSION COMPLETE</h2>
      <div class="post-buttons">
        <button class="btn btn-primary" id="btn-next-mission">NEXT MISSION</button>
        <button class="btn btn-secondary" id="btn-replay">REPLAY</button>
        <button class="btn btn-ghost" id="btn-back-menu">BACK TO MENU</button>
      </div>
    `;

    requestAnimationFrame(() => {
      const nextBtn = this.shadowRoot.getElementById("btn-next-mission");
      const replayBtn = this.shadowRoot.getElementById("btn-replay");
      const menuBtn = this.shadowRoot.getElementById("btn-back-menu");

      if (nextBtn) nextBtn.addEventListener("click", () => {
        // Dispatch event for next mission (handled by mission-objectives or main)
        this.dispatchEvent(new CustomEvent("next-mission", { bubbles: true }));
      });
      if (replayBtn) replayBtn.addEventListener("click", () => {
        if (this._activeScenario) this._loadScenario(this._activeScenario);
      });
      if (menuBtn) menuBtn.addEventListener("click", () => {
        this._setMenuState(MENU_STATE.TITLE);
      });
    });

    return el;
  }

  /** Show post-mission overlay. Called externally when mission ends. */
  showPostMission() {
    this._setMenuState(MENU_STATE.POST_MISSION);
  }

  // ─── Data Fetching ──────────────────────────────────────────────

  async _ensureConnected() {
    if (wsClient.status !== "connected") {
      try {
        await wsClient.connect();
      } catch (err) {
        // will proceed disconnected; individual calls will fail
      }
    }
  }

  async _fetchScenarios() {
    try {
      const resp = await wsClient.send("list_scenarios", {});
      this._scenarios = (resp && resp.ok !== false && resp.scenarios) ? resp.scenarios : [];
    } catch (e) {
      this._scenarios = [];
    }
  }

  async _fetchAndRenderLobby() {
    this._isLoading = true;
    await this._ensureConnected();

    try {
      // Fetch ships
      const shipsResp = await wsClient.send("list_ships", {});
      this._ships = (shipsResp && shipsResp.success && shipsResp.data.ships) ? shipsResp.data.ships : [];

      // Check captain status
      const statusResp = await wsClient.send("my_status", {});
      this._isCaptain = statusResp?.success && statusResp?.data?.station === "captain";

      // Detect active scenario
      const stateResp = await wsClient.send("get_state", {});
      this._activeScenario = stateResp?.active_scenario || null;

      // Fetch station status per ship
      for (const ship of this._ships) {
        const sResp = await wsClient.send("station_status", { ship: ship.id });
        ship.stations = sResp?.success ? sResp.data.stations : [];
      }
    } catch (e) {
      // leave ships empty
    }

    this._isLoading = false;
    this._setMenuState(MENU_STATE.LOBBY);
  }

  // ─── Actions ────────────────────────────────────────────────────

  async _joinStation(shipId, stationName) {
    try {
      const assignResp = await wsClient.send("assign_ship", { ship: shipId });
      if (!assignResp.success) throw new Error(assignResp.message);

      const claimResp = await wsClient.send("claim_station", { station: stationName, ship: shipId });
      if (!claimResp.success) throw new Error(claimResp.message);

      this.dispatchEvent(new CustomEvent("scenario-loaded", {
        detail: { assignedShip: shipId, station: stationName },
        bubbles: true,
      }));

      const panel = this.closest("flaxos-panel");
      if (panel) panel.setAttribute("collapsed", "");

      this._fetchAndRenderLobby();
    } catch (err) {
      // Re-render lobby with error state would go here
      console.error("Failed to join station:", err.message);
    }
  }

  async _loadScenario(scenarioId) {
    if (!scenarioId) return;

    try {
      const response = await wsClient.send("load_scenario", { scenario: scenarioId });

      if (response && response.ok === false) {
        console.error("Load scenario failed:", response.error);
        return;
      }

      if (response && response.ok !== false) {
        this._activeScenario = scenarioId;
        this._selectedScenario = null;
        this._expandedCard = null;

        this.dispatchEvent(new CustomEvent("scenario-loaded", {
          detail: response,
          bubbles: true,
        }));

        // Transition to lobby after loading
        await this._fetchAndRenderLobby();
      }
    } catch (error) {
      console.error("Error loading scenario:", error.message);
    }
  }

  // ─── Utilities ──────────────────────────────────────────────────

  _escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ─── Styles ─────────────────────────────────────────────────────

  _styles() {
    return `
      :host {
        display: block;
        font-family: var(--font-sans, "Inter", sans-serif);
        color: var(--text-primary, #e0e0e0);
      }

      .menu-root {
        padding: 16px;
      }

      /* ── Title Screen ──────────────────────────────────────── */

      .title-screen {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 350px;
        text-align: center;
        position: relative;
      }

      .title-content {
        position: relative;
        z-index: 1;
      }

      .title-glow {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(0, 170, 255, 0.08) 0%, transparent 70%);
        pointer-events: none;
        z-index: 0;
      }

      .game-title {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: 4px;
        color: #ffffff;
        margin: 0 0 8px;
        text-shadow: 0 0 40px rgba(0, 170, 255, 0.3);
      }

      .game-subtitle {
        font-size: 0.8rem;
        color: var(--text-secondary, #888899);
        letter-spacing: 1px;
        text-transform: uppercase;
        margin: 0 0 32px;
      }

      .title-buttons {
        display: flex;
        flex-direction: column;
        gap: 12px;
        width: 220px;
        margin: 0 auto;
      }

      .title-version {
        margin-top: 24px;
        font-size: 0.65rem;
        color: var(--text-dim, #555566);
        letter-spacing: 1px;
      }

      /* ── Buttons ───────────────────────────────────────────── */

      .btn {
        padding: 10px 18px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        cursor: pointer;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        transition: all 0.15s ease;
        border: 1px solid transparent;
        font-family: inherit;
        min-height: 40px;
      }

      .btn-large {
        padding: 14px 24px;
        font-size: 0.9rem;
        min-height: 48px;
      }

      .btn-small {
        padding: 6px 12px;
        font-size: 0.7rem;
        min-height: 30px;
      }

      .btn-primary {
        background: var(--status-info, #00aaff);
        border-color: var(--status-info, #00aaff);
        color: var(--bg-primary, #0a0a0f);
      }
      .btn-primary:hover {
        filter: brightness(1.15);
      }

      .btn-secondary {
        background: var(--bg-input, #1a1a24);
        border-color: var(--border-default, #2a2a3a);
        color: var(--text-primary, #e0e0e0);
      }
      .btn-secondary:hover {
        background: var(--bg-hover, #22222e);
        border-color: var(--border-active, #3a3a4a);
      }

      .btn-ghost {
        background: transparent;
        border-color: transparent;
        color: var(--text-secondary, #888899);
      }
      .btn-ghost:hover {
        color: var(--text-primary, #e0e0e0);
        background: rgba(255, 255, 255, 0.05);
      }

      .btn-back {
        margin-bottom: 12px;
        padding: 4px 8px;
        font-size: 0.7rem;
      }

      .btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }

      /* ── Section Header ────────────────────────────────────── */

      .section-header {
        font-size: 0.9rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: var(--text-primary, #e0e0e0);
        margin: 0 0 16px;
      }

      /* ── Filter Bar ────────────────────────────────────────── */

      .filter-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-bottom: 16px;
      }

      .filter-btn {
        padding: 4px 10px;
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        background: transparent;
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        color: var(--text-secondary, #888899);
        cursor: pointer;
        transition: all 0.1s ease;
        font-family: inherit;
      }

      .filter-btn:hover {
        background: var(--bg-hover, #22222e);
        border-color: var(--border-active, #3a3a4a);
      }

      .filter-btn.active {
        background: rgba(0, 170, 255, 0.15);
        border-color: var(--status-info, #00aaff);
        color: var(--status-info, #00aaff);
      }

      /* ── Mission Grid ──────────────────────────────────────── */

      .mission-grid {
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-height: 500px;
        overflow-y: auto;
      }

      .mission-card {
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 8px;
        padding: 12px;
        cursor: pointer;
        transition: all 0.1s ease;
      }

      .mission-card:hover {
        background: var(--bg-hover, #22222e);
        border-color: var(--border-active, #3a3a4a);
      }

      .mission-card.selected {
        background: rgba(0, 170, 255, 0.08);
        border-color: var(--status-info, #00aaff);
      }

      .card-header {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 6px;
      }

      .card-name {
        font-weight: 700;
        font-size: 0.85rem;
        color: var(--text-primary, #e0e0e0);
      }

      .card-tags {
        display: flex;
        gap: 4px;
        flex-wrap: wrap;
        margin-left: auto;
      }

      .tag {
        padding: 2px 6px;
        font-size: 0.55rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-radius: 3px;
        border: 1px solid;
      }

      .tag-difficulty {
        color: var(--tag-color, #888);
        border-color: var(--tag-color, #888);
        background: color-mix(in srgb, var(--tag-color, #888) 10%, transparent);
      }

      .tag-category {
        color: var(--text-secondary, #888899);
        border-color: var(--border-default, #2a2a3a);
        background: rgba(255, 255, 255, 0.03);
      }

      .tag-players {
        color: var(--status-info, #00aaff);
        border-color: rgba(0, 170, 255, 0.3);
        background: rgba(0, 170, 255, 0.05);
      }

      .card-desc {
        font-size: 0.75rem;
        color: var(--text-secondary, #888899);
        line-height: 1.4;
        margin-bottom: 8px;
      }

      .card-briefing {
        margin: 8px 0;
        padding: 10px;
        background: var(--bg-dark, #111118);
        border: 1px solid var(--border-default, #2a2a3a);
        border-left: 3px solid var(--status-info, #00aaff);
        border-radius: 4px;
        max-height: 200px;
        overflow-y: auto;
      }

      .briefing-label {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--status-info, #00aaff);
        margin-bottom: 6px;
      }

      .briefing-text {
        font-size: 0.72rem;
        line-height: 1.5;
        color: var(--text-primary, #e0e0e0);
        white-space: pre-line;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
      }

      .card-actions {
        display: flex;
        justify-content: flex-end;
        gap: 6px;
        margin-top: 4px;
      }

      /* ── Lobby ─────────────────────────────────────────────── */

      .lobby-view {
        display: flex;
        flex-direction: column;
      }

      .lobby-scenario-name {
        font-size: 0.75rem;
        color: var(--status-info, #00aaff);
        margin-bottom: 12px;
        font-weight: 600;
      }

      .ship-grid {
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin-bottom: 16px;
      }

      .ship-card {
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 8px;
        padding: 12px;
      }

      .ship-card-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
      }

      .ship-name {
        font-weight: 700;
        font-size: 0.85rem;
        color: var(--text-primary, #e0e0e0);
      }

      .ship-class {
        font-size: 0.7rem;
        color: var(--text-secondary, #888899);
        text-transform: uppercase;
      }

      .ship-faction {
        font-size: 0.6rem;
        color: var(--text-dim, #555566);
        margin-left: auto;
        letter-spacing: 0.5px;
      }

      .station-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
        gap: 4px;
      }

      .station-slot {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 6px 4px;
        border-radius: 4px;
        border: 1px solid var(--border-default, #2a2a3a);
        background: var(--bg-dark, #111118);
        cursor: pointer;
        transition: all 0.1s ease;
        font-family: inherit;
      }

      .station-slot .station-name {
        font-size: 0.6rem;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        color: var(--text-secondary, #888899);
      }

      .station-slot .station-status {
        font-size: 0.6rem;
        font-weight: 700;
      }

      .station-slot.vacant {
        border-color: rgba(0, 255, 136, 0.3);
      }
      .station-slot.vacant .station-status {
        color: var(--status-nominal, #00ff88);
      }
      .station-slot.vacant:hover {
        background: rgba(0, 255, 136, 0.08);
        border-color: var(--status-nominal, #00ff88);
      }

      .station-slot.occupied {
        cursor: not-allowed;
        opacity: 0.6;
        border-color: rgba(255, 68, 68, 0.3);
      }
      .station-slot.occupied .station-status {
        color: var(--status-critical, #ff4444);
      }

      .start-mission-btn {
        width: 100%;
        margin-bottom: 8px;
      }

      .refresh-btn {
        align-self: flex-end;
      }

      /* ── Post-Mission ──────────────────────────────────────── */

      .post-mission {
        text-align: center;
        padding: 24px 0;
      }

      .post-buttons {
        display: flex;
        flex-direction: column;
        gap: 10px;
        width: 200px;
        margin: 16px auto 0;
      }

      /* ── Empty State ───────────────────────────────────────── */

      .empty-state {
        text-align: center;
        padding: 32px 16px;
        color: var(--text-dim, #555566);
        font-size: 0.8rem;
        font-style: italic;
      }

      /* ── Scrollbar ─────────────────────────────────────────── */

      ::-webkit-scrollbar {
        width: 4px;
      }
      ::-webkit-scrollbar-track {
        background: transparent;
      }
      ::-webkit-scrollbar-thumb {
        background: var(--border-default, #2a2a3a);
        border-radius: 2px;
      }
    `;
  }
}

customElements.define("scenario-loader", ScenarioLoader);
export { ScenarioLoader };
