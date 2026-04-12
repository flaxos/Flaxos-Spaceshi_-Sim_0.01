<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";

  const dispatch = createEventDispatcher<{
    "scenario-loaded": { ship_id?: string; station?: string; assignedShip?: string; started?: boolean };
    "next-mission": Record<string, never>;
  }>();

  type MenuState = "title" | "mission_select" | "quick_play" | "lobby" | "post_mission";

  interface Scenario {
    id: string;
    name?: string;
    description?: string;
    mission_description?: string;
    difficulty?: string;
    category?: string;
    briefing?: string;
    player_count?: string | number;
  }

  interface ShipStation {
    station: string;
    claimed: boolean;
    player?: string;
  }

  interface LobbyShip {
    id: string;
    name?: string;
    class?: string;
    faction?: string;
    stations?: ShipStation[];
  }

  interface SkirmishShip { class: string; count?: number; }

  // ── State ─────────────────────────────────────────────────────────
  let menuState: MenuState = "title";
  let scenarios: Scenario[] = [];
  let ships: LobbyShip[] = [];
  let selectedScenario: string | null = null;
  let expandedCard: string | null = null;
  let activeScenario: string | null = null;
  let isCaptain = false;
  let isLoading = false;
  let categoryFilter = "all";
  let errorMsg = "";

  // Skirmish configurator
  let skirmishMode = "deathmatch";
  let skirmishPlayerShips: SkirmishShip[] = [{ class: "corvette" }];
  let skirmishEnemyShips: SkirmishShip[] = [{ class: "frigate", count: 1 }];
  let skirmishRange = 50;
  let skirmishTimeLimit: number | null = null;
  let skirmishNewPlayerClass = "corvette";
  let skirmishNewEnemyClass = "frigate";
  let skirmishNewEnemyCount = 1;

  const SKIRMISH_SHIP_CLASSES = ["fighter", "corvette", "gunship", "frigate", "destroyer", "cruiser", "battleship", "carrier"];
  const SKIRMISH_MODES = [
    { id: "deathmatch", label: "DEATHMATCH", desc: "All vs all, last team standing" },
    { id: "team",       label: "TEAM",       desc: "Two teams, destroy all enemies" },
    { id: "defend",     label: "DEFEND",     desc: "Protect a station from waves" },
    { id: "escort",     label: "ESCORT",     desc: "Escort a freighter to safety" },
  ];
  const DIFFICULTY_ORDER: Record<string, number> = { tutorial: 0, easy: 1, medium: 2, hard: 3, extreme: 4 };
  const DIFFICULTY_COLORS: Record<string, string> = {
    tutorial: "#00aaff", easy: "#00ff88", medium: "#ffaa00", hard: "#ff6644", extreme: "#ff2222",
  };
  const CATEGORY_LABELS: Record<string, string> = {
    tutorial: "TUTORIAL", combat: "COMBAT", stealth: "STEALTH", fleet: "FLEET", campaign: "CAMPAIGN",
  };
  const CATEGORIES = ["all", "tutorial", "combat", "stealth", "fleet", "campaign"];

  // ── Derived ───────────────────────────────────────────────────────
  $: filteredScenarios = [...scenarios]
    .sort((a, b) => (DIFFICULTY_ORDER[a.difficulty ?? ""] ?? 99) - (DIFFICULTY_ORDER[b.difficulty ?? ""] ?? 99))
    .filter(sc => categoryFilter === "all" || sc.category === categoryFilter);

  // ── Lifecycle ─────────────────────────────────────────────────────
  let statusHandler: ((e: Event) => void) | null = null;

  onMount(() => {
    statusHandler = (e: Event) => {
      const detail = (e as CustomEvent<{ status: string }>).detail;
      if (detail.status === "connected" && menuState === "lobby") {
        fetchAndRenderLobby();
      }
    };
    wsClient.addEventListener("status_change", statusHandler);
  });

  onDestroy(() => {
    if (statusHandler) wsClient.removeEventListener("status_change", statusHandler);
  });

  // ── Navigation ────────────────────────────────────────────────────
  async function goNewGame() {
    errorMsg = "";
    await fetchScenarios();
    menuState = "mission_select";
  }

  async function goJoinGame() {
    errorMsg = "";
    await fetchAndRenderLobby();
  }

  function goQuickPlay() {
    errorMsg = "";
    menuState = "quick_play";
  }

  // ── Data Fetching ─────────────────────────────────────────────────
  async function fetchScenarios() {
    try {
      const resp = await wsClient.send("list_scenarios", {}) as { ok?: boolean; scenarios?: Scenario[] };
      scenarios = (resp?.ok !== false && resp?.scenarios) ? resp.scenarios : [];
    } catch { scenarios = []; }
  }

  let lastLobbyFetch = 0;

  async function fetchAndRenderLobby() {
    if (isLoading) return;
    const now = Date.now();
    if (now - lastLobbyFetch < 2000) return;

    isLoading = true;
    errorMsg = "";

    try {
      if (wsClient.status !== "connected") {
        try { await wsClient.connect(); } catch { /* continue */ }
      }

      const shipsResp = await wsClient.send("list_ships", {}) as { success?: boolean; data?: { ships: LobbyShip[] } };
      ships = (shipsResp?.success && shipsResp?.data?.ships) ? shipsResp.data.ships : [];

      const statusResp = await wsClient.send("my_status", {}) as { success?: boolean; data?: { station?: string } };
      isCaptain = !!(statusResp?.success && statusResp?.data?.station === "captain");

      const stateResp = await wsClient.send("get_state", {}) as { active_scenario?: string };
      activeScenario = stateResp?.active_scenario ?? null;

      await Promise.all(ships.map(async (ship) => {
        try {
          const sResp = await wsClient.send("station_status", { ship: ship.id }) as { success?: boolean; data?: { stations: ShipStation[] } };
          ship.stations = sResp?.success ? (sResp.data?.stations ?? []) : [];
        } catch { ship.stations = []; }
      }));
      ships = [...ships]; // trigger reactivity

      lastLobbyFetch = Date.now();
      menuState = "lobby";
    } catch (e) {
      errorMsg = "Failed to load lobby. Check server connection.";
    } finally {
      isLoading = false;
    }
  }

  // ── Mission Launch ─────────────────────────────────────────────────
  let launching = false;

  async function loadScenario(scenarioId: string) {
    if (!scenarioId || launching) return;
    launching = true;
    errorMsg = "";

    try {
      if (wsClient.status !== "connected") {
        try { await wsClient.connect(); } catch { /* continue */ }
      }

      const resp = await wsClient.send("load_scenario", { scenario: scenarioId }) as Record<string, unknown>;

      if (resp?.ok === false) {
        errorMsg = (resp.error as string) ?? "Failed to load scenario.";
        return;
      }

      activeScenario = scenarioId;
      selectedScenario = null;
      expandedCard = null;

      _dispatchScenarioLoaded(resp);
      await fetchAndRenderLobby();
    } catch (e) {
      errorMsg = "Error loading scenario.";
    } finally {
      launching = false;
    }
  }

  async function generateAndPlay() {
    if (isLoading) return;
    isLoading = true;
    errorMsg = "";

    try {
      const params: Record<string, unknown> = {
        mode: skirmishMode,
        player_ships: skirmishPlayerShips,
        enemy_ships: skirmishEnemyShips,
        start_range_km: skirmishRange,
        randomize_positions: true,
      };
      if (skirmishTimeLimit) params.time_limit_seconds = skirmishTimeLimit;

      const resp = await wsClient.send("generate_skirmish", params) as Record<string, unknown>;

      if (resp?.ok === false) {
        errorMsg = (resp.error as string) ?? "Skirmish generation failed.";
        return;
      }

      activeScenario = (resp?.scenario_name as string) ?? "Generated Skirmish";
      _dispatchScenarioLoaded(resp);
      await fetchAndRenderLobby();
    } catch { errorMsg = "Error generating skirmish."; }
    finally { isLoading = false; }
  }

  async function joinStation(shipId: string, stationName: string) {
    errorMsg = "";
    try {
      const assignResp = await wsClient.send("assign_ship", { ship: shipId }) as { success?: boolean; message?: string };
      if (!assignResp?.success) throw new Error(assignResp?.message ?? "assign failed");

      const claimResp = await wsClient.send("claim_station", { station: stationName, ship: shipId }) as { success?: boolean; message?: string };
      if (!claimResp?.success) throw new Error(claimResp?.message ?? "claim failed");

      const detail = { assignedShip: shipId, station: stationName };
      dispatch("scenario-loaded", detail);
      document.dispatchEvent(new CustomEvent("scenario-loaded", { detail }));

      await fetchAndRenderLobby();
    } catch (e) {
      errorMsg = `Failed to join station: ${e instanceof Error ? e.message : e}`;
    }
  }

  function startMission() {
    const detail = { started: true };
    dispatch("scenario-loaded", detail);
    document.dispatchEvent(new CustomEvent("scenario-loaded", { detail }));
  }

  function _dispatchScenarioLoaded(detail: Record<string, unknown>) {
    dispatch("scenario-loaded", { ship_id: detail.ship_id as string | undefined });
    document.dispatchEvent(new CustomEvent("scenario-loaded", { detail }));
  }

  // ── Post-mission ────────────────────────────────────────────────
  /** Called externally to switch to post-mission screen */
  export function showPostMission() { menuState = "post_mission"; }

  function replayScenario() {
    if (activeScenario) loadScenario(activeScenario);
  }

  function onNextMission() {
    dispatch("next-mission", {});
    document.dispatchEvent(new CustomEvent("next-mission", {}));
  }
</script>

<div class="loader-root">
  <!-- ── TITLE ─────────────────────────────────── -->
  {#if menuState === "title"}
    <div class="title-screen">
      <div class="title-glow"></div>
      <div class="title-content">
        <h1 class="game-title">FLAXOS SPACESHIP SIM</h1>
        <p class="game-subtitle">Hard Sci-Fi Tactical Bridge Simulator</p>
        <div class="title-buttons">
          <button class="btn btn-primary btn-large" on:click={goNewGame}>NEW GAME</button>
          <button class="btn btn-accent btn-large" on:click={goQuickPlay}>QUICK PLAY</button>
          <button class="btn btn-secondary btn-large" on:click={goJoinGame}>JOIN GAME</button>
        </div>
        <div class="title-version">v0.01</div>
      </div>
    </div>

  <!-- ── MISSION SELECT ─────────────────────────── -->
  {:else if menuState === "mission_select"}
    <div class="screen">
      <div class="screen-header">
        <button class="btn btn-ghost" on:click={() => menuState = "title"}>← BACK</button>
        <h2 class="section-title">SELECT MISSION</h2>
      </div>

      <div class="filter-bar">
        {#each CATEGORIES as cat}
          <button
            class="filter-btn"
            class:active={categoryFilter === cat}
            on:click={() => categoryFilter = cat}
          >
            {cat === "all" ? "ALL" : (CATEGORY_LABELS[cat] ?? cat.toUpperCase())}
          </button>
        {/each}
      </div>

      {#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}

      {#if filteredScenarios.length === 0}
        <div class="empty-state">
          {scenarios.length === 0 ? "No missions found. Check server connection." : "No missions in this category."}
        </div>
      {:else}
        <div class="mission-grid">
          {#each filteredScenarios as sc (sc.id)}
            {@const diffColor = DIFFICULTY_COLORS[sc.difficulty ?? ""] ?? "#888"}
            {@const isExpanded = expandedCard === sc.id}
            <div
              class="mission-card"
              class:selected={selectedScenario === sc.id}
              class:expanded={isExpanded}
              on:click|stopPropagation={() => selectedScenario = sc.id}
              role="button"
              tabindex="0"
              on:keydown={(e) => e.key === "Enter" && (selectedScenario = sc.id)}
            >
              <div class="card-header">
                <span class="card-name">{sc.name ?? sc.id}</span>
                <div class="card-tags">
                  <span class="tag" style="--tag-color: {diffColor}">{(sc.difficulty ?? "unknown").toUpperCase()}</span>
                  {#if sc.category}<span class="tag tag-cat">{CATEGORY_LABELS[sc.category] ?? sc.category.toUpperCase()}</span>{/if}
                  {#if sc.player_count}<span class="tag tag-players">{sc.player_count}P</span>{/if}
                </div>
              </div>
              <div class="card-desc">{sc.description ?? sc.mission_description ?? ""}</div>
              {#if isExpanded && sc.briefing}
                <div class="card-briefing">
                  <div class="briefing-label">MISSION BRIEFING</div>
                  <div class="briefing-text">{sc.briefing}</div>
                </div>
              {/if}
              <div class="card-actions">
                {#if sc.briefing}
                  <button class="btn btn-ghost btn-sm" on:click|stopPropagation={() => expandedCard = isExpanded ? null : sc.id}>
                    {isExpanded ? "HIDE" : "BRIEFING"}
                  </button>
                {/if}
                <button
                  class="btn btn-primary btn-sm"
                  disabled={launching}
                  on:click|stopPropagation={() => loadScenario(sc.id)}
                >
                  {launching && selectedScenario === sc.id ? "LOADING..." : "LAUNCH"}
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>

  <!-- ── QUICK PLAY ─────────────────────────────── -->
  {:else if menuState === "quick_play"}
    <div class="screen">
      <div class="screen-header">
        <button class="btn btn-ghost" on:click={() => menuState = "title"}>← BACK</button>
        <h2 class="section-title">QUICK PLAY</h2>
      </div>

      {#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}

      <div class="qp-section">
        <div class="qp-label">MODE</div>
        <div class="filter-bar">
          {#each SKIRMISH_MODES as m}
            <button class="filter-btn" class:active={skirmishMode === m.id} title={m.desc} on:click={() => skirmishMode = m.id}>
              {m.label}
            </button>
          {/each}
        </div>
      </div>

      <!-- Player ships -->
      <div class="qp-section">
        <div class="qp-label">PLAYER SHIPS</div>
        <div class="qp-ship-list">
          {#each skirmishPlayerShips as s, i}
            <div class="qp-ship-row">
              <span class="ship-class-tag">{s.class.toUpperCase()}</span>
              <button class="btn btn-ghost btn-xs" on:click={() => { skirmishPlayerShips.splice(i, 1); skirmishPlayerShips = [...skirmishPlayerShips]; }}>✕</button>
            </div>
          {/each}
        </div>
        <div class="qp-add-row">
          <select class="qp-select" bind:value={skirmishNewPlayerClass}>
            {#each SKIRMISH_SHIP_CLASSES as cls}<option value={cls}>{cls.toUpperCase()}</option>{/each}
          </select>
          <button class="btn btn-secondary btn-sm" on:click={() => { skirmishPlayerShips = [...skirmishPlayerShips, { class: skirmishNewPlayerClass }]; }}>ADD</button>
        </div>
      </div>

      <!-- Enemy ships -->
      <div class="qp-section">
        <div class="qp-label">ENEMY SHIPS</div>
        <div class="qp-ship-list">
          {#each skirmishEnemyShips as s, i}
            <div class="qp-ship-row">
              <span class="ship-class-tag">{s.class.toUpperCase()}</span>
              {#if (s.count ?? 1) > 1}<span class="count-tag">×{s.count}</span>{/if}
              <button class="btn btn-ghost btn-xs" on:click={() => { skirmishEnemyShips.splice(i, 1); skirmishEnemyShips = [...skirmishEnemyShips]; }}>✕</button>
            </div>
          {/each}
        </div>
        <div class="qp-add-row">
          <select class="qp-select" bind:value={skirmishNewEnemyClass}>
            {#each SKIRMISH_SHIP_CLASSES as cls}<option value={cls}>{cls.toUpperCase()}</option>{/each}
          </select>
          <input class="qp-count" type="number" min="1" max="10" bind:value={skirmishNewEnemyCount} />
          <button class="btn btn-secondary btn-sm" on:click={() => { skirmishEnemyShips = [...skirmishEnemyShips, { class: skirmishNewEnemyClass, count: skirmishNewEnemyCount }]; }}>ADD</button>
        </div>
      </div>

      <!-- Range slider -->
      <div class="qp-section">
        <div class="qp-label">START RANGE: <span class="range-val">{skirmishRange} km</span></div>
        <input type="range" class="qp-slider" min="10" max="200" step="5" bind:value={skirmishRange} />
      </div>

      <!-- Time limit -->
      <div class="qp-section">
        <div class="qp-label">TIME LIMIT <span class="qp-optional">(optional)</span></div>
        <div class="qp-add-row">
          <input class="qp-count" type="number" min="60" max="3600" step="30" placeholder="seconds" bind:value={skirmishTimeLimit} />
          <button class="btn btn-ghost btn-sm" on:click={() => skirmishTimeLimit = null}>CLEAR</button>
        </div>
      </div>

      <button class="btn btn-primary btn-large qp-launch" disabled={isLoading} on:click={generateAndPlay}>
        {isLoading ? "GENERATING..." : "GENERATE & PLAY"}
      </button>
    </div>

  <!-- ── LOBBY ──────────────────────────────────── -->
  {:else if menuState === "lobby"}
    <div class="screen">
      <div class="screen-header">
        <button class="btn btn-ghost" on:click={() => menuState = "title"}>← BACK</button>
        <h2 class="section-title">FLEET LOBBY</h2>
        <button class="btn btn-ghost btn-sm" on:click={fetchAndRenderLobby} disabled={isLoading}>
          {isLoading ? "..." : "REFRESH"}
        </button>
      </div>

      {#if activeScenario}
        <div class="lobby-scenario">Mission: {activeScenario}</div>
      {/if}
      {#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}

      {#if ships.length === 0}
        <div class="empty-state">No active fleet. Load a mission first.</div>
        <button class="btn btn-primary" on:click={goNewGame}>SELECT MISSION</button>
      {:else}
        <div class="ship-grid">
          {#each ships as ship (ship.id)}
            <div class="ship-card">
              <div class="ship-card-header">
                <span class="ship-name">{ship.name ?? ship.id}</span>
                <span class="ship-class-badge">{ship.class ?? "?"}</span>
                {#if ship.faction}<span class="ship-faction">{ship.faction.toUpperCase()}</span>{/if}
              </div>
              <div class="station-grid">
                {#each (ship.stations ?? []) as st}
                  {#if st.claimed}
                    <div class="station-slot occupied" title={st.player ?? "Taken"}>
                      <span class="st-name">{st.station}</span>
                      <span class="st-status">{st.player ?? "TAKEN"}</span>
                    </div>
                  {:else}
                    <button class="station-slot vacant" on:click={() => joinStation(ship.id, st.station)}>
                      <span class="st-name">{st.station}</span>
                      <span class="st-status">JOIN</span>
                    </button>
                  {/if}
                {/each}
              </div>
            </div>
          {/each}
        </div>

        {#if isCaptain}
          <button class="btn btn-primary btn-large start-btn" on:click={startMission}>START MISSION</button>
        {/if}
      {/if}
    </div>

  <!-- ── POST MISSION ───────────────────────────── -->
  {:else if menuState === "post_mission"}
    <div class="post-mission screen">
      <h2 class="section-title post-title">MISSION COMPLETE</h2>
      <div class="post-buttons">
        <button class="btn btn-primary btn-large" on:click={onNextMission}>NEXT MISSION</button>
        <button class="btn btn-secondary btn-large" on:click={replayScenario}>REPLAY</button>
        <button class="btn btn-ghost btn-large" on:click={() => menuState = "title"}>BACK TO MENU</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .loader-root {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-sans);
  }

  /* ── Title ── */
  .title-screen {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100%;
    padding: var(--space-xl);
    text-align: center;
    position: relative;
  }

  .title-glow {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(0, 170, 255, 0.07) 0%, transparent 70%);
    pointer-events: none;
  }

  .title-content { position: relative; z-index: 1; }

  .game-title {
    font-family: var(--font-mono);
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: 6px;
    color: var(--tier-accent, var(--hud-primary));
    text-shadow: 0 0 20px rgba(68, 136, 255, 0.4);
    margin: 0 0 var(--space-sm);
    text-transform: uppercase;
  }

  .game-subtitle {
    font-size: var(--font-size-sm);
    color: var(--text-secondary);
    letter-spacing: 2px;
    margin: 0 0 var(--space-xl);
  }

  .title-buttons {
    display: flex;
    gap: var(--space-md);
    justify-content: center;
    flex-wrap: wrap;
  }

  .title-version {
    margin-top: var(--space-lg);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-dim);
  }

  /* ── Screen wrapper ── */
  .screen {
    max-width: 900px;
    margin: 0 auto;
    padding: var(--space-md);
    min-height: 100%;
  }

  .screen-header {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: var(--space-sm);
  }

  .section-title {
    font-family: var(--font-mono);
    font-size: var(--font-size-lg);
    font-weight: 700;
    letter-spacing: 3px;
    color: var(--text-primary);
    text-transform: uppercase;
    flex: 1;
    margin: 0;
  }

  /* ── Filter bar ── */
  .filter-bar {
    display: flex;
    gap: var(--space-xs);
    flex-wrap: wrap;
    margin-bottom: var(--space-md);
  }

  .filter-btn {
    padding: 4px 12px;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: all var(--transition-fast);
  }

  .filter-btn.active {
    background: var(--tier-accent, var(--hud-primary));
    border-color: var(--tier-accent, var(--hud-primary));
    color: #0a0a0f;
    font-weight: 600;
  }

  .filter-btn:hover:not(.active) {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  /* ── Mission grid ── */
  .mission-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: var(--space-sm);
  }

  .mission-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    cursor: pointer;
    transition: border-color var(--transition-fast);
  }

  .mission-card:hover { border-color: var(--border-active); }
  .mission-card.selected { border-color: var(--tier-accent, var(--hud-primary)); }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-xs);
    margin-bottom: var(--space-xs);
  }

  .card-name {
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .card-tags { display: flex; gap: 4px; flex-wrap: wrap; }

  .tag {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    padding: 2px 6px;
    border-radius: 3px;
    background: rgba(var(--tier-accent-rgb, 68, 136, 255), 0.15);
    color: var(--tag-color, var(--tier-accent, var(--hud-primary)));
    border: 1px solid var(--tag-color, var(--tier-accent, var(--hud-primary)));
    font-weight: 600;
    letter-spacing: 0.5px;
    white-space: nowrap;
  }

  .tag-cat { color: var(--text-secondary); border-color: var(--border-default); background: transparent; }
  .tag-players { color: var(--text-dim); border-color: var(--border-subtle); background: transparent; }

  .card-desc {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    line-height: 1.4;
    margin-bottom: var(--space-xs);
  }

  .card-briefing {
    margin: var(--space-xs) 0;
    padding: var(--space-sm);
    background: var(--bg-input);
    border-radius: var(--radius-sm);
  }

  .briefing-label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: var(--space-xs);
  }

  .briefing-text {
    font-size: var(--font-size-xs);
    color: var(--text-primary);
    line-height: 1.5;
    white-space: pre-wrap;
  }

  .card-actions {
    display: flex;
    gap: var(--space-xs);
    justify-content: flex-end;
    margin-top: var(--space-xs);
  }

  /* ── Quick play ── */
  .qp-section { margin-bottom: var(--space-md); }

  .qp-label {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: var(--space-xs);
  }

  .qp-optional { color: var(--text-dim); font-weight: 400; }

  .qp-slider {
    width: 100%;
    accent-color: var(--tier-accent, var(--hud-primary));
  }

  .range-val { color: var(--tier-accent, var(--hud-primary)); font-weight: 600; }

  .qp-ship-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: var(--space-xs); }

  .qp-ship-row {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    padding: 4px 8px;
    background: var(--bg-input);
    border-radius: var(--radius-sm);
  }

  .ship-class-tag {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-primary);
    flex: 1;
  }

  .count-tag {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .qp-add-row { display: flex; gap: var(--space-xs); align-items: center; }

  .qp-select {
    flex: 1;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    padding: 4px 8px;
  }

  .qp-count {
    width: 60px;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    padding: 4px 8px;
    text-align: center;
  }

  .qp-launch { width: 100%; margin-top: var(--space-sm); }

  /* ── Lobby ── */
  .lobby-scenario {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--tier-accent, var(--hud-primary));
    margin-bottom: var(--space-sm);
    padding: var(--space-xs) var(--space-sm);
    background: rgba(var(--tier-accent-rgb, 68, 136, 255), 0.1);
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--tier-accent, var(--hud-primary));
  }

  .ship-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: var(--space-sm);
    margin-bottom: var(--space-md);
  }

  .ship-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
  }

  .ship-card-header {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    margin-bottom: var(--space-xs);
    padding-bottom: var(--space-xs);
    border-bottom: 1px solid var(--border-subtle);
  }

  .ship-name {
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--text-primary);
    flex: 1;
  }

  .ship-class-badge, .ship-faction {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    padding: 2px 6px;
    border-radius: 3px;
    background: var(--bg-input);
    color: var(--text-secondary);
    text-transform: uppercase;
  }

  .station-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
  }

  .station-slot {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 6px 4px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    font-family: var(--font-mono);
    transition: all var(--transition-fast);
  }

  .station-slot.vacant {
    cursor: pointer;
    background: rgba(var(--tier-accent-rgb, 68, 136, 255), 0.08);
    border-color: var(--tier-accent, var(--hud-primary));
  }

  .station-slot.vacant:hover {
    background: rgba(var(--tier-accent-rgb, 68, 136, 255), 0.2);
  }

  .station-slot.occupied {
    background: var(--bg-input);
    opacity: 0.7;
  }

  .st-name {
    font-size: 0.55rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .st-status {
    font-size: 0.6rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-top: 2px;
  }

  .station-slot.vacant .st-status { color: var(--tier-accent, var(--hud-primary)); }

  .start-btn { width: 100%; margin-top: var(--space-md); }

  /* ── Post mission ── */
  .post-mission {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 60vh;
    text-align: center;
  }

  .post-title { margin-bottom: var(--space-xl); font-size: 1.5rem; letter-spacing: 6px; }

  .post-buttons {
    display: flex;
    gap: var(--space-md);
    flex-wrap: wrap;
    justify-content: center;
  }

  /* ── Buttons ── */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-xs);
    padding: 8px 20px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    letter-spacing: 1px;
    cursor: pointer;
    transition: all var(--transition-fast);
    text-transform: uppercase;
    white-space: nowrap;
  }

  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-large { padding: 12px 32px; font-size: var(--font-size-sm); }
  .btn-sm { padding: 4px 12px; font-size: 0.65rem; }
  .btn-xs { padding: 2px 8px; font-size: 0.6rem; }

  .btn-primary {
    background: var(--tier-accent, var(--hud-primary));
    border-color: var(--tier-accent, var(--hud-primary));
    color: #0a0a0f;
  }
  .btn-primary:hover:not(:disabled) { filter: brightness(1.15); box-shadow: 0 0 12px rgba(var(--tier-accent-rgb, 68, 136, 255), 0.4); }

  .btn-accent {
    background: transparent;
    border-color: var(--tier-accent, var(--hud-primary));
    color: var(--tier-accent, var(--hud-primary));
  }
  .btn-accent:hover:not(:disabled) { background: rgba(var(--tier-accent-rgb, 68, 136, 255), 0.15); }

  .btn-secondary {
    background: var(--bg-input);
    border-color: var(--border-active);
    color: var(--text-primary);
  }
  .btn-secondary:hover:not(:disabled) { background: var(--bg-hover); }

  .btn-ghost {
    background: transparent;
    border-color: transparent;
    color: var(--text-secondary);
  }
  .btn-ghost:hover:not(:disabled) { color: var(--text-primary); background: var(--bg-hover); }

  /* ── Misc ── */
  .empty-state {
    text-align: center;
    padding: var(--space-xl);
    color: var(--text-dim);
    font-style: italic;
    font-size: var(--font-size-sm);
  }

  .error-msg {
    padding: var(--space-sm) var(--space-md);
    background: rgba(255, 68, 68, 0.1);
    border: 1px solid var(--status-critical);
    border-radius: var(--radius-sm);
    color: var(--status-critical);
    font-size: var(--font-size-xs);
    font-family: var(--font-mono);
    margin-bottom: var(--space-sm);
  }
</style>
