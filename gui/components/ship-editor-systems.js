/**
 * Ship Editor — Systems & Weapons Sub-component
 * Center column: system toggles with config fields, weapon mounts list.
 */

// System definitions: each system's configurable fields
const SYSTEM_DEFS = {
  propulsion: {
    label: "Propulsion",
    fields: [
      { key: "max_thrust", label: "Max Thrust (kN)", type: "number", step: 10, default: 280 },
      { key: "isp", label: "ISP (s)", type: "number", step: 100, default: 3500 },
      { key: "power_draw", label: "Power Draw", type: "number", step: 5, default: 50 },
      { key: "drive_type", label: "Drive Type", type: "select", options: ["epstein", "chemical", "ion", "nuclear_thermal"], default: "epstein" },
    ],
  },
  rcs: {
    label: "RCS",
    fields: [
      { key: "max_torque", label: "Max Torque (Nm)", type: "number", step: 5, default: 35 },
      { key: "attitude_rate", label: "Attitude Rate (deg/s)", type: "number", step: 1, default: 20 },
      { key: "thruster_count", label: "Thruster Count", type: "number", step: 2, default: 12 },
    ],
  },
  sensors: {
    label: "Sensors",
    fields: [
      { key: "power_draw", label: "Power Draw", type: "number", step: 5, default: 18 },
      { key: "passive.range", label: "Passive Range (km)", type: "number", step: 10000, default: 200000 },
      { key: "active.scan_range", label: "Active Range (km)", type: "number", step: 10000, default: 400000 },
      { key: "active.cooldown_time", label: "Scan Cooldown (s)", type: "number", step: 0.5, default: 5 },
      { key: "signature_base", label: "Signature Base", type: "number", step: 0.1, default: 0.9 },
    ],
  },
  navigation: {
    label: "Navigation",
    fields: [
      { key: "power_draw", label: "Power Draw", type: "number", step: 1, default: 8 },
    ],
  },
  targeting: {
    label: "Targeting",
    fields: [
      { key: "lock_time", label: "Lock Time (s)", type: "number", step: 0.1, default: 2 },
      { key: "lock_range", label: "Lock Range (km)", type: "number", step: 10000, default: 500000 },
    ],
  },
  combat: {
    label: "Combat",
    fields: [
      { key: "railguns", label: "Railguns", type: "number", step: 1, default: 1 },
      { key: "pdcs", label: "PDCs", type: "number", step: 1, default: 2 },
      { key: "torpedoes", label: "Torpedo Tubes", type: "number", step: 1, default: 0 },
      { key: "torpedo_capacity", label: "Torpedo Capacity", type: "number", step: 1, default: 0 },
    ],
  },
  ecm: {
    label: "ECM",
    fields: [
      { key: "jammer_power", label: "Jammer Power", type: "number", step: 1000, default: 30000 },
      { key: "chaff_count", label: "Chaff", type: "number", step: 1, default: 6 },
      { key: "flare_count", label: "Flares", type: "number", step: 1, default: 8 },
    ],
  },
  power_management: {
    label: "Power Management",
    fields: [
      { key: "primary.output", label: "Primary Output", type: "number", step: 10, default: 100 },
      { key: "secondary.output", label: "Secondary Output", type: "number", step: 10, default: 55 },
      { key: "tertiary.output", label: "Tertiary Output", type: "number", step: 5, default: 28 },
    ],
  },
  fleet_coord: {
    label: "Fleet Coordination",
    fields: [
      { key: "command_capable", label: "Command Capable", type: "checkbox", default: false },
      { key: "power_draw", label: "Power Draw", type: "number", step: 0.5, default: 1 },
    ],
  },
  science: {
    label: "Science",
    fields: [
      { key: "power_draw", label: "Power Draw", type: "number", step: 1, default: 5 },
    ],
  },
  comms: {
    label: "Communications",
    fields: [
      { key: "power_draw", label: "Power Draw", type: "number", step: 1, default: 3 },
    ],
  },
};

const WEAPON_TYPES = ["railgun", "pdc", "torpedo", "missile"];
const MOUNT_SECTIONS = ["fore", "aft", "dorsal", "ventral", "port", "starboard",
  "fore_dorsal", "fore_ventral", "midship_dorsal", "midship_port", "midship_starboard",
  "aft_dorsal", "aft_ventral", "fore_port", "fore_starboard"];

class ShipEditorSystems extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._weaponMounts = [];
    this._mountCounter = 0;
  }

  connectedCallback() {
    this.render();
  }

  /** Load systems + weapon_mounts from a full ship config */
  loadConfig(cfg) {
    const systems = cfg.systems || {};
    // Set enabled checkboxes and field values
    for (const [sysKey, def] of Object.entries(SYSTEM_DEFS)) {
      const cb = this.shadowRoot.getElementById(`sys-${sysKey}-enabled`);
      const sysData = systems[sysKey];
      const enabled = sysData?.enabled !== false && !!sysData;
      if (cb) cb.checked = enabled;

      // Show/hide detail panel
      const detail = this.shadowRoot.getElementById(`sys-${sysKey}-detail`);
      if (detail) detail.style.display = enabled ? "block" : "none";

      if (sysData) {
        for (const f of def.fields) {
          const el = this.shadowRoot.getElementById(`sys-${sysKey}-${f.key}`);
          if (!el) continue;
          const val = this._getNestedVal(sysData, f.key);
          if (f.type === "checkbox") el.checked = !!val;
          else el.value = val ?? f.default ?? "";
        }
      }
    }

    // Weapon mounts
    this._weaponMounts = (cfg.weapon_mounts || []).map((m, i) => ({ ...m, _idx: i }));
    this._mountCounter = this._weaponMounts.length;
    this._renderMounts();
  }

  /** Extract systems config + weapon_mounts from current field values */
  getConfig() {
    const systems = {};
    for (const [sysKey, def] of Object.entries(SYSTEM_DEFS)) {
      const cb = this.shadowRoot.getElementById(`sys-${sysKey}-enabled`);
      if (!cb?.checked) continue;
      const sysData = { enabled: true };
      for (const f of def.fields) {
        const el = this.shadowRoot.getElementById(`sys-${sysKey}-${f.key}`);
        if (!el) continue;
        let val;
        if (f.type === "checkbox") val = el.checked;
        else if (f.type === "number") val = parseFloat(el.value) || 0;
        else val = el.value;
        this._setNestedVal(sysData, f.key, val);
      }
      // Propulsion: mirror max_fuel from hull mass section
      if (sysKey === "propulsion") {
        sysData.max_fuel = sysData.max_fuel || 0;
        sysData.fuel_level = sysData.max_fuel;
      }
      systems[sysKey] = sysData;
    }

    // Collect weapon mounts from DOM
    const weapon_mounts = [];
    const container = this.shadowRoot.getElementById("mount-list");
    if (container) {
      container.querySelectorAll(".mount-entry").forEach(entry => {
        const mountId = entry.querySelector(".mount-id")?.value || "";
        const weaponType = entry.querySelector(".mount-type")?.value || "railgun";
        const section = entry.querySelector(".mount-section")?.value || "fore";
        weapon_mounts.push({
          mount_id: mountId,
          weapon_type: weaponType,
          placement: { section, position: { x: 0, y: 0, z: 0 } },
          firing_arc: { azimuth_min: -30, azimuth_max: 30, elevation_min: -20, elevation_max: 20 },
        });
      });
    }

    return { systems, weapon_mounts };
  }

  _getNestedVal(obj, path) {
    return path.split(".").reduce((o, k) => o?.[k], obj);
  }

  _setNestedVal(obj, path, val) {
    const keys = path.split(".");
    let cur = obj;
    for (let i = 0; i < keys.length - 1; i++) {
      if (!cur[keys[i]]) cur[keys[i]] = {};
      cur = cur[keys[i]];
    }
    cur[keys[keys.length - 1]] = val;
  }

  _emitChange() {
    this.dispatchEvent(new CustomEvent("systems-changed", { bubbles: true, composed: true }));
  }

  _addMount() {
    this._mountCounter++;
    const type = "railgun";
    const id = `${type}_${this._mountCounter}`;
    this._weaponMounts.push({
      mount_id: id,
      weapon_type: type,
      placement: { section: "fore", position: { x: 0, y: 0, z: 0 } },
      firing_arc: { azimuth_min: -30, azimuth_max: 30, elevation_min: -20, elevation_max: 20 },
    });
    this._renderMounts();
    this._emitChange();
  }

  _removeMount(idx) {
    this._weaponMounts.splice(idx, 1);
    this._renderMounts();
    this._emitChange();
  }

  _renderMounts() {
    const container = this.shadowRoot.getElementById("mount-list");
    if (!container) return;
    container.innerHTML = this._weaponMounts.map((m, i) => `
      <div class="mount-entry" data-idx="${i}">
        <input class="mount-id" type="text" value="${m.mount_id}" placeholder="mount_id">
        <select class="mount-type">
          ${WEAPON_TYPES.map(t => `<option value="${t}" ${t === m.weapon_type ? "selected" : ""}>${t}</option>`).join("")}
        </select>
        <select class="mount-section">
          ${MOUNT_SECTIONS.map(s => `<option value="${s}" ${s === m.placement?.section ? "selected" : ""}>${s}</option>`).join("")}
        </select>
        <button class="mount-remove" data-idx="${i}" title="Remove mount">X</button>
      </div>
    `).join("");

    // Bind remove buttons
    container.querySelectorAll(".mount-remove").forEach(btn => {
      btn.addEventListener("click", () => this._removeMount(parseInt(btn.dataset.idx)));
    });
    // Bind change events
    container.querySelectorAll("input, select").forEach(el => {
      el.addEventListener("change", () => this._emitChange());
    });
  }

  render() {
    const sysHtml = Object.entries(SYSTEM_DEFS).map(([sysKey, def]) => `
      <div class="sys-block">
        <label class="sys-toggle">
          <input type="checkbox" id="sys-${sysKey}-enabled" checked>
          <span>${def.label}</span>
        </label>
        <div class="sys-detail" id="sys-${sysKey}-detail">
          ${def.fields.map(f => {
            if (f.type === "select") {
              return `<label>${f.label}<select id="sys-${sysKey}-${f.key}">${f.options.map(o => `<option value="${o}" ${o === f.default ? "selected" : ""}>${o}</option>`).join("")}</select></label>`;
            }
            if (f.type === "checkbox") {
              return `<label class="inline"><input type="checkbox" id="sys-${sysKey}-${f.key}" ${f.default ? "checked" : ""}> ${f.label}</label>`;
            }
            return `<label>${f.label}<input type="number" id="sys-${sysKey}-${f.key}" step="${f.step || 1}" value="${f.default ?? 0}"></label>`;
          }).join("")}
        </div>
      </div>
    `).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; color: var(--text-primary, #e0e0e0); font-family: var(--font-sans, "Inter", sans-serif); font-size: 0.82rem; }
        .section-title { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-dim, #555566); margin: 0 0 6px; border-bottom: 1px solid var(--border-subtle, #1a1a2a); padding-bottom: 4px; }
        .sys-block { margin-bottom: 8px; padding: 6px 8px; background: var(--bg-secondary, #14141e); border-radius: 4px; border: 1px solid var(--border-subtle, #1a1a2a); }
        .sys-toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 600; font-size: 0.78rem; }
        .sys-toggle input[type="checkbox"] { accent-color: var(--status-info, #00aaff); }
        .sys-detail { margin-top: 6px; padding-left: 4px; display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; }
        .sys-detail label { display: flex; flex-direction: column; gap: 2px; font-size: 0.7rem; color: var(--text-secondary, #888899); }
        .sys-detail label.inline { flex-direction: row; align-items: center; gap: 6px; }
        input, select { width: 100%; box-sizing: border-box; padding: 4px 6px; background: var(--bg-input, #1a1a24); border: 1px solid var(--border-default, #2a2a3a); border-radius: 4px; color: var(--text-primary, #e0e0e0); font-family: inherit; font-size: 0.78rem; }
        input[type="number"] { font-family: var(--font-mono, monospace); }
        input:focus, select:focus { outline: none; border-color: var(--status-info, #00aaff); }

        /* Weapon mounts */
        .mounts-header { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; }
        .add-mount-btn { padding: 4px 10px; background: var(--bg-input, #1a1a24); border: 1px solid var(--status-info, #00aaff); border-radius: 4px; color: var(--status-info, #00aaff); cursor: pointer; font-size: 0.72rem; font-family: var(--font-mono, monospace); }
        .add-mount-btn:hover { background: rgba(0,170,255,0.1); }
        .mount-entry { display: grid; grid-template-columns: 1fr 90px 100px 28px; gap: 4px; margin: 4px 0; align-items: center; }
        .mount-entry input, .mount-entry select { padding: 4px 5px; font-size: 0.72rem; }
        .mount-remove { background: transparent; border: 1px solid var(--status-critical, #ff4444); color: var(--status-critical, #ff4444); border-radius: 3px; cursor: pointer; font-size: 0.72rem; padding: 2px 6px; font-family: var(--font-mono, monospace); }
        .mount-remove:hover { background: rgba(255,68,68,0.15); }
        #mount-list { max-height: 240px; overflow-y: auto; }
      </style>

      <div class="section-title">Systems</div>
      ${sysHtml}

      <div class="mounts-header">
        <div class="section-title" style="margin:0;border:none;padding:0;">Weapon Mounts</div>
        <button class="add-mount-btn" id="add-mount-btn">+ ADD MOUNT</button>
      </div>
      <div id="mount-list"></div>
    `;

    // Toggle system detail visibility
    this.shadowRoot.querySelectorAll(".sys-toggle input[type='checkbox']").forEach(cb => {
      cb.addEventListener("change", () => {
        const sysKey = cb.id.replace("sys-", "").replace("-enabled", "");
        const detail = this.shadowRoot.getElementById(`sys-${sysKey}-detail`);
        if (detail) detail.style.display = cb.checked ? "grid" : "none";
        this._emitChange();
      });
    });

    // Emit on any field change
    this.shadowRoot.querySelectorAll(".sys-detail input, .sys-detail select").forEach(el => {
      el.addEventListener("change", () => this._emitChange());
    });

    // Add mount button
    this.shadowRoot.getElementById("add-mount-btn").addEventListener("click", () => this._addMount());
  }
}

customElements.define("ship-editor-systems", ShipEditorSystems);
export { ShipEditorSystems, SYSTEM_DEFS, WEAPON_TYPES };
