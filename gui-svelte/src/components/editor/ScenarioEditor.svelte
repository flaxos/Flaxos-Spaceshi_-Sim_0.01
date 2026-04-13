<script lang="ts">
  import { onMount } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { isCommandRejected, describeCommandFailure } from "../../lib/ws/commandResponse.js";

  // ── Types ────────────────────────────────────────────────────────────────────

  interface Ship {
    id: string;
    name: string;
    shipClass: string;
    faction: string;
    playerControlled: boolean;
    aiEnabled: boolean;
    px: number; py: number; pz: number;
    vx: number; vy: number; vz: number;
    aiRole: string;
    engagementRange: number;
    fleeThreshold: number;
  }

  interface Objective {
    id: string;
    type: string;
    description: string;
    required: boolean;
    target?: string;
    range?: number;
    time?: number;
  }

  interface ScenarioMeta {
    name: string;
    description: string;
    difficulty: string;
    category: string;
    player_count: string;
    time_limit: number;
    next_scenario: string;
    briefing: string;
  }

  // ── Constants ─────────────────────────────────────────────────────────────────

  const FACTIONS = ["unsa", "mcrn", "civilian", "pirates", "hostile", "neutral"];
  const AI_ROLES = ["combat", "freighter", "escort", "patrol"];
  const DIFFICULTY_OPTIONS = ["tutorial", "easy", "medium", "hard", "extreme"];
  const CATEGORY_OPTIONS = ["tutorial", "combat", "stealth", "fleet", "campaign"];
  const PLAYER_COUNT_OPTIONS = ["1", "1-2", "2-4"];

  const OBJECTIVE_TYPES = [
    "reach_range", "destroy_target", "mission_kill", "protect_ship",
    "survive_time", "dock_with", "scan_target", "avoid_detection",
    "avoid_mission_kill", "escape_range", "ammo_depleted",
    "match_velocity", "reach_position", "collect_item",
  ];

  const TARGET_OBJECTIVES = new Set([
    "reach_range", "destroy_target", "mission_kill", "protect_ship",
    "dock_with", "scan_target", "avoid_mission_kill", "escape_range",
    "ammo_depleted", "match_velocity",
  ]);
  const RANGE_OBJECTIVES = new Set(["reach_range", "escape_range"]);
  const TIME_OBJECTIVES  = new Set(["survive_time", "protect_ship", "avoid_detection"]);

  // ── State ────────────────────────────────────────────────────────────────────

  let scenarioList: string[] = [];
  let shipClasses: any[] = [];
  let selectedScenario: string | null = null;

  let statusMsg = "";
  let statusType: "idle" | "success" | "error" | "saving" = "idle";
  let statusTimer: ReturnType<typeof setTimeout> | null = null;

  let meta: ScenarioMeta = createEmptyMeta();
  let ships: Ship[] = [];
  let objectives: Objective[] = [];

  // Inline editing
  let editingShipIdx: number | null = null;
  let editingObjIdx: number | null = null;
  let shipDraft: Ship = emptyShip();
  let objDraft: Objective = emptyObjective();

  // ── Factories ─────────────────────────────────────────────────────────────────

  function createEmptyMeta(): ScenarioMeta {
    return {
      name: "", description: "", difficulty: "easy", category: "combat",
      player_count: "1", time_limit: 0, next_scenario: "", briefing: "",
    };
  }

  function emptyShip(): Ship {
    return {
      id: "", name: "", shipClass: "", faction: "neutral",
      playerControlled: false, aiEnabled: true,
      px: 0, py: 0, pz: 0, vx: 0, vy: 0, vz: 0,
      aiRole: "combat", engagementRange: 50000, fleeThreshold: 0.25,
    };
  }

  function emptyObjective(): Objective {
    return {
      id: "", type: "destroy_target", description: "", required: true,
      target: "", range: 1000, time: 60,
    };
  }

  // ── Status helper ─────────────────────────────────────────────────────────────

  function showStatus(msg: string, type: typeof statusType = "success") {
    statusMsg = msg;
    statusType = type;
    if (statusTimer) clearTimeout(statusTimer);
    if (type !== "saving") {
      statusTimer = setTimeout(() => { statusMsg = ""; statusType = "idle"; }, 4000);
    }
  }

  // ── Data loading ──────────────────────────────────────────────────────────────

  async function loadData() {
    try {
      const [scRes, clsRes] = await Promise.all([
        wsClient.send("list_scenarios", {}) as Promise<any>,
        wsClient.send("list_ship_classes", {}) as Promise<any>,
      ]);
      if (!isCommandRejected(scRes))  scenarioList = scRes.scenarios ?? [];
      if (!isCommandRejected(clsRes)) shipClasses  = clsRes.ship_classes ?? [];
    } catch {
      showStatus("Connection error loading editor data", "error");
    }
  }

  async function loadScenario(id: string) {
    try {
      const res = await wsClient.send("get_scenario_yaml", { scenario: id }) as any;
      if (isCommandRejected(res)) { showStatus(describeCommandFailure(res), "error"); return; }
      populateFromData(res.data ?? {});
      selectedScenario = id;
      editingShipIdx = null;
      editingObjIdx  = null;
    } catch {
      showStatus("Failed to load scenario", "error");
    }
  }

  function newScenario() {
    selectedScenario = null;
    meta = createEmptyMeta();
    ships = [];
    objectives = [];
    editingShipIdx = null;
    editingObjIdx  = null;
    statusMsg = "";
  }

  function populateFromData(data: any) {
    meta = {
      name:          data.name          ?? "",
      description:   data.description   ?? "",
      difficulty:    data.difficulty     ?? "easy",
      category:      data.category      ?? "combat",
      player_count:  data.player_count  ?? "1",
      time_limit:    data.settings?.time_limit   ?? data.time_limit   ?? 0,
      next_scenario: data.settings?.next_scenario ?? data.next_scenario ?? "",
      briefing:      data.briefing      ?? "",
    };

    ships = (data.ships ?? []).map((s: any) => ({
      id:               s.id          ?? "",
      name:             s.name        ?? "",
      shipClass:        s.class ?? s.ship_class ?? "",
      faction:          s.faction     ?? "neutral",
      playerControlled: s.player_controlled ?? false,
      aiEnabled:        s.ai_enabled  ?? !s.player_controlled,
      px: s.position?.x ?? 0,
      py: s.position?.y ?? 0,
      pz: s.position?.z ?? 0,
      vx: s.velocity?.x ?? 0,
      vy: s.velocity?.y ?? 0,
      vz: s.velocity?.z ?? 0,
      aiRole:          s.ai_role       ?? "combat",
      engagementRange: s.engagement_range ?? 50000,
      fleeThreshold:   s.flee_threshold   ?? 0.25,
    }));

    objectives = (data.objectives ?? []).map((o: any, i: number) => ({
      id:          o.id          ?? `obj_${i + 1}`,
      type:        o.type        ?? "destroy_target",
      description: o.description ?? "",
      required:    o.required    !== false,
      target:      o.target      ?? "",
      range:       o.range       ?? 1000,
      time:        o.time        ?? 60,
    }));
  }

  // ── Ship editing ──────────────────────────────────────────────────────────────

  function beginEditShip(idx: number) {
    editingObjIdx = null;
    if (idx === -1) {
      shipDraft = emptyShip();
    } else {
      shipDraft = { ...ships[idx] };
    }
    editingShipIdx = idx;
  }

  function cancelEditShip() { editingShipIdx = null; }

  function commitShip() {
    if (!shipDraft.id.trim()) { return; } // require ID
    if (editingShipIdx === -1) {
      ships = [...ships, { ...shipDraft }];
    } else if (editingShipIdx !== null) {
      ships = ships.map((s, i) => i === editingShipIdx ? { ...shipDraft } : s);
    }
    editingShipIdx = null;
  }

  function removeShip(idx: number) {
    ships = ships.filter((_, i) => i !== idx);
    if (editingShipIdx === idx) editingShipIdx = null;
  }

  // ── Objective editing ─────────────────────────────────────────────────────────

  function beginEditObj(idx: number) {
    editingShipIdx = null;
    if (idx === -1) {
      objDraft = emptyObjective();
    } else {
      objDraft = { ...objectives[idx] };
    }
    editingObjIdx = idx;
  }

  function cancelEditObj() { editingObjIdx = null; }

  function commitObj() {
    if (!objDraft.id.trim()) return;
    if (editingObjIdx === -1) {
      objectives = [...objectives, { ...objDraft }];
    } else if (editingObjIdx !== null) {
      objectives = objectives.map((o, i) => i === editingObjIdx ? { ...objDraft } : o);
    }
    editingObjIdx = null;
  }

  function removeObj(idx: number) {
    objectives = objectives.filter((_, i) => i !== idx);
    if (editingObjIdx === idx) editingObjIdx = null;
  }

  // ── YAML generation ───────────────────────────────────────────────────────────

  function yamlStr(s: string): string {
    // Wrap in quotes if contains special chars
    if (/[:#\[\]{}&*!|>'"%@`\n]/.test(s) || s.trim() !== s) {
      return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
    }
    return s || '""';
  }

  function generateYaml(): string {
    const lines: string[] = [];

    lines.push(`name: ${yamlStr(meta.name)}`);
    lines.push(`description: ${yamlStr(meta.description)}`);
    if (meta.briefing) lines.push(`briefing: ${yamlStr(meta.briefing)}`);
    lines.push(`difficulty: ${meta.difficulty}`);
    lines.push(`category: ${meta.category}`);
    lines.push(`player_count: ${yamlStr(meta.player_count)}`);
    lines.push("");
    lines.push("ships:");

    for (const s of ships) {
      lines.push(`  - id: ${yamlStr(s.id)}`);
      lines.push(`    name: ${yamlStr(s.name)}`);
      if (s.shipClass) lines.push(`    class: ${s.shipClass}`);
      lines.push(`    faction: ${s.faction}`);
      lines.push(`    player_controlled: ${s.playerControlled}`);
      lines.push(`    ai_enabled: ${s.aiEnabled}`);
      lines.push(`    position: {x: ${s.px}, y: ${s.py}, z: ${s.pz}}`);
      lines.push(`    velocity: {x: ${s.vx}, y: ${s.vy}, z: ${s.vz}}`);
      if (s.aiEnabled) {
        lines.push(`    ai_role: ${s.aiRole}`);
        lines.push(`    engagement_range: ${s.engagementRange}`);
        lines.push(`    flee_threshold: ${s.fleeThreshold}`);
      }
    }

    if (objectives.length > 0) {
      lines.push("");
      lines.push("objectives:");
      for (const o of objectives) {
        lines.push(`  - id: ${yamlStr(o.id)}`);
        lines.push(`    type: ${o.type}`);
        lines.push(`    description: ${yamlStr(o.description)}`);
        lines.push(`    required: ${o.required}`);
        if (TARGET_OBJECTIVES.has(o.type) && o.target) lines.push(`    target: ${yamlStr(o.target)}`);
        if (RANGE_OBJECTIVES.has(o.type))  lines.push(`    range: ${o.range}`);
        if (TIME_OBJECTIVES.has(o.type))   lines.push(`    time: ${o.time}`);
      }
    }

    // Settings block
    const hasSettings = meta.time_limit > 0 || meta.next_scenario;
    if (hasSettings) {
      lines.push("");
      lines.push("settings:");
      if (meta.time_limit > 0)   lines.push(`  time_limit: ${meta.time_limit}`);
      if (meta.next_scenario)    lines.push(`  next_scenario: ${yamlStr(meta.next_scenario)}`);
    }

    return lines.join("\n") + "\n";
  }

  // ── Validate ──────────────────────────────────────────────────────────────────

  function validateScenario(): string | null {
    if (!meta.name.trim()) return "Scenario name is required";
    if (ships.length === 0) return "At least one ship is required";
    return null;
  }

  // Derive filename from scenario name
  function scenarioFilename(): string {
    const slug = meta.name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    return `${slug || "scenario"}.yaml`;
  }

  // ── Save / Test / Export ──────────────────────────────────────────────────────

  async function saveScenario() {
    const err = validateScenario();
    if (err) { showStatus(err, "error"); return; }

    const filename = selectedScenario ?? scenarioFilename();
    showStatus("Saving…", "saving");
    try {
      const yaml_content = generateYaml();
      const res = await wsClient.send("save_scenario", { filename, yaml_content }) as any;
      if (isCommandRejected(res)) { showStatus(describeCommandFailure(res), "error"); return; }
      showStatus(`Saved: ${filename}`, "success");
      selectedScenario = filename;
      await loadData(); // refresh list
    } catch {
      showStatus("Connection error — save failed", "error");
    }
  }

  async function testScenario() {
    const err = validateScenario();
    if (err) { showStatus(err, "error"); return; }

    await saveScenario();
    if (statusType === "error") return;

    const filename = selectedScenario ?? scenarioFilename();
    document.dispatchEvent(new CustomEvent("scenario-loaded", {
      detail: { scenario: filename.replace(/\.ya?ml$/, "") },
      bubbles: true,
    }));
  }

  function exportYaml() {
    const yaml = generateYaml();
    const blob = new Blob([yaml], { type: "text/yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = scenarioFilename();
    a.click();
    URL.revokeObjectURL(url);
  }

  onMount(loadData);
</script>

<div class="scenario-editor">
  <!-- Sidebar: scenario list -->
  <aside class="scenario-list">
    <button class="new-btn" type="button" on:click={newScenario}>+ NEW</button>
    <div class="list-scroll">
      {#each scenarioList as sc}
        <button
          class="sc-btn"
          class:selected={sc === selectedScenario}
          type="button"
          on:click={() => loadScenario(sc)}
        >
          {sc.replace(/\.(ya?ml|json)$/, "").replace(/_/g, " ")}
        </button>
      {/each}
      {#if scenarioList.length === 0}
        <div class="list-empty">No scenarios found</div>
      {/if}
    </div>
  </aside>

  <!-- Main editor area -->
  <div class="editor-main">
    <!-- Metadata -->
    <section class="meta-section">
      <div class="section-title">METADATA</div>
      <div class="meta-grid">
        <label class="field-row">
          <span class="field-label">Name</span>
          <input type="text" class="field-input" bind:value={meta.name} placeholder="Scenario name" />
        </label>
        <label class="field-row">
          <span class="field-label">Difficulty</span>
          <select class="field-select" bind:value={meta.difficulty}>
            {#each DIFFICULTY_OPTIONS as d}<option value={d}>{d}</option>{/each}
          </select>
        </label>
        <label class="field-row">
          <span class="field-label">Category</span>
          <select class="field-select" bind:value={meta.category}>
            {#each CATEGORY_OPTIONS as c}<option value={c}>{c}</option>{/each}
          </select>
        </label>
        <label class="field-row">
          <span class="field-label">Players</span>
          <select class="field-select" bind:value={meta.player_count}>
            {#each PLAYER_COUNT_OPTIONS as p}<option value={p}>{p}</option>{/each}
          </select>
        </label>
        <label class="field-row">
          <span class="field-label">Time Limit (s)</span>
          <input type="number" class="field-input" bind:value={meta.time_limit} min="0" step="30"
            placeholder="0 = no limit" />
        </label>
        <label class="field-row">
          <span class="field-label">Next Scenario</span>
          <input type="text" class="field-input" bind:value={meta.next_scenario}
            placeholder="filename or scenario ID" />
        </label>
        <label class="field-row full">
          <span class="field-label">Description</span>
          <input type="text" class="field-input" bind:value={meta.description} />
        </label>
        <label class="field-row full">
          <span class="field-label">Briefing</span>
          <textarea class="field-textarea" rows="2" bind:value={meta.briefing}></textarea>
        </label>
      </div>
    </section>

    <!-- Ships + Objectives columns -->
    <div class="editor-columns">
      <!-- Ships -->
      <section class="ships-col">
        <div class="section-title">SHIPS ({ships.length})</div>

        {#each ships as ship, i}
          <div class="entity-card" class:editing={editingShipIdx === i}>
            <div class="card-info">
              <span class="card-title">{ship.name || ship.id}</span>
              <span class="card-tags">
                <span class="tag">{ship.shipClass || "—"}</span>
                <span class="tag">{ship.faction}</span>
                {#if ship.playerControlled}<span class="tag player">PLAYER</span>{/if}
                {#if ship.aiEnabled && !ship.playerControlled}<span class="tag ai">AI</span>{/if}
              </span>
            </div>
            <div class="card-actions">
              <button class="icon-btn" type="button" on:click={() => beginEditShip(i)}>EDIT</button>
              <button class="icon-btn danger" type="button" on:click={() => removeShip(i)}>×</button>
            </div>
          </div>

          {#if editingShipIdx === i}
            <div class="inline-form">
              <div class="form-grid">
                <label class="field-row">
                  <span class="field-label">ID</span>
                  <input type="text" class="field-input" bind:value={shipDraft.id} placeholder="player" />
                </label>
                <label class="field-row">
                  <span class="field-label">Name</span>
                  <input type="text" class="field-input" bind:value={shipDraft.name} placeholder="Ship name" />
                </label>
                <label class="field-row">
                  <span class="field-label">Class</span>
                  <select class="field-select" bind:value={shipDraft.shipClass}>
                    <option value="">— none —</option>
                    {#each shipClasses as cls}
                      <option value={cls.class_id}>{cls.class_name}</option>
                    {/each}
                  </select>
                </label>
                <label class="field-row">
                  <span class="field-label">Faction</span>
                  <select class="field-select" bind:value={shipDraft.faction}>
                    {#each FACTIONS as f}<option value={f}>{f}</option>{/each}
                  </select>
                </label>
                <label class="field-row">
                  <span class="field-label">Player</span>
                  <input type="checkbox" bind:checked={shipDraft.playerControlled} />
                </label>
                <label class="field-row">
                  <span class="field-label">AI</span>
                  <input type="checkbox" bind:checked={shipDraft.aiEnabled} />
                </label>
                {#if shipDraft.aiEnabled}
                  <label class="field-row">
                    <span class="field-label">AI Role</span>
                    <select class="field-select" bind:value={shipDraft.aiRole}>
                      {#each AI_ROLES as r}<option value={r}>{r}</option>{/each}
                    </select>
                  </label>
                {/if}
                <div class="field-row"><span class="field-label">Position (km)</span>
                  <div class="xyz-row">
                    <input type="number" class="field-input" bind:value={shipDraft.px} step="1000" placeholder="X" />
                    <input type="number" class="field-input" bind:value={shipDraft.py} step="1000" placeholder="Y" />
                    <input type="number" class="field-input" bind:value={shipDraft.pz} step="1000" placeholder="Z" />
                  </div>
                </div>
                <div class="field-row"><span class="field-label">Velocity (m/s)</span>
                  <div class="xyz-row">
                    <input type="number" class="field-input" bind:value={shipDraft.vx} step="10" placeholder="X" />
                    <input type="number" class="field-input" bind:value={shipDraft.vy} step="10" placeholder="Y" />
                    <input type="number" class="field-input" bind:value={shipDraft.vz} step="10" placeholder="Z" />
                  </div>
                </div>
              </div>
              <div class="form-actions">
                <button class="action-btn primary" type="button" on:click={commitShip}>CONFIRM</button>
                <button class="action-btn" type="button" on:click={cancelEditShip}>CANCEL</button>
              </div>
            </div>
          {/if}
        {/each}

        <!-- Add new ship inline form -->
        {#if editingShipIdx === -1}
          <div class="inline-form">
            <div class="form-grid">
              <label class="field-row">
                <span class="field-label">ID</span>
                <input type="text" class="field-input" bind:value={shipDraft.id} placeholder="player" />
              </label>
              <label class="field-row">
                <span class="field-label">Name</span>
                <input type="text" class="field-input" bind:value={shipDraft.name} />
              </label>
              <label class="field-row">
                <span class="field-label">Class</span>
                <select class="field-select" bind:value={shipDraft.shipClass}>
                  <option value="">— none —</option>
                  {#each shipClasses as cls}
                    <option value={cls.class_id}>{cls.class_name}</option>
                  {/each}
                </select>
              </label>
              <label class="field-row">
                <span class="field-label">Faction</span>
                <select class="field-select" bind:value={shipDraft.faction}>
                  {#each FACTIONS as f}<option value={f}>{f}</option>{/each}
                </select>
              </label>
              <label class="field-row">
                <span class="field-label">Player</span>
                <input type="checkbox" bind:checked={shipDraft.playerControlled} />
              </label>
              <label class="field-row">
                <span class="field-label">AI</span>
                <input type="checkbox" bind:checked={shipDraft.aiEnabled} />
              </label>
              <div class="field-row"><span class="field-label">Position (m)</span>
                <div class="xyz-row">
                  <input type="number" class="field-input" bind:value={shipDraft.px} step="1000" placeholder="X" />
                  <input type="number" class="field-input" bind:value={shipDraft.py} step="1000" placeholder="Y" />
                  <input type="number" class="field-input" bind:value={shipDraft.pz} step="1000" placeholder="Z" />
                </div>
              </div>
            </div>
            <div class="form-actions">
              <button class="action-btn primary" type="button" on:click={commitShip}>ADD SHIP</button>
              <button class="action-btn" type="button" on:click={cancelEditShip}>CANCEL</button>
            </div>
          </div>
        {/if}

        <button class="add-btn" type="button" on:click={() => beginEditShip(-1)}>+ ADD SHIP</button>
      </section>

      <!-- Objectives -->
      <section class="objectives-col">
        <div class="section-title">OBJECTIVES ({objectives.length})</div>

        {#each objectives as obj, i}
          <div class="entity-card" class:editing={editingObjIdx === i}>
            <div class="card-info">
              <span class="card-title">{obj.type.replace(/_/g, " ")}</span>
              <span class="card-tags">
                <span class="tag" class:required={obj.required}>{obj.required ? "REQ" : "OPT"}</span>
                {#if obj.target}<span class="tag">→ {obj.target}</span>{/if}
              </span>
              {#if obj.description}<div class="card-desc">{obj.description}</div>{/if}
            </div>
            <div class="card-actions">
              <button class="icon-btn" type="button" on:click={() => beginEditObj(i)}>EDIT</button>
              <button class="icon-btn danger" type="button" on:click={() => removeObj(i)}>×</button>
            </div>
          </div>

          {#if editingObjIdx === i}
            <div class="inline-form">
              <div class="form-grid">
                <label class="field-row">
                  <span class="field-label">ID</span>
                  <input type="text" class="field-input" bind:value={objDraft.id} />
                </label>
                <label class="field-row">
                  <span class="field-label">Type</span>
                  <select class="field-select" bind:value={objDraft.type}>
                    {#each OBJECTIVE_TYPES as t}<option value={t}>{t.replace(/_/g, " ")}</option>{/each}
                  </select>
                </label>
                <label class="field-row">
                  <span class="field-label">Required</span>
                  <input type="checkbox" bind:checked={objDraft.required} />
                </label>
                <label class="field-row full">
                  <span class="field-label">Description</span>
                  <input type="text" class="field-input" bind:value={objDraft.description} />
                </label>
                {#if TARGET_OBJECTIVES.has(objDraft.type)}
                  <label class="field-row">
                    <span class="field-label">Target ID</span>
                    <input type="text" class="field-input" bind:value={objDraft.target} placeholder="ship ID" />
                  </label>
                {/if}
                {#if RANGE_OBJECTIVES.has(objDraft.type)}
                  <label class="field-row">
                    <span class="field-label">Range (m)</span>
                    <input type="number" class="field-input" bind:value={objDraft.range} min="0" step="100" />
                  </label>
                {/if}
                {#if TIME_OBJECTIVES.has(objDraft.type)}
                  <label class="field-row">
                    <span class="field-label">Time (s)</span>
                    <input type="number" class="field-input" bind:value={objDraft.time} min="0" step="10" />
                  </label>
                {/if}
              </div>
              <div class="form-actions">
                <button class="action-btn primary" type="button" on:click={commitObj}>CONFIRM</button>
                <button class="action-btn" type="button" on:click={cancelEditObj}>CANCEL</button>
              </div>
            </div>
          {/if}
        {/each}

        {#if editingObjIdx === -1}
          <div class="inline-form">
            <div class="form-grid">
              <label class="field-row">
                <span class="field-label">ID</span>
                <input type="text" class="field-input" bind:value={objDraft.id} placeholder="obj_1" />
              </label>
              <label class="field-row">
                <span class="field-label">Type</span>
                <select class="field-select" bind:value={objDraft.type}>
                  {#each OBJECTIVE_TYPES as t}<option value={t}>{t.replace(/_/g, " ")}</option>{/each}
                </select>
              </label>
              <label class="field-row">
                <span class="field-label">Required</span>
                <input type="checkbox" bind:checked={objDraft.required} />
              </label>
              <label class="field-row full">
                <span class="field-label">Description</span>
                <input type="text" class="field-input" bind:value={objDraft.description} />
              </label>
              {#if TARGET_OBJECTIVES.has(objDraft.type)}
                <label class="field-row">
                  <span class="field-label">Target ID</span>
                  <input type="text" class="field-input" bind:value={objDraft.target} />
                </label>
              {/if}
              {#if RANGE_OBJECTIVES.has(objDraft.type)}
                <label class="field-row">
                  <span class="field-label">Range (m)</span>
                  <input type="number" class="field-input" bind:value={objDraft.range} min="0" step="100" />
                </label>
              {/if}
              {#if TIME_OBJECTIVES.has(objDraft.type)}
                <label class="field-row">
                  <span class="field-label">Time (s)</span>
                  <input type="number" class="field-input" bind:value={objDraft.time} min="0" step="10" />
                </label>
              {/if}
            </div>
            <div class="form-actions">
              <button class="action-btn primary" type="button" on:click={commitObj}>ADD OBJECTIVE</button>
              <button class="action-btn" type="button" on:click={cancelEditObj}>CANCEL</button>
            </div>
          </div>
        {/if}

        <button class="add-btn" type="button" on:click={() => beginEditObj(-1)}>+ ADD OBJECTIVE</button>
      </section>
    </div>

    <!-- Action bar -->
    <div class="action-bar">
      <button class="action-btn primary" type="button" on:click={saveScenario}>SAVE</button>
      <button class="action-btn" type="button" on:click={testScenario}>TEST MISSION</button>
      <button class="action-btn" type="button" on:click={exportYaml}>EXPORT YAML</button>
      {#if statusMsg}
        <span class="status-msg status-{statusType}">{statusMsg}</span>
      {/if}
    </div>
  </div>
</div>

<style>
  .scenario-editor {
    display: grid;
    grid-template-columns: 200px 1fr;
    height: 100%;
    overflow: hidden;
  }

  /* Sidebar */
  .scenario-list {
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border-default);
    overflow: hidden;
  }

  .new-btn {
    flex-shrink: 0;
    padding: 8px 12px;
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.1);
    border: none;
    border-bottom: 1px solid var(--border-default);
    color: var(--tier-accent, var(--hud-primary));
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    cursor: pointer;
    text-align: left;
  }

  .new-btn:hover { background: rgba(var(--tier-accent-rgb, 68,136,255), 0.18); }

  .list-scroll { flex: 1; overflow-y: auto; scrollbar-width: thin; }

  .sc-btn {
    display: block;
    width: 100%;
    padding: 7px 10px;
    background: none;
    border: none;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: 0.65rem;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-transform: capitalize;
  }

  .sc-btn:hover { background: var(--bg-hover); }
  .sc-btn.selected {
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.1);
    border-left: 2px solid var(--tier-accent, var(--hud-primary));
    color: var(--text-primary);
  }

  .list-empty {
    padding: 12px 10px;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-dim);
  }

  /* Main area */
  .editor-main {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    gap: 0;
  }

  .meta-section {
    flex-shrink: 0;
    padding: var(--space-xs) var(--space-sm);
    border-bottom: 1px solid var(--border-default);
  }

  .section-title {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--tier-accent, var(--text-secondary));
    margin-bottom: 6px;
  }

  .meta-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px 8px;
  }

  .editor-columns {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    overflow: hidden;
  }

  .ships-col,
  .objectives-col {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    overflow-y: auto;
    padding: var(--space-xs) var(--space-sm);
    border-right: 1px solid var(--border-default);
  }

  .objectives-col { border-right: none; }

  /* Form elements */
  .field-row {
    display: grid;
    grid-template-columns: 90px 1fr;
    align-items: center;
    gap: 4px;
  }

  .field-row.full { grid-column: 1 / -1; }

  .field-label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--text-dim);
    white-space: nowrap;
  }

  .field-input,
  .field-select {
    background: var(--bg-input, rgba(255,255,255,0.04));
    border: 1px solid var(--border-default);
    border-radius: 3px;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    padding: 3px 6px;
    width: 100%;
    box-sizing: border-box;
  }

  .field-input:focus,
  .field-select:focus { outline: none; border-color: var(--tier-accent, var(--hud-primary)); }

  .field-textarea {
    background: var(--bg-input, rgba(255,255,255,0.04));
    border: 1px solid var(--border-default);
    border-radius: 3px;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    padding: 4px 6px;
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
    grid-column: 2;
  }

  .xyz-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 4px;
  }

  /* Entity cards */
  .entity-card {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    border: 1px solid var(--border-default);
    border-radius: 3px;
    padding: 5px 8px;
    gap: 6px;
    background: var(--bg-panel);
  }

  .entity-card.editing { border-color: rgba(var(--tier-accent-rgb, 68,136,255), 0.5); }

  .card-info { flex: 1; min-width: 0; }

  .card-title {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-primary);
    text-transform: capitalize;
  }

  .card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    margin-top: 3px;
  }

  .tag {
    font-family: var(--font-mono);
    font-size: 0.55rem;
    color: var(--text-dim);
    border: 1px solid var(--border-default);
    border-radius: 2px;
    padding: 1px 4px;
  }

  .tag.player { color: var(--status-nominal, #00ff88); border-color: var(--status-nominal, #00ff88); }
  .tag.ai     { color: var(--hud-primary, #00aaff); border-color: var(--hud-primary, #00aaff); }
  .tag.required { color: var(--status-warning, #ffaa00); border-color: var(--status-warning, #ffaa00); }

  .card-desc {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--text-dim);
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card-actions {
    display: flex;
    gap: 3px;
    flex-shrink: 0;
  }

  .icon-btn {
    padding: 2px 6px;
    background: none;
    border: 1px solid var(--border-default);
    border-radius: 2px;
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.55rem;
    cursor: pointer;
  }

  .icon-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
  .icon-btn.danger { color: var(--status-critical, #ff4444); }

  /* Inline form */
  .inline-form {
    border: 1px solid rgba(var(--tier-accent-rgb, 68,136,255), 0.35);
    border-radius: 3px;
    padding: 8px;
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.04);
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px 8px;
    margin-bottom: 6px;
  }

  .form-actions {
    display: flex;
    gap: 6px;
  }

  .add-btn {
    padding: 5px 10px;
    background: rgba(255,255,255,0.02);
    border: 1px dashed var(--border-default);
    border-radius: 3px;
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    cursor: pointer;
    text-align: left;
    letter-spacing: 0.04em;
  }

  .add-btn:hover { border-color: var(--tier-accent, var(--hud-primary)); color: var(--text-primary); }

  /* Action bar */
  .action-bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 8px var(--space-sm);
    border-top: 1px solid var(--border-default);
    background: var(--bg-panel);
  }

  .action-btn {
    padding: 6px 14px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: rgba(255,255,255,0.04);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: background 0.12s, border-color 0.12s, color 0.12s;
  }

  .action-btn:hover { background: rgba(255,255,255,0.08); color: var(--text-primary); }

  .action-btn.primary {
    border-color: rgba(var(--tier-accent-rgb, 68,136,255), 0.6);
    color: var(--tier-accent, var(--hud-primary));
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.1);
  }

  .action-btn.primary:hover { background: rgba(var(--tier-accent-rgb, 68,136,255), 0.2); }

  .status-msg { font-family: var(--font-mono); font-size: var(--font-size-xs); }
  .status-success { color: var(--status-nominal, #00ff88); }
  .status-error   { color: var(--status-critical, #ff4444); }
  .status-saving  { color: var(--text-dim); }

  @media (max-width: 900px) {
    .editor-columns { grid-template-columns: 1fr; }
    .ships-col { border-right: none; border-bottom: 1px solid var(--border-default); }
  }
</style>
