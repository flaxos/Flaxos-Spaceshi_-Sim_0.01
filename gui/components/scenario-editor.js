/**
 * Scenario Editor Component
 * Visual editor for creating and editing YAML scenario files.
 * Ships, objectives, metadata -- all serialized to YAML and sent to server.
 */

import { wsClient } from "../js/ws-client.js";

const FACTIONS = ["unsa", "mcrn", "civilian", "pirates", "hostile", "neutral"];
const DIFFICULTIES = ["tutorial", "easy", "medium", "hard", "extreme"];
const CATEGORIES = ["tutorial", "combat", "stealth", "fleet", "campaign"];
const PLAYER_COUNTS = ["1", "1-2", "2-4"];
const AI_ROLES = ["combat", "freighter", "escort", "patrol"];

const OBJECTIVE_TYPES = [
  "reach_range", "destroy_target", "mission_kill", "protect_ship",
  "survive_time", "dock_with", "scan_target", "avoid_detection",
  "avoid_mission_kill", "escape_range", "ammo_depleted",
  "match_velocity", "reach_position", "collect_item",
];

// Objective types that use a target ship reference
const TARGET_OBJECTIVES = [
  "reach_range", "destroy_target", "mission_kill", "protect_ship",
  "dock_with", "scan_target", "avoid_mission_kill", "escape_range",
  "ammo_depleted", "match_velocity",
];

// Objective types that use a range/distance parameter
const RANGE_OBJECTIVES = ["reach_range", "escape_range"];

// Objective types that use a time parameter
const TIME_OBJECTIVES = ["survive_time", "protect_ship", "avoid_detection"];

class ScenarioEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._ships = [];
    this._objectives = [];
    this._shipClasses = [];
    this._existingScenarios = [];
    // Metadata
    this._name = "";
    this._description = "";
    this._difficulty = "medium";
    this._playerCount = "1";
    this._category = "combat";
    this._nextScenario = "";
    this._briefing = "";
    this._timeLimit = 300;
  }

  connectedCallback() {
    this._fetchShipClasses();
    this._fetchScenarios();
    this._render();
  }

  async _fetchShipClasses() {
    try {
      const resp = await wsClient.send("list_ship_classes", {});
      if (resp?.ok && resp.ship_classes) {
        this._shipClasses = resp.ship_classes;
        this._render();
      }
    } catch (e) {
      console.warn("Failed to fetch ship classes:", e.message);
    }
  }

  async _fetchScenarios() {
    try {
      const resp = await wsClient.send("list_scenarios", {});
      if (resp?.ok && resp.scenarios) {
        this._existingScenarios = resp.scenarios;
        this._render();
      }
    } catch (e) {
      console.warn("Failed to fetch scenarios:", e.message);
    }
  }

  _render() {
    const classOptions = this._shipClasses
      .map(c => `<option value="${c.class_id || c.id || c}">${c.class_name || c.class_id || c}</option>`)
      .join("");
    const scenarioOptions = this._existingScenarios
      .map(s => `<option value="${s.id || s.file}">${s.name || s.id || s.file}</option>`)
      .join("");

    this.shadowRoot.innerHTML = `
      <style>${ScenarioEditor._styles()}</style>
      <div class="editor-root">
        <div class="metadata-bar">
          <div class="meta-row">
            <label>Name <input type="text" id="meta-name" value="${this._esc(this._name)}" placeholder="Scenario name"></label>
            <label>Difficulty
              <select id="meta-difficulty">
                ${DIFFICULTIES.map(d => `<option value="${d}" ${d === this._difficulty ? "selected" : ""}>${d}</option>`).join("")}
              </select>
            </label>
            <label>Players
              <select id="meta-players">
                ${PLAYER_COUNTS.map(p => `<option value="${p}" ${p === this._playerCount ? "selected" : ""}>${p}</option>`).join("")}
              </select>
            </label>
            <label>Category
              <select id="meta-category">
                ${CATEGORIES.map(c => `<option value="${c}" ${c === this._category ? "selected" : ""}>${c}</option>`).join("")}
              </select>
            </label>
            <label>Time Limit (s) <input type="number" id="meta-timelimit" value="${this._timeLimit}" min="0" step="30"></label>
          </div>
          <div class="meta-row">
            <label class="wide">Description <input type="text" id="meta-desc" value="${this._esc(this._description)}" placeholder="Short description"></label>
            <label>Next Scenario
              <select id="meta-next">
                <option value="">-- none --</option>
                ${scenarioOptions}
              </select>
            </label>
          </div>
          <label class="full-width">Briefing
            <textarea id="meta-briefing" rows="3" placeholder="Mission briefing text...">${this._esc(this._briefing)}</textarea>
          </label>
        </div>

        <div class="columns">
          <!-- LEFT: Ships -->
          <div class="column">
            <div class="column-header">
              <h3>SHIPS</h3>
              <button class="btn btn-add" id="btn-add-ship">+ ADD SHIP</button>
            </div>
            <div class="card-list" id="ship-list">
              ${this._ships.map((s, i) => this._renderShipCard(s, i)).join("")}
              ${this._ships.length === 0 ? '<div class="empty-hint">No ships defined. Click ADD SHIP to begin.</div>' : ""}
            </div>
          </div>

          <!-- RIGHT: Objectives -->
          <div class="column">
            <div class="column-header">
              <h3>OBJECTIVES</h3>
              <button class="btn btn-add" id="btn-add-obj">+ ADD OBJECTIVE</button>
            </div>
            <div class="card-list" id="obj-list">
              ${this._objectives.map((o, i) => this._renderObjectiveCard(o, i)).join("")}
              ${this._objectives.length === 0 ? '<div class="empty-hint">No objectives defined. Click ADD OBJECTIVE to begin.</div>' : ""}
            </div>
          </div>
        </div>

        <div class="bottom-bar">
          <button class="btn btn-primary" id="btn-save">SAVE SCENARIO</button>
          <button class="btn btn-secondary" id="btn-load">LOAD SCENARIO</button>
          <button class="btn btn-secondary" id="btn-test">TEST MISSION</button>
          <button class="btn btn-secondary" id="btn-export">EXPORT YAML</button>
          <button class="btn btn-secondary" id="btn-validate">VALIDATE</button>
          <div class="status-msg" id="status-msg"></div>
        </div>
      </div>

      <!-- Ship form dialog (hidden) -->
      <div class="dialog-backdrop" id="ship-dialog" style="display:none">
        <div class="dialog">
          <h3 id="ship-dialog-title">Add Ship</h3>
          <div class="form-grid">
            <label>ID <input type="text" id="sf-id" placeholder="e.g. player"></label>
            <label>Name <input type="text" id="sf-name" placeholder="e.g. UNS Valor"></label>
            <label>Ship Class
              <select id="sf-class"><option value="">--select--</option>${classOptions}</select>
            </label>
            <label>Faction
              <select id="sf-faction">
                ${FACTIONS.map(f => `<option value="${f}">${f}</option>`).join("")}
              </select>
            </label>
            <label class="checkbox-label"><input type="checkbox" id="sf-player"> Player Controlled</label>
            <label class="checkbox-label"><input type="checkbox" id="sf-ai"> AI Enabled</label>
            <label>Pos X (km) <input type="number" id="sf-px" value="0" step="1"></label>
            <label>Pos Y (km) <input type="number" id="sf-py" value="0" step="1"></label>
            <label>Pos Z (km) <input type="number" id="sf-pz" value="0" step="1"></label>
            <label>AI Role
              <select id="sf-ai-role">
                <option value="">--none--</option>
                ${AI_ROLES.map(r => `<option value="${r}">${r}</option>`).join("")}
              </select>
            </label>
            <label>Engagement Range (m) <input type="number" id="sf-engage" value="60000" step="1000"></label>
            <label>Flee Threshold <input type="number" id="sf-flee" value="0.2" step="0.05" min="0" max="1"></label>
          </div>
          <div class="dialog-buttons">
            <button class="btn btn-primary" id="sf-confirm">CONFIRM</button>
            <button class="btn btn-secondary" id="sf-cancel">CANCEL</button>
          </div>
        </div>
      </div>

      <!-- Objective form dialog (hidden) -->
      <div class="dialog-backdrop" id="obj-dialog" style="display:none">
        <div class="dialog">
          <h3 id="obj-dialog-title">Add Objective</h3>
          <div class="form-grid">
            <label>ID <input type="text" id="of-id" placeholder="e.g. reach_target"></label>
            <label>Type
              <select id="of-type">
                ${OBJECTIVE_TYPES.map(t => `<option value="${t}">${t}</option>`).join("")}
              </select>
            </label>
            <label class="wide">Description <input type="text" id="of-desc" placeholder="Objective description"></label>
            <label class="checkbox-label"><input type="checkbox" id="of-required" checked> Required</label>
            <label>Target Ship
              <select id="of-target">
                <option value="">--none--</option>
                ${this._ships.map(s => `<option value="${s.id}">${s.id} (${s.name})</option>`).join("")}
              </select>
            </label>
            <label>Range (m) <input type="number" id="of-range" value="1000" step="100"></label>
            <label>Time (s) <input type="number" id="of-time" value="60" step="10"></label>
          </div>
          <div class="dialog-buttons">
            <button class="btn btn-primary" id="of-confirm">CONFIRM</button>
            <button class="btn btn-secondary" id="of-cancel">CANCEL</button>
          </div>
        </div>
      </div>

      <!-- Load scenario dialog -->
      <div class="dialog-backdrop" id="load-dialog" style="display:none">
        <div class="dialog">
          <h3>Load Scenario</h3>
          <label>Scenario
            <select id="ld-scenario">
              ${scenarioOptions}
            </select>
          </label>
          <div class="dialog-buttons">
            <button class="btn btn-primary" id="ld-confirm">LOAD</button>
            <button class="btn btn-secondary" id="ld-cancel">CANCEL</button>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
  }

  _bindEvents() {
    const $ = (sel) => this.shadowRoot.querySelector(sel);

    // Metadata live-sync
    $("#meta-name")?.addEventListener("input", e => { this._name = e.target.value; });
    $("#meta-desc")?.addEventListener("input", e => { this._description = e.target.value; });
    $("#meta-difficulty")?.addEventListener("change", e => { this._difficulty = e.target.value; });
    $("#meta-players")?.addEventListener("change", e => { this._playerCount = e.target.value; });
    $("#meta-category")?.addEventListener("change", e => { this._category = e.target.value; });
    $("#meta-next")?.addEventListener("change", e => { this._nextScenario = e.target.value; });
    $("#meta-briefing")?.addEventListener("input", e => { this._briefing = e.target.value; });
    $("#meta-timelimit")?.addEventListener("input", e => { this._timeLimit = parseInt(e.target.value) || 0; });

    // Ship add/edit
    $("#btn-add-ship")?.addEventListener("click", () => this._openShipDialog());

    // Objective add
    $("#btn-add-obj")?.addEventListener("click", () => this._openObjDialog());

    // Ship card remove buttons
    this.shadowRoot.querySelectorAll(".ship-remove").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.idx);
        this._ships.splice(idx, 1);
        this._render();
      });
    });

    // Ship card edit buttons
    this.shadowRoot.querySelectorAll(".ship-edit").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.idx);
        this._openShipDialog(idx);
      });
    });

    // Objective card remove buttons
    this.shadowRoot.querySelectorAll(".obj-remove").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.idx);
        this._objectives.splice(idx, 1);
        this._render();
      });
    });

    // Objective card edit buttons
    this.shadowRoot.querySelectorAll(".obj-edit").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.idx);
        this._openObjDialog(idx);
      });
    });

    // Ship dialog
    $("#sf-cancel")?.addEventListener("click", () => { $("#ship-dialog").style.display = "none"; });
    $("#sf-confirm")?.addEventListener("click", () => this._confirmShip());

    // Objective dialog
    $("#of-cancel")?.addEventListener("click", () => { $("#obj-dialog").style.display = "none"; });
    $("#of-confirm")?.addEventListener("click", () => this._confirmObjective());

    // Load dialog
    $("#ld-cancel")?.addEventListener("click", () => { $("#load-dialog").style.display = "none"; });
    $("#ld-confirm")?.addEventListener("click", () => this._confirmLoad());

    // Bottom bar
    $("#btn-save")?.addEventListener("click", () => this._saveScenario());
    $("#btn-load")?.addEventListener("click", () => { $("#load-dialog").style.display = "flex"; });
    $("#btn-test")?.addEventListener("click", () => this._testMission());
    $("#btn-export")?.addEventListener("click", () => this._exportYaml());
    $("#btn-validate")?.addEventListener("click", () => this._validate());
  }

  // --- Ship dialog ---

  _openShipDialog(editIdx = null) {
    const $ = (sel) => this.shadowRoot.querySelector(sel);
    const dlg = $("#ship-dialog");
    const title = $("#ship-dialog-title");
    dlg._editIdx = editIdx;

    if (editIdx !== null) {
      const s = this._ships[editIdx];
      title.textContent = "Edit Ship";
      $("#sf-id").value = s.id;
      $("#sf-name").value = s.name;
      $("#sf-class").value = s.shipClass;
      $("#sf-faction").value = s.faction;
      $("#sf-player").checked = s.playerControlled;
      $("#sf-ai").checked = s.aiEnabled;
      $("#sf-px").value = s.px;
      $("#sf-py").value = s.py;
      $("#sf-pz").value = s.pz;
      $("#sf-ai-role").value = s.aiRole || "";
      $("#sf-engage").value = s.engagementRange || 60000;
      $("#sf-flee").value = s.fleeThreshold || 0.2;
    } else {
      title.textContent = "Add Ship";
      $("#sf-id").value = "";
      $("#sf-name").value = "";
      $("#sf-class").value = "";
      $("#sf-faction").value = "unsa";
      $("#sf-player").checked = false;
      $("#sf-ai").checked = false;
      $("#sf-px").value = 0;
      $("#sf-py").value = 0;
      $("#sf-pz").value = 0;
      $("#sf-ai-role").value = "";
      $("#sf-engage").value = 60000;
      $("#sf-flee").value = 0.2;
    }
    dlg.style.display = "flex";
  }

  _confirmShip() {
    const $ = (sel) => this.shadowRoot.querySelector(sel);
    const dlg = $("#ship-dialog");
    const ship = {
      id: $("#sf-id").value.trim(),
      name: $("#sf-name").value.trim(),
      shipClass: $("#sf-class").value,
      faction: $("#sf-faction").value,
      playerControlled: $("#sf-player").checked,
      aiEnabled: $("#sf-ai").checked,
      px: parseFloat($("#sf-px").value) || 0,
      py: parseFloat($("#sf-py").value) || 0,
      pz: parseFloat($("#sf-pz").value) || 0,
      aiRole: $("#sf-ai-role").value,
      engagementRange: parseInt($("#sf-engage").value) || 60000,
      fleeThreshold: parseFloat($("#sf-flee").value) || 0.2,
    };

    if (!ship.id) {
      this._showStatus("Ship ID is required", "error");
      return;
    }

    if (dlg._editIdx !== null) {
      this._ships[dlg._editIdx] = ship;
    } else {
      this._ships.push(ship);
    }
    dlg.style.display = "none";
    this._render();
  }

  // --- Objective dialog ---

  _openObjDialog(editIdx = null) {
    const $ = (sel) => this.shadowRoot.querySelector(sel);
    const dlg = $("#obj-dialog");
    const title = $("#obj-dialog-title");
    dlg._editIdx = editIdx;

    // Re-populate target dropdown with current ships
    const targetSel = $("#of-target");
    targetSel.innerHTML = '<option value="">--none--</option>' +
      this._ships.map(s => `<option value="${s.id}">${s.id} (${s.name})</option>`).join("");

    if (editIdx !== null) {
      const o = this._objectives[editIdx];
      title.textContent = "Edit Objective";
      $("#of-id").value = o.id;
      $("#of-type").value = o.type;
      $("#of-desc").value = o.description;
      $("#of-required").checked = o.required;
      targetSel.value = o.target || "";
      $("#of-range").value = o.range || 1000;
      $("#of-time").value = o.time || 60;
    } else {
      title.textContent = "Add Objective";
      $("#of-id").value = "";
      $("#of-type").value = OBJECTIVE_TYPES[0];
      $("#of-desc").value = "";
      $("#of-required").checked = true;
      targetSel.value = "";
      $("#of-range").value = 1000;
      $("#of-time").value = 60;
    }
    dlg.style.display = "flex";
  }

  _confirmObjective() {
    const $ = (sel) => this.shadowRoot.querySelector(sel);
    const dlg = $("#obj-dialog");
    const obj = {
      id: $("#of-id").value.trim(),
      type: $("#of-type").value,
      description: $("#of-desc").value.trim(),
      required: $("#of-required").checked,
      target: $("#of-target").value,
      range: parseInt($("#of-range").value) || 1000,
      time: parseInt($("#of-time").value) || 60,
    };

    if (!obj.id) {
      this._showStatus("Objective ID is required", "error");
      return;
    }

    if (dlg._editIdx !== null) {
      this._objectives[dlg._editIdx] = obj;
    } else {
      this._objectives.push(obj);
    }
    dlg.style.display = "none";
    this._render();
  }

  // --- Load scenario into editor ---

  async _confirmLoad() {
    const $ = (sel) => this.shadowRoot.querySelector(sel);
    const scenarioId = $("#ld-scenario").value;
    if (!scenarioId) return;

    $("#load-dialog").style.display = "none";
    this._showStatus("Loading...", "info");

    try {
      const resp = await wsClient.send("get_scenario_yaml", { scenario: scenarioId });
      if (resp?.ok && resp.data) {
        this._populateFromData(resp.data);
        this._render();
        this._showStatus(`Loaded: ${scenarioId}`, "success");
      } else {
        this._showStatus(resp?.error || "Failed to load scenario", "error");
      }
    } catch (e) {
      this._showStatus(`Load failed: ${e.message}`, "error");
    }
  }

  /** Populate editor state from parsed scenario data object */
  _populateFromData(data) {
    this._name = data.name || "";
    this._description = data.description || "";
    this._difficulty = data.difficulty || "medium";
    this._playerCount = data.player_count || "1";
    this._category = data.category || "combat";
    this._timeLimit = (data.mission && data.mission.time_limit) || 300;
    this._briefing = (data.mission && data.mission.briefing) || "";
    this._nextScenario = (data.mission && data.mission.next_scenario) || "";

    this._ships = (data.ships || []).map(s => ({
      id: s.id || "",
      name: s.name || "",
      shipClass: s.ship_class || s.class || "",
      faction: s.faction || "neutral",
      playerControlled: !!s.player_controlled,
      aiEnabled: !!s.ai_enabled,
      px: Math.round((s.position?.x || 0) / 1000),
      py: Math.round((s.position?.y || 0) / 1000),
      pz: Math.round((s.position?.z || 0) / 1000),
      aiRole: s.ai_behavior?.role || "",
      engagementRange: s.ai_behavior?.engagement_range || 60000,
      fleeThreshold: s.ai_behavior?.flee_threshold || 0.2,
    }));

    const objectives = (data.mission && data.mission.objectives) || [];
    this._objectives = objectives.map(o => ({
      id: o.id || "",
      type: o.type || "",
      description: o.description || "",
      required: o.required !== false,
      target: o.params?.target || "",
      range: o.params?.range || o.params?.escape_range || 1000,
      time: o.params?.time || 60,
    }));
  }

  // --- YAML generation ---

  _generateYaml() {
    let y = "";
    y += `name: "${this._esc(this._name)}"\n`;
    y += `description: "${this._esc(this._description)}"\n`;
    y += `difficulty: "${this._difficulty}"\n`;
    y += `player_count: "${this._playerCount}"\n`;
    y += `category: "${this._category}"\n`;
    y += `dt: 0.1\n\n`;

    y += `ships:\n`;
    for (const s of this._ships) {
      y += `  - id: "${s.id}"\n`;
      y += `    name: "${this._esc(s.name)}"\n`;
      y += `    ship_class: "${s.shipClass}"\n`;
      y += `    faction: "${s.faction}"\n`;
      if (s.playerControlled) y += `    player_controlled: true\n`;
      if (s.aiEnabled) y += `    ai_enabled: true\n`;
      // Convert km to meters
      y += `    position: {x: ${s.px * 1000}, y: ${s.py * 1000}, z: ${s.pz * 1000}}\n`;
      y += `    velocity: {x: 0, y: 0, z: 0}\n`;
      y += `    orientation: {pitch: 0, yaw: 0, roll: 0}\n`;
      if (s.aiEnabled && s.aiRole) {
        y += `    ai_behavior:\n`;
        y += `      role: "${s.aiRole}"\n`;
        y += `      engagement_range: ${s.engagementRange}\n`;
        y += `      flee_threshold: ${s.fleeThreshold}\n`;
        y += `      aggression: 0.7\n`;
      }
      y += `\n`;
    }

    y += `mission:\n`;
    y += `  name: "${this._esc(this._name)}"\n`;
    y += `  description: "${this._esc(this._description)}"\n`;
    if (this._timeLimit > 0) y += `  time_limit: ${this._timeLimit}\n`;
    if (this._nextScenario) y += `  next_scenario: "${this._nextScenario}"\n`;
    if (this._briefing) {
      y += `  briefing: |\n`;
      for (const line of this._briefing.split("\n")) {
        y += `    ${line}\n`;
      }
    }
    y += `\n`;
    y += `  objectives:\n`;
    for (const o of this._objectives) {
      y += `    - id: "${o.id}"\n`;
      y += `      type: "${o.type}"\n`;
      y += `      description: "${this._esc(o.description)}"\n`;
      y += `      required: ${o.required}\n`;
      y += `      params:\n`;
      if (TARGET_OBJECTIVES.includes(o.type) && o.target) {
        y += `        target: "${o.target}"\n`;
      }
      if (RANGE_OBJECTIVES.includes(o.type)) {
        const key = o.type === "escape_range" ? "escape_range" : "range";
        y += `        ${key}: ${o.range}\n`;
      }
      if (TIME_OBJECTIVES.includes(o.type)) {
        y += `        time: ${o.time}\n`;
      }
    }

    return y;
  }

  // --- Actions ---

  async _saveScenario() {
    const errors = this._getValidationErrors();
    if (errors.length > 0) {
      this._showStatus("Validation failed: " + errors[0], "error");
      return;
    }

    const yaml = this._generateYaml();
    const filename = this._slugify(this._name) + ".yaml";

    try {
      const resp = await wsClient.send("save_scenario", { filename, yaml_content: yaml });
      if (resp?.ok) {
        this._showStatus(`Saved: scenarios/${filename}`, "success");
        this._fetchScenarios(); // refresh dropdown
      } else {
        this._showStatus(resp?.error || "Save failed", "error");
      }
    } catch (e) {
      this._showStatus(`Save failed: ${e.message}`, "error");
    }
  }

  async _testMission() {
    const errors = this._getValidationErrors();
    if (errors.length > 0) {
      this._showStatus("Validation failed: " + errors[0], "error");
      return;
    }

    // Save first, then load
    const yaml = this._generateYaml();
    const filename = this._slugify(this._name) + ".yaml";

    try {
      let resp = await wsClient.send("save_scenario", { filename, yaml_content: yaml });
      if (!resp?.ok) {
        this._showStatus(resp?.error || "Save failed before test", "error");
        return;
      }

      // Strip .yaml extension for the scenario loader
      const scenarioId = filename.replace(/\.yaml$/, "");
      resp = await wsClient.send("load_scenario", { scenario: scenarioId });
      if (resp?.ok !== false) {
        document.dispatchEvent(new CustomEvent("scenario-loaded", {
          detail: resp,
          bubbles: true,
        }));
        this._showStatus("Mission loaded -- switching to HELM", "success");
      } else {
        this._showStatus(resp?.error || "Failed to load test mission", "error");
      }
    } catch (e) {
      this._showStatus(`Test failed: ${e.message}`, "error");
    }
  }

  _exportYaml() {
    const yaml = this._generateYaml();
    const blob = new Blob([yaml], { type: "text/yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (this._slugify(this._name) || "scenario") + ".yaml";
    a.click();
    URL.revokeObjectURL(url);
    this._showStatus("YAML exported", "success");
  }

  _validate() {
    const errors = this._getValidationErrors();
    if (errors.length === 0) {
      this._showStatus("Validation passed -- no issues found", "success");
    } else {
      this._showStatus("Issues: " + errors.join("; "), "error");
    }
  }

  _getValidationErrors() {
    const errors = [];
    if (!this._name.trim()) errors.push("Scenario name is required");
    if (this._ships.length === 0) errors.push("At least one ship is required");

    const shipIds = new Set();
    for (const s of this._ships) {
      if (!s.id) errors.push("All ships must have an ID");
      if (shipIds.has(s.id)) errors.push(`Duplicate ship ID: ${s.id}`);
      shipIds.add(s.id);
      if (!s.shipClass) errors.push(`Ship "${s.id}" needs a ship class`);
    }

    const hasPlayer = this._ships.some(s => s.playerControlled);
    if (!hasPlayer) errors.push("At least one ship must be player controlled");

    for (const o of this._objectives) {
      if (!o.id) errors.push("All objectives must have an ID");
      if (TARGET_OBJECTIVES.includes(o.type) && o.target && !shipIds.has(o.target)) {
        errors.push(`Objective "${o.id}" references unknown ship "${o.target}"`);
      }
    }

    return errors;
  }

  // --- Rendering helpers ---

  _renderShipCard(s, idx) {
    const tags = [];
    if (s.playerControlled) tags.push('<span class="tag tag-player">PLAYER</span>');
    if (s.aiEnabled) tags.push('<span class="tag tag-ai">AI</span>');
    return `
      <div class="card">
        <div class="card-header">
          <strong>${this._esc(s.id)}</strong>
          <span class="card-subtitle">${this._esc(s.name)}</span>
        </div>
        <div class="card-body">
          <span class="chip">${s.shipClass || "?"}</span>
          <span class="chip">${s.faction}</span>
          ${tags.join("")}
          <span class="card-pos">(${s.px}, ${s.py}, ${s.pz}) km</span>
        </div>
        <div class="card-actions">
          <button class="btn-sm ship-edit" data-idx="${idx}">EDIT</button>
          <button class="btn-sm btn-danger ship-remove" data-idx="${idx}">REMOVE</button>
        </div>
      </div>`;
  }

  _renderObjectiveCard(o, idx) {
    return `
      <div class="card">
        <div class="card-header">
          <strong>${this._esc(o.id)}</strong>
          <span class="chip">${o.type}</span>
          ${o.required ? '<span class="tag tag-req">REQUIRED</span>' : '<span class="tag tag-opt">OPTIONAL</span>'}
        </div>
        <div class="card-body">
          <span>${this._esc(o.description)}</span>
          ${o.target ? `<span class="chip">target: ${o.target}</span>` : ""}
        </div>
        <div class="card-actions">
          <button class="btn-sm obj-edit" data-idx="${idx}">EDIT</button>
          <button class="btn-sm btn-danger obj-remove" data-idx="${idx}">REMOVE</button>
        </div>
      </div>`;
  }

  _showStatus(msg, type = "info") {
    const el = this.shadowRoot.querySelector("#status-msg");
    if (!el) return;
    el.textContent = msg;
    el.className = `status-msg status-${type}`;
    clearTimeout(this._statusTimer);
    this._statusTimer = setTimeout(() => { el.textContent = ""; }, 6000);
  }

  _esc(str) {
    return (str || "").replace(/"/g, '\\"').replace(/</g, "&lt;");
  }

  _slugify(str) {
    return (str || "scenario")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "");
  }

  static _styles() {
    return `
      :host { display: block; height: 100%; overflow: hidden; }

      .editor-root {
        display: flex;
        flex-direction: column;
        height: 100%;
        gap: 8px;
        padding: 8px;
        box-sizing: border-box;
        font-family: var(--font-sans, "Inter", sans-serif);
        color: var(--text-primary, #e0e0e0);
        font-size: 0.85rem;
      }

      /* Metadata bar */
      .metadata-bar {
        background: var(--bg-panel, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 6px;
        padding: 12px;
        display: flex;
        flex-direction: column;
        gap: 8px;
        flex-shrink: 0;
      }
      .meta-row {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        align-items: end;
      }
      .metadata-bar label {
        display: flex;
        flex-direction: column;
        gap: 2px;
        font-size: 0.7rem;
        color: var(--text-secondary, #888899);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        min-width: 120px;
      }
      .metadata-bar label.wide { flex: 1; min-width: 200px; }
      .metadata-bar label.full-width { width: 100%; }
      .metadata-bar input, .metadata-bar select, .metadata-bar textarea {
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        color: var(--text-primary, #e0e0e0);
        padding: 6px 8px;
        font-size: 0.8rem;
        font-family: inherit;
      }
      .metadata-bar textarea { resize: vertical; min-height: 48px; }

      /* Columns */
      .columns {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        flex: 1;
        min-height: 0;
        overflow: hidden;
      }
      .column {
        display: flex;
        flex-direction: column;
        background: var(--bg-panel, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 6px;
        overflow: hidden;
      }
      .column-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        border-bottom: 1px solid var(--border-default, #2a2a3a);
      }
      .column-header h3 {
        margin: 0;
        font-size: 0.8rem;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        letter-spacing: 0.1em;
        color: var(--text-bright, #ffffff);
      }
      .card-list {
        flex: 1;
        overflow-y: auto;
        padding: 8px;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      /* Cards */
      .card {
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        padding: 8px 10px;
      }
      .card-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
      }
      .card-subtitle { color: var(--text-secondary, #888899); font-size: 0.75rem; }
      .card-body {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        align-items: center;
        font-size: 0.75rem;
        margin-bottom: 4px;
      }
      .card-pos { color: var(--text-dim, #555566); font-family: var(--font-mono, monospace); }
      .card-actions { display: flex; gap: 6px; justify-content: flex-end; }

      /* Chips and tags */
      .chip {
        background: rgba(255,255,255,0.06);
        padding: 2px 8px;
        border-radius: 3px;
        font-size: 0.7rem;
        font-family: var(--font-mono, monospace);
      }
      .tag {
        padding: 1px 6px;
        border-radius: 3px;
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .tag-player { background: rgba(0, 170, 255, 0.2); color: #00aaff; }
      .tag-ai { background: rgba(255, 170, 0, 0.2); color: #ffaa00; }
      .tag-req { background: rgba(255, 68, 68, 0.2); color: #ff4444; }
      .tag-opt { background: rgba(136, 136, 136, 0.15); color: #888; }

      .empty-hint {
        color: var(--text-dim, #555566);
        text-align: center;
        padding: 24px 12px;
        font-style: italic;
        font-size: 0.8rem;
      }

      /* Bottom bar */
      .bottom-bar {
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 8px 0;
        flex-shrink: 0;
      }
      .status-msg {
        margin-left: auto;
        font-size: 0.75rem;
        font-family: var(--font-mono, monospace);
      }
      .status-success { color: #00ff88; }
      .status-error { color: #ff4444; }
      .status-info { color: #00aaff; }

      /* Buttons */
      .btn {
        padding: 8px 16px;
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        cursor: pointer;
        transition: all 0.1s ease;
        text-transform: uppercase;
      }
      .btn-primary {
        background: rgba(0, 170, 255, 0.15);
        border-color: #00aaff;
        color: #00aaff;
      }
      .btn-primary:hover { background: rgba(0, 170, 255, 0.25); }
      .btn-secondary {
        background: transparent;
        color: var(--text-secondary, #888899);
      }
      .btn-secondary:hover {
        background: var(--bg-hover, #22222e);
        color: var(--text-primary, #e0e0e0);
      }
      .btn-add {
        background: rgba(0, 255, 136, 0.1);
        border-color: #00ff88;
        color: #00ff88;
        padding: 4px 12px;
        font-size: 0.7rem;
      }
      .btn-add:hover { background: rgba(0, 255, 136, 0.2); }
      .btn-sm {
        padding: 3px 10px;
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 3px;
        background: transparent;
        color: var(--text-secondary, #888899);
        font-size: 0.65rem;
        font-family: var(--font-mono, monospace);
        cursor: pointer;
      }
      .btn-sm:hover { background: var(--bg-hover, #22222e); color: var(--text-primary, #e0e0e0); }
      .btn-danger { border-color: #ff4444; color: #ff4444; }
      .btn-danger:hover { background: rgba(255, 68, 68, 0.15); }

      /* Dialogs */
      .dialog-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.7);
        z-index: 1000;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .dialog {
        background: var(--bg-panel, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 8px;
        padding: 20px;
        min-width: 400px;
        max-width: 520px;
      }
      .dialog h3 {
        margin: 0 0 12px;
        font-family: var(--font-mono, monospace);
        font-size: 0.9rem;
        letter-spacing: 0.08em;
        color: var(--text-bright, #fff);
      }
      .form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .form-grid label {
        display: flex;
        flex-direction: column;
        gap: 2px;
        font-size: 0.7rem;
        color: var(--text-secondary, #888899);
        text-transform: uppercase;
      }
      .form-grid label.wide { grid-column: 1 / -1; }
      .form-grid input, .form-grid select {
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        color: var(--text-primary, #e0e0e0);
        padding: 6px 8px;
        font-size: 0.8rem;
        font-family: inherit;
      }
      .checkbox-label {
        flex-direction: row !important;
        align-items: center;
        gap: 6px !important;
      }
      .checkbox-label input[type="checkbox"] {
        width: 16px;
        height: 16px;
        accent-color: #00aaff;
      }
      .dialog-buttons {
        display: flex;
        gap: 8px;
        justify-content: flex-end;
        margin-top: 16px;
      }

      @media (max-width: 768px) {
        .columns { grid-template-columns: 1fr; }
        .meta-row { flex-direction: column; }
        .dialog { min-width: 90vw; }
        .form-grid { grid-template-columns: 1fr; }
      }
    `;
  }
}

customElements.define("scenario-editor", ScenarioEditor);
export { ScenarioEditor };
