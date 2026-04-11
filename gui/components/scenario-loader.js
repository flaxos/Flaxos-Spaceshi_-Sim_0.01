/**
 * Scenario Loader — Game Menu System
 *
 * Five states:
 *   TITLE          — Title screen with NEW GAME / JOIN GAME / QUICK PLAY
 *   MISSION_SELECT — Filterable grid of mission cards
 *   QUICK_PLAY     — Skirmish configurator
 *   LOBBY          — Fleet lobby: pick a ship + station, captain starts
 *   POST_MISSION   — Results overlay (NEXT / REPLAY / MENU)
 */

import { wsClient } from "../js/ws-client.js";

const MENU_STATE = {
  TITLE: "title",
  MISSION_SELECT: "mission_select",
  QUICK_PLAY: "quick_play",
  LOBBY: "lobby",
  POST_MISSION: "post_mission",
};

// Ship classes available for skirmish configuration
const SKIRMISH_SHIP_CLASSES = [
  "fighter", "corvette", "gunship", "frigate", "destroyer",
  "cruiser", "battleship", "carrier",
];

const SKIRMISH_MODES = [
  { id: "deathmatch", label: "DEATHMATCH", desc: "All vs all, last team standing" },
  { id: "team", label: "TEAM", desc: "Two teams, destroy all enemies" },
  { id: "defend", label: "DEFEND", desc: "Protect a station from waves" },
  { id: "escort", label: "ESCORT", desc: "Escort a freighter to safety" },
];

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
    // Skirmish configurator state
    this._skirmishMode = "deathmatch";
    this._skirmishPlayerShips = [{ class: "corvette" }];
    this._skirmishEnemyShips = [{ class: "frigate", count: 1 }];
    this._skirmishRange = 50;
    this._skirmishTimeLimit = null;
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
      case MENU_STATE.QUICK_PLAY:
        container.appendChild(this._buildQuickPlay());
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
          <button class="btn btn-accent btn-large" id="btn-quick-play">QUICK PLAY</button>
          <button class="btn btn-secondary btn-large" id="btn-join-game">JOIN GAME</button>
        </div>
        <div class="title-version">v0.01</div>
      </div>
    `;

    // Defer event binding until after DOM insertion
    requestAnimationFrame(() => {
      const newBtn = this.shadowRoot.getElementById("btn-new-game");
      const quickBtn = this.shadowRoot.getElementById("btn-quick-play");
      const joinBtn = this.shadowRoot.getElementById("btn-join-game");
      if (newBtn) newBtn.addEventListener("click", () => this._onNewGame());
      if (quickBtn) quickBtn.addEventListener("click", () => this._onQuickPlay());
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

  async _onQuickPlay() {
    await this._ensureConnected();
    this._setMenuState(MENU_STATE.QUICK_PLAY);
  }

  // ─── QUICK PLAY (Skirmish Configurator) ─────────────────────────

  _buildQuickPlay() {
    const el = document.createElement("div");
    el.className = "quick-play";

    // Back button
    const backBtn = document.createElement("button");
    backBtn.className = "btn btn-ghost btn-back";
    backBtn.textContent = "< BACK";
    backBtn.addEventListener("click", () => this._setMenuState(MENU_STATE.TITLE));
    el.appendChild(backBtn);

    const header = document.createElement("h2");
    header.className = "section-header";
    header.textContent = "QUICK PLAY";
    el.appendChild(header);

    // Mode selector
    const modeLabel = document.createElement("div");
    modeLabel.className = "qp-label";
    modeLabel.textContent = "MODE";
    el.appendChild(modeLabel);

    const modeBar = document.createElement("div");
    modeBar.className = "filter-bar";
    for (const m of SKIRMISH_MODES) {
      const btn = document.createElement("button");
      btn.className = `filter-btn ${this._skirmishMode === m.id ? "active" : ""}`;
      btn.textContent = m.label;
      btn.title = m.desc;
      btn.addEventListener("click", () => {
        this._skirmishMode = m.id;
        this._render();
      });
      modeBar.appendChild(btn);
    }
    el.appendChild(modeBar);

    // Player ships
    el.appendChild(this._buildShipListEditor("PLAYER SHIPS", this._skirmishPlayerShips, "player"));

    // Enemy ships
    el.appendChild(this._buildShipListEditor("ENEMY SHIPS", this._skirmishEnemyShips, "enemy"));

    // Start range slider
    const rangeSection = document.createElement("div");
    rangeSection.className = "qp-section";
    rangeSection.innerHTML = `
      <div class="qp-label">START RANGE: <span class="qp-range-val">${this._skirmishRange} km</span></div>
      <input type="range" class="qp-slider" min="10" max="200" step="5" value="${this._skirmishRange}">
    `;
    const slider = rangeSection.querySelector(".qp-slider");
    slider.addEventListener("input", (e) => {
      this._skirmishRange = parseInt(e.target.value);
      rangeSection.querySelector(".qp-range-val").textContent = `${this._skirmishRange} km`;
    });
    el.appendChild(rangeSection);

    // Time limit (optional)
    const timeSection = document.createElement("div");
    timeSection.className = "qp-section";
    timeSection.innerHTML = `
      <div class="qp-label">TIME LIMIT (optional)</div>
      <div class="qp-row">
        <input type="number" class="qp-input" min="60" max="3600" step="30"
               placeholder="seconds" value="${this._skirmishTimeLimit || ""}">
        <button class="btn btn-ghost btn-small qp-clear-time">CLEAR</button>
      </div>
    `;
    const timeInput = timeSection.querySelector(".qp-input");
    timeInput.addEventListener("change", (e) => {
      const val = parseInt(e.target.value);
      this._skirmishTimeLimit = val > 0 ? val : null;
    });
    timeSection.querySelector(".qp-clear-time").addEventListener("click", () => {
      this._skirmishTimeLimit = null;
      timeInput.value = "";
    });
    el.appendChild(timeSection);

    // Generate & Play button
    const launchBtn = document.createElement("button");
    launchBtn.className = "btn btn-primary btn-large qp-launch";
    launchBtn.textContent = "GENERATE & PLAY";
    launchBtn.addEventListener("click", () => this._generateAndPlay());
    el.appendChild(launchBtn);

    return el;
  }

  _buildShipListEditor(label, shipList, side) {
    const section = document.createElement("div");
    section.className = "qp-section";

    const header = document.createElement("div");
    header.className = "qp-label";
    header.textContent = label;
    section.appendChild(header);

    // Current ships list
    const list = document.createElement("div");
    list.className = "qp-ship-list";

    for (let i = 0; i < shipList.length; i++) {
      const entry = shipList[i];
      const row = document.createElement("div");
      row.className = "qp-ship-row";

      const classLabel = document.createElement("span");
      classLabel.className = "qp-ship-class";
      classLabel.textContent = entry.class.toUpperCase();
      row.appendChild(classLabel);

      if (side === "enemy" && entry.count > 1) {
        const countLabel = document.createElement("span");
        countLabel.className = "qp-ship-count";
        countLabel.textContent = `x${entry.count}`;
        row.appendChild(countLabel);
      }

      const removeBtn = document.createElement("button");
      removeBtn.className = "btn btn-ghost btn-small";
      removeBtn.textContent = "X";
      removeBtn.addEventListener("click", () => {
        shipList.splice(i, 1);
        this._render();
      });
      row.appendChild(removeBtn);

      list.appendChild(row);
    }
    section.appendChild(list);

    // Add ship controls
    const addRow = document.createElement("div");
    addRow.className = "qp-add-row";

    const classSelect = document.createElement("select");
    classSelect.className = "qp-select";
    for (const cls of SKIRMISH_SHIP_CLASSES) {
      const opt = document.createElement("option");
      opt.value = cls;
      opt.textContent = cls.toUpperCase();
      classSelect.appendChild(opt);
    }
    addRow.appendChild(classSelect);

    if (side === "enemy") {
      const countInput = document.createElement("input");
      countInput.type = "number";
      countInput.className = "qp-input qp-count-input";
      countInput.min = "1";
      countInput.max = "10";
      countInput.value = "1";
      countInput.placeholder = "#";
      addRow.appendChild(countInput);
    }

    const addBtn = document.createElement("button");
    addBtn.className = "btn btn-secondary btn-small";
    addBtn.textContent = "ADD";
    addBtn.addEventListener("click", () => {
      const cls = classSelect.value;
      if (side === "enemy") {
        const countInput = addRow.querySelector(".qp-count-input");
        const count = Math.max(1, Math.min(10, parseInt(countInput?.value) || 1));
        shipList.push({ class: cls, count });
      } else {
        shipList.push({ class: cls });
      }
      this._render();
    });
    addRow.appendChild(addBtn);

    section.appendChild(addRow);
    return section;
  }

  async _generateAndPlay() {
    const params = {
      cmd: "generate_skirmish",
      mode: this._skirmishMode,
      player_ships: this._skirmishPlayerShips,
      enemy_ships: this._skirmishEnemyShips,
      start_range_km: this._skirmishRange,
      randomize_positions: true,
    };

    if (this._skirmishTimeLimit) {
      params.time_limit_seconds = this._skirmishTimeLimit;
    }

    try {
      const response = await wsClient.send("generate_skirmish", params);

      if (response && response.ok === false) {
        console.error("Generate skirmish failed:", response.error);
        return;
      }

      if (response && response.ok !== false) {
        this._activeScenario = response.scenario_name || "Generated Skirmish";
        this.dispatchEvent(new CustomEvent("scenario-loaded", {
          detail: response,
          bubbles: true,
        }));
        await this._fetchAndRenderLobby();
      }
    } catch (error) {
      console.error("Error generating skirmish:", error.message);
    }
  }

  // ─── MISSION SELECT ─────────────────────────────���───────────────

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
        e.preventDefault();
        e.stopPropagation();
        if (this._launching) {
            console.warn("[scenario-loader] Already launching, ignoring click");
            return;
        }
        console.log("[scenario-loader] Launch button clicked for:", sc.id);
        this._launching = true;
        this._loadScenario(sc.id).finally(() => { 
            this._launching = false; 
            console.log("[scenario-loader] Launch sequence completed for:", sc.id);
        });
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
    // Guard against re-entry: the previous call may still be in-flight when
    // a status_change reconnect fires, causing a second full fetch cycle.
    if (this._isLoading) return;

    // Debounce: ignore calls within 2s of the last successful fetch —
    // prevents double-load when _loadScenario's call to this method
    // finishes right before a status_change event re-triggers it.
    const now = Date.now();
    if (this._lastLobbyFetch && (now - this._lastLobbyFetch) < 2000) return;

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

      // Fetch station status per ship (PARALLEL)
      await Promise.all(this._ships.map(async (ship) => {
        try {
          const sResp = await wsClient.send("station_status", { ship: ship.id });
          ship.stations = sResp?.success ? sResp.data.stations : [];
        } catch (e) {
          ship.stations = [];
        }
      }));
    } catch (e) {
      // leave ships empty
    }

    this._lastLobbyFetch = Date.now();
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
    console.log("[scenario-loader] Loading scenario:", scenarioId, "ws status:", wsClient.status);

    // Visual feedback — disable all launch buttons while loading
    const btns = this.shadowRoot.querySelectorAll(".btn-launch");
    btns.forEach(b => { b.textContent = "LOADING..."; b.disabled = true; });

    try {
      // Ensure WS is connected before sending
      if (wsClient.status !== "connected") {
        console.warn("[scenario-loader] WS not connected, attempting reconnect");
        try { await wsClient.connect(); } catch (e) { /* continue anyway */ }
      }

      const response = await wsClient.send("load_scenario", { scenario: scenarioId });
      console.log("[scenario-loader] Response:", JSON.stringify(response));

      if (response && response.ok === false) {
        console.error("Load scenario failed:", response.error);
        btns.forEach(b => { b.textContent = "LAUNCH"; b.disabled = false; });
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
      console.error("Error loading scenario:", error.message || error);
      const btns2 = this.shadowRoot.querySelectorAll(".btn-launch");
      btns2.forEach(b => { b.textContent = "LAUNCH"; b.disabled = false; });
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

      .btn-accent {
        background: rgba(170, 0, 255, 0.2);
        border-color: #aa44ff;
        color: #cc88ff;
      }
      .btn-accent:hover {
        background: rgba(170, 0, 255, 0.35);
        filter: brightness(1.1);
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

      /* ── Quick Play ──────────────────────────────────────────── */

      .quick-play {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .qp-label {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--text-secondary, #888899);
        margin: 8px 0 4px;
      }

      .qp-range-val {
        color: var(--status-info, #00aaff);
        font-weight: 700;
      }

      .qp-section {
        margin-bottom: 8px;
      }

      .qp-slider {
        width: 100%;
        accent-color: var(--status-info, #00aaff);
      }

      .qp-row {
        display: flex;
        gap: 6px;
        align-items: center;
      }

      .qp-input {
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        color: var(--text-primary, #e0e0e0);
        padding: 6px 8px;
        font-size: 0.75rem;
        font-family: inherit;
        width: 100px;
      }

      .qp-count-input {
        width: 50px;
      }

      .qp-select {
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        color: var(--text-primary, #e0e0e0);
        padding: 6px 8px;
        font-size: 0.75rem;
        font-family: inherit;
      }

      .qp-ship-list {
        display: flex;
        flex-direction: column;
        gap: 3px;
        margin-bottom: 6px;
      }

      .qp-ship-row {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 4px 8px;
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
      }

      .qp-ship-class {
        font-size: 0.75rem;
        font-weight: 700;
        color: var(--text-primary, #e0e0e0);
        flex: 1;
      }

      .qp-ship-count {
        font-size: 0.7rem;
        color: var(--status-info, #00aaff);
        font-weight: 700;
      }

      .qp-add-row {
        display: flex;
        gap: 6px;
        align-items: center;
      }

      .qp-launch {
        width: 100%;
        margin-top: 12px;
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
