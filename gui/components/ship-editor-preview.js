/**
 * Ship Editor — Preview & Stats Sub-component
 * Right column: computed stats (delta-v, acceleration, firepower, armor).
 * Also houses the damage_model editor.
 */

const DAMAGE_SUBSYSTEMS = ["propulsion", "rcs", "weapons", "sensors", "reactor", "life_support"];

class ShipEditorPreview extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._stats = {};
  }

  connectedCallback() {
    this.render();
  }

  /**
   * Update the preview panel with computed stats from the full config.
   * @param {object} fullConfig - The merged ship class config
   */
  updatePreview(fullConfig) {
    const mass = fullConfig.mass || {};
    const systems = fullConfig.systems || {};
    const armor = fullConfig.armor || {};
    const mounts = fullConfig.weapon_mounts || [];

    const dryMass = mass.dry_mass || 0;
    const fuel = mass.max_fuel || 0;
    const wetMass = dryMass + fuel;
    const isp = systems.propulsion?.isp || 0;
    const thrust = systems.propulsion?.max_thrust || 0;

    // Tsiolkovsky: dv = isp * g0 * ln(wet / dry)
    const g0 = 9.81;
    let deltaV = 0;
    if (dryMass > 0 && wetMass > dryMass && isp > 0) {
      deltaV = isp * g0 * Math.log(wetMass / dryMass);
    }

    // Max acceleration (m/s^2) at full fuel then convert to g
    const maxAccelMs2 = wetMass > 0 ? (thrust * 1000 / wetMass) : 0; // thrust in kN
    const maxAccelG = maxAccelMs2 / g0;

    // Firepower summary
    const railguns = mounts.filter(m => m.weapon_type === "railgun").length;
    const pdcs = mounts.filter(m => m.weapon_type === "pdc").length;
    const torpedoes = mounts.filter(m => m.weapon_type === "torpedo").length;
    const missiles = mounts.filter(m => m.weapon_type === "missile").length;

    // Average armor thickness
    const armorSections = Object.values(armor);
    const avgArmor = armorSections.length > 0
      ? armorSections.reduce((sum, s) => sum + (s.thickness_cm || 0), 0) / armorSections.length
      : 0;

    this._stats = { deltaV, maxAccelMs2, maxAccelG, railguns, pdcs, torpedoes, missiles, avgArmor, wetMass, dryMass, fuel };
    this._renderStats();
  }

  /** Load damage_model values from config */
  loadConfig(cfg) {
    const dm = cfg.damage_model || {};
    for (const sub of DAMAGE_SUBSYSTEMS) {
      const data = dm[sub] || {};
      const mhEl = this.shadowRoot.getElementById(`dm-${sub}-maxhp`);
      const critEl = this.shadowRoot.getElementById(`dm-${sub}-crit`);
      const ftEl = this.shadowRoot.getElementById(`dm-${sub}-ft`);
      if (mhEl) mhEl.value = data.max_health ?? 80;
      if (critEl) critEl.value = data.criticality ?? 3;
      if (ftEl) ftEl.value = data.failure_threshold ?? 0.2;
    }
  }

  /** Extract damage_model config from fields */
  getDamageModel() {
    const dm = {};
    for (const sub of DAMAGE_SUBSYSTEMS) {
      const maxHp = parseFloat(this.shadowRoot.getElementById(`dm-${sub}-maxhp`)?.value) || 80;
      const crit = parseFloat(this.shadowRoot.getElementById(`dm-${sub}-crit`)?.value) || 3;
      const ft = parseFloat(this.shadowRoot.getElementById(`dm-${sub}-ft`)?.value) || 0.2;
      dm[sub] = { max_health: maxHp, health: maxHp, criticality: crit, failure_threshold: ft };
    }
    return dm;
  }

  _renderStats() {
    const s = this._stats;
    const el = this.shadowRoot.getElementById("stats-body");
    if (!el) return;
    el.innerHTML = `
      <div class="stat-row">
        <span class="stat-label">WET MASS</span>
        <span class="stat-value">${this._fmt(s.wetMass)} kg</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">DRY MASS</span>
        <span class="stat-value">${this._fmt(s.dryMass)} kg</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">FUEL</span>
        <span class="stat-value">${this._fmt(s.fuel)} kg</span>
      </div>
      <div class="stat-row highlight">
        <span class="stat-label">DELTA-V</span>
        <span class="stat-value">${this._fmt(s.deltaV)} m/s</span>
      </div>
      <div class="stat-row highlight">
        <span class="stat-label">MAX ACCEL</span>
        <span class="stat-value">${s.maxAccelMs2.toFixed(1)} m/s2 (${s.maxAccelG.toFixed(2)} G)</span>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-row"><span class="stat-label">RAILGUNS</span><span class="stat-value">${s.railguns}</span></div>
      <div class="stat-row"><span class="stat-label">PDCs</span><span class="stat-value">${s.pdcs}</span></div>
      <div class="stat-row"><span class="stat-label">TORPEDO TUBES</span><span class="stat-value">${s.torpedoes}</span></div>
      <div class="stat-row"><span class="stat-label">MISSILE RACKS</span><span class="stat-value">${s.missiles}</span></div>
      <div class="stat-divider"></div>
      <div class="stat-row">
        <span class="stat-label">AVG ARMOR</span>
        <span class="stat-value">${s.avgArmor.toFixed(1)} cm</span>
      </div>
    `;
  }

  _fmt(n) {
    if (n == null || isNaN(n)) return "0";
    return n >= 1000 ? n.toLocaleString("en-US", { maximumFractionDigits: 0 }) : n.toFixed(1);
  }

  _emitChange() {
    this.dispatchEvent(new CustomEvent("preview-changed", { bubbles: true, composed: true }));
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; color: var(--text-primary, #e0e0e0); font-family: var(--font-sans, "Inter", sans-serif); font-size: 0.82rem; }
        .section-title { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-dim, #555566); margin: 0 0 6px; border-bottom: 1px solid var(--border-subtle, #1a1a2a); padding-bottom: 4px; }
        .stat-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.78rem; }
        .stat-label { font-family: var(--font-mono, monospace); font-size: 0.7rem; letter-spacing: 0.05em; color: var(--text-secondary, #888899); }
        .stat-value { font-family: var(--font-mono, monospace); font-size: 0.78rem; color: var(--text-primary, #e0e0e0); }
        .stat-row.highlight .stat-value { color: var(--status-info, #00aaff); font-weight: 600; }
        .stat-divider { height: 1px; background: var(--border-subtle, #1a1a2a); margin: 6px 0; }
        .stats-panel { background: var(--bg-secondary, #14141e); border: 1px solid var(--border-subtle, #1a1a2a); border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; }

        /* Damage model */
        .dm-grid { display: grid; grid-template-columns: 90px 1fr 1fr 1fr; gap: 3px 6px; align-items: center; font-size: 0.7rem; }
        .dm-header { font-family: var(--font-mono, monospace); font-size: 0.65rem; color: var(--text-dim, #555566); text-transform: uppercase; letter-spacing: 0.05em; }
        .dm-label { font-family: var(--font-mono, monospace); color: var(--text-secondary, #888899); text-transform: uppercase; }
        input[type="number"] { width: 100%; box-sizing: border-box; padding: 3px 5px; background: var(--bg-input, #1a1a24); border: 1px solid var(--border-default, #2a2a3a); border-radius: 3px; color: var(--text-primary, #e0e0e0); font-family: var(--font-mono, monospace); font-size: 0.72rem; }
        input:focus { outline: none; border-color: var(--status-info, #00aaff); }
      </style>

      <div class="section-title">Computed Stats</div>
      <div class="stats-panel" id="stats-body">
        <div class="stat-row"><span class="stat-label">Load a template or fill fields...</span></div>
      </div>

      <div class="section-title">Damage Model</div>
      <div class="dm-grid">
        <span class="dm-header">System</span>
        <span class="dm-header">Max HP</span>
        <span class="dm-header">Crit</span>
        <span class="dm-header">Fail %</span>
        ${DAMAGE_SUBSYSTEMS.map(sub => `
          <span class="dm-label">${sub.replace("_", " ")}</span>
          <input type="number" id="dm-${sub}-maxhp" min="0" step="10" value="80">
          <input type="number" id="dm-${sub}-crit" min="0" max="10" step="0.5" value="3">
          <input type="number" id="dm-${sub}-ft" min="0" max="1" step="0.05" value="0.2">
        `).join("")}
      </div>
    `;

    // Emit change on damage model edits
    this.shadowRoot.querySelectorAll(".dm-grid input").forEach(el => {
      el.addEventListener("change", () => this._emitChange());
    });
  }
}

customElements.define("ship-editor-preview", ShipEditorPreview);
export { ShipEditorPreview, DAMAGE_SUBSYSTEMS };
