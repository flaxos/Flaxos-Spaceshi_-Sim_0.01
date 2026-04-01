/**
 * Ship Editor — Hull Configuration Sub-component
 * Left column: hull selector, class ID/name, description, dimensions, crew, mass, armor.
 */

const ARMOR_SECTIONS = ["fore", "aft", "port", "starboard", "dorsal", "ventral"];
const ARMOR_MATERIALS = ["composite_cermet", "steel_composite", "station_composite", "asteroid_rock"];

class ShipEditorHull extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._templates = []; // [{class_id, class_name, ...full config}]
  }

  connectedCallback() {
    this.render();
  }

  /** Set available templates (full ship class configs) for the hull selector dropdown */
  set templates(list) {
    this._templates = list || [];
    const sel = this.shadowRoot?.querySelector("#hull-selector");
    if (sel) this._populateSelector(sel);
  }

  /** Load a full ship class config into the editor fields */
  loadConfig(cfg) {
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("class-id").value = cfg.class_id || "";
    $("class-name").value = cfg.class_name || "";
    $("description").value = cfg.description || "";
    // Dimensions
    $("dim-length").value = cfg.dimensions?.length_m ?? "";
    $("dim-beam").value = cfg.dimensions?.beam_m ?? "";
    $("dim-draft").value = cfg.dimensions?.draft_m ?? "";
    // Crew
    $("crew-min").value = cfg.crew_complement?.minimum ?? "";
    $("crew-std").value = cfg.crew_complement?.standard ?? "";
    $("crew-max").value = cfg.crew_complement?.maximum ?? "";
    // Mass
    $("dry-mass").value = cfg.mass?.dry_mass ?? "";
    $("max-fuel").value = cfg.mass?.max_fuel ?? "";
    $("max-hull").value = cfg.mass?.max_hull_integrity ?? "";
    // Armor
    for (const s of ARMOR_SECTIONS) {
      const thick = $(`armor-${s}-thickness`);
      const mat = $(`armor-${s}-material`);
      if (thick) thick.value = cfg.armor?.[s]?.thickness_cm ?? 2;
      if (mat) mat.value = cfg.armor?.[s]?.material ?? "composite_cermet";
    }
  }

  /** Extract hull config from current field values */
  getConfig() {
    const $ = (id) => this.shadowRoot.getElementById(id);
    const armor = {};
    for (const s of ARMOR_SECTIONS) {
      armor[s] = {
        thickness_cm: parseFloat($(`armor-${s}-thickness`)?.value) || 0,
        material: $(`armor-${s}-material`)?.value || "composite_cermet",
      };
    }
    return {
      class_id: $("class-id").value.trim(),
      class_name: $("class-name").value.trim(),
      description: $("description").value.trim(),
      dimensions: {
        length_m: parseFloat($("dim-length").value) || 0,
        beam_m: parseFloat($("dim-beam").value) || 0,
        draft_m: parseFloat($("dim-draft").value) || 0,
      },
      crew_complement: {
        minimum: parseInt($("crew-min").value) || 0,
        standard: parseInt($("crew-std").value) || 0,
        maximum: parseInt($("crew-max").value) || 0,
      },
      mass: {
        dry_mass: parseFloat($("dry-mass").value) || 0,
        max_fuel: parseFloat($("max-fuel").value) || 0,
        max_hull_integrity: parseFloat($("max-hull").value) || 0,
      },
      armor,
    };
  }

  /** Validate hull fields, return array of error strings */
  validate() {
    const cfg = this.getConfig();
    const errors = [];
    if (!cfg.class_id) errors.push("Class ID is required");
    if (!cfg.class_name) errors.push("Class Name is required");
    if (cfg.mass.dry_mass <= 0) errors.push("Dry mass must be positive");
    if (cfg.mass.max_fuel <= 0) errors.push("Max fuel must be positive");
    if (cfg.dimensions.length_m <= 0) errors.push("Length must be positive");
    return errors;
  }

  _populateSelector(sel) {
    // Keep first two options (header + New Hull)
    while (sel.options.length > 2) sel.remove(2);
    for (const t of this._templates) {
      const opt = document.createElement("option");
      opt.value = t.class_id;
      opt.textContent = `${t.class_name} (${t.class_id})`;
      sel.appendChild(opt);
    }
  }

  _onTemplateSelect(classId) {
    if (!classId) return;
    if (classId === "__new__") {
      this._clearFields();
      this.dispatchEvent(new CustomEvent("template-loaded", { detail: { config: null }, bubbles: true, composed: true }));
      return;
    }
    const tpl = this._templates.find(t => t.class_id === classId);
    if (tpl) {
      this.loadConfig(tpl);
      this.dispatchEvent(new CustomEvent("template-loaded", { detail: { config: tpl }, bubbles: true, composed: true }));
    }
  }

  _clearFields() {
    this.shadowRoot.querySelectorAll("input, textarea, select").forEach(el => {
      if (el.id === "hull-selector") return;
      if (el.type === "number") el.value = "0";
      else if (el.tagName === "SELECT") el.selectedIndex = 0;
      else el.value = "";
    });
  }

  _emitChange() {
    this.dispatchEvent(new CustomEvent("hull-changed", { bubbles: true, composed: true }));
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; color: var(--text-primary, #e0e0e0); font-family: var(--font-sans, "Inter", sans-serif); font-size: 0.82rem; }
        .section { margin-bottom: 12px; }
        .section-title { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-dim, #555566); margin: 0 0 6px; border-bottom: 1px solid var(--border-subtle, #1a1a2a); padding-bottom: 4px; }
        label { display: block; font-size: 0.72rem; color: var(--text-secondary, #888899); margin: 4px 0 2px; }
        input, textarea, select { width: 100%; box-sizing: border-box; padding: 6px 8px; background: var(--bg-input, #1a1a24); border: 1px solid var(--border-default, #2a2a3a); border-radius: 4px; color: var(--text-primary, #e0e0e0); font-family: inherit; font-size: 0.8rem; }
        input:focus, textarea:focus, select:focus { outline: none; border-color: var(--status-info, #00aaff); }
        textarea { resize: vertical; min-height: 48px; }
        input[type="number"] { font-family: var(--font-mono, "JetBrains Mono", monospace); }
        .row { display: flex; gap: 8px; }
        .row > * { flex: 1; }
        .armor-row { display: grid; grid-template-columns: 80px 1fr 120px; gap: 6px; align-items: center; margin: 3px 0; }
        .armor-label { font-family: var(--font-mono, monospace); font-size: 0.72rem; text-transform: uppercase; color: var(--text-secondary, #888899); }
        .armor-val { font-family: var(--font-mono, monospace); font-size: 0.72rem; color: var(--text-dim, #666); min-width: 32px; text-align: right; }
        input[type="range"] { width: 100%; accent-color: var(--status-info, #00aaff); }
      </style>

      <div class="section">
        <div class="section-title">Hull Template</div>
        <select id="hull-selector">
          <option value="" disabled selected>Select template...</option>
          <option value="__new__">+ New Hull</option>
        </select>
      </div>

      <div class="section">
        <div class="section-title">Identity</div>
        <label for="class-id">Class ID</label>
        <input id="class-id" type="text" placeholder="e.g. light_cruiser">
        <label for="class-name">Class Name</label>
        <input id="class-name" type="text" placeholder="e.g. Light Cruiser">
        <label for="description">Description</label>
        <textarea id="description" rows="3" placeholder="Ship class description..."></textarea>
      </div>

      <div class="section">
        <div class="section-title">Dimensions (m)</div>
        <div class="row">
          <div><label for="dim-length">Length</label><input id="dim-length" type="number" min="1" step="0.1"></div>
          <div><label for="dim-beam">Beam</label><input id="dim-beam" type="number" min="1" step="0.1"></div>
          <div><label for="dim-draft">Draft</label><input id="dim-draft" type="number" min="1" step="0.1"></div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Crew Complement</div>
        <div class="row">
          <div><label for="crew-min">Min</label><input id="crew-min" type="number" min="1"></div>
          <div><label for="crew-std">Std</label><input id="crew-std" type="number" min="1"></div>
          <div><label for="crew-max">Max</label><input id="crew-max" type="number" min="1"></div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Mass</div>
        <div class="row">
          <div><label for="dry-mass">Dry Mass (kg)</label><input id="dry-mass" type="number" min="0" step="100"></div>
          <div><label for="max-fuel">Max Fuel (kg)</label><input id="max-fuel" type="number" min="0" step="100"></div>
        </div>
        <label for="max-hull">Max Hull Integrity</label>
        <input id="max-hull" type="number" min="0" step="10">
      </div>

      <div class="section">
        <div class="section-title">Armor</div>
        ${ARMOR_SECTIONS.map(s => `
          <div class="armor-row">
            <span class="armor-label">${s}</span>
            <div style="display:flex;gap:4px;align-items:center;">
              <input type="range" id="armor-${s}-thickness" min="0" max="20" step="0.5" value="2">
              <span class="armor-val" id="armor-${s}-val">2</span>cm
            </div>
            <select id="armor-${s}-material">
              ${ARMOR_MATERIALS.map(m => `<option value="${m}">${m.replace(/_/g, " ")}</option>`).join("")}
            </select>
          </div>
        `).join("")}
      </div>
    `;

    // Event: template selector
    this.shadowRoot.getElementById("hull-selector").addEventListener("change", (e) => {
      this._onTemplateSelect(e.target.value);
    });

    // Auto-generate class_id from class_name
    this.shadowRoot.getElementById("class-name").addEventListener("input", (e) => {
      const idField = this.shadowRoot.getElementById("class-id");
      idField.value = e.target.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
      this._emitChange();
    });

    // Armor slider value display
    for (const s of ARMOR_SECTIONS) {
      const slider = this.shadowRoot.getElementById(`armor-${s}-thickness`);
      const valSpan = this.shadowRoot.getElementById(`armor-${s}-val`);
      slider.addEventListener("input", () => {
        valSpan.textContent = slider.value;
        this._emitChange();
      });
    }

    // Emit change on any input
    this.shadowRoot.querySelectorAll("input, textarea, select").forEach(el => {
      if (el.id === "hull-selector") return;
      el.addEventListener("change", () => this._emitChange());
      if (el.type === "text" || el.tagName === "TEXTAREA") {
        el.addEventListener("input", () => this._emitChange());
      }
    });
  }
}

customElements.define("ship-editor-hull", ShipEditorHull);
export { ShipEditorHull, ARMOR_SECTIONS, ARMOR_MATERIALS };
