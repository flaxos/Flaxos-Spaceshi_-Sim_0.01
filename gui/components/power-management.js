/**
 * Power Management Panel
 * Allocation sliders + reactor meters.
 *
 * Tier awareness:
 *   MANUAL:     Raw kW sliders per system. Voltage/amperage readouts. Direct reactor output control.
 *   RAW:        Per-system power allocation with exact kW numbers. Full reactor status.
 *   ARCADE:     Percentage sliders (0-100%). Preset profiles prominent. AUTO-BALANCE button.
 *   CPU-ASSIST: Read-only summary of current allocation. Auto-ops proposals if changes needed.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const DEFAULT_ALLOCATION = {
  primary: 0.5,
  secondary: 0.3,
  tertiary: 0.2,
};

// Preset power profiles for ARCADE tier
const POWER_PRESETS = {
  combat:    { primary: 0.4, secondary: 0.4, tertiary: 0.2, label: "COMBAT",    desc: "Balanced weapons + engines" },
  cruise:    { primary: 0.6, secondary: 0.2, tertiary: 0.2, label: "CRUISE",    desc: "Maximum propulsion efficiency" },
  stealth:   { primary: 0.2, secondary: 0.2, tertiary: 0.6, label: "STEALTH",   desc: "Minimum emissions" },
  emergency: { primary: 0.5, secondary: 0.5, tertiary: 0.0, label: "EMERGENCY", desc: "All power to critical systems" },
};

class PowerManagement extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tierHandler = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._applyTier();
    this._tierHandler = () => this._applyTier();
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  /** Re-render entire panel when tier changes — layout differs significantly */
  _applyTier() {
    this.render();
    this._updateDisplay();
  }

  _getTier() {
    return window.controlTier || "arcade";
  }

  render() {
    const tier = this._getTier();
    if (tier === "manual") {
      this._renderManual();
    } else if (tier === "raw") {
      this._renderRaw();
    } else if (tier === "cpu-assist") {
      this._renderCpuAssist();
    } else {
      this._renderArcade();
    }
  }

  // ---------------------------------------------------------------------------
  // MANUAL tier: raw kW sliders, voltage/amperage, direct reactor output
  // ---------------------------------------------------------------------------

  _renderManual() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._manualStyles()}</style>
      <div class="section">
        <div class="section-title">BUS ALLOCATION [kW]</div>
        <div id="allocation-list"></div>
        <div class="allocation-footer">
          <span id="allocation-total" class="mono">TOTAL: 0.0 kW</span>
          <button class="apply-btn" id="apply-btn">TX ALLOC</button>
        </div>
        <div class="allocation-feedback" id="allocation-feedback"></div>
      </div>
      <div class="section">
        <div class="section-title">REACTOR STATUS</div>
        <div id="reactor-list"></div>
      </div>
    `;
    this._renderManualAllocation();
    this._renderManualReactors();
    this._attachHandlers();
  }

  _manualStyles() {
    return `
      :host {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: #ffe0b0;
      }
      .section-title {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: #ff8800;
        border-bottom: 1px solid #ff880044;
      }
      .allocation-row {
        grid-template-columns: 90px 1fr 70px;
      }
      .allocation-label { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; font-size: 0.75rem; }
      .allocation-value { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.75rem; color: #ffe0b0; }
      input[type="range"] { accent-color: #ff8800; }
      .apply-btn { background: #ff8800; color: #0a0a0f; font-family: var(--font-mono, "JetBrains Mono", monospace); border-radius: 0; text-transform: uppercase; letter-spacing: 1px; }
      .mono { font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .reactor-card { border: 1px solid #ff880033; border-radius: 0; }
      .reactor-name { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; }
      .meter { border-radius: 0; }
      .meter-fill { border-radius: 0; background: #ff8800; }
      .meter-label { font-family: var(--font-mono, "JetBrains Mono", monospace); color: #ffe0b0; }
      .reactor-detail { font-family: var(--font-mono, "JetBrains Mono", monospace); color: #ffe0b0; }
      .voltage-row {
        display: flex;
        justify-content: space-between;
        font-size: 0.7rem;
        color: #ffe0b0;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        padding: 2px 0;
      }
      .voltage-label { color: #ff880088; text-transform: uppercase; }
    `;
  }

  _renderManualAllocation() {
    const allocation = this._getAllocation();
    const power = this._getPowerState();
    const totalCapacity = this._getTotalCapacity();
    const busKeys = Object.keys(allocation);
    const list = this.shadowRoot.getElementById("allocation-list");

    list.innerHTML = busKeys.map((bus) => {
      const fraction = allocation[bus] || 0;
      const kwValue = (fraction * totalCapacity).toFixed(1);
      return `
        <div class="allocation-row">
          <div class="allocation-label">${bus}</div>
          <input type="range" min="0" max="${totalCapacity.toFixed(0)}" step="0.1"
                 value="${kwValue}" data-bus="${bus}" />
          <div class="allocation-value" data-value="${bus}">${kwValue} kW</div>
        </div>
      `;
    }).join("");

    list.querySelectorAll("input[type='range']").forEach((input) => {
      input.addEventListener("input", () => {
        const bus = input.dataset.bus;
        const valueEl = this.shadowRoot.querySelector(`[data-value="${bus}"]`);
        if (valueEl) {
          valueEl.textContent = `${Number(input.value).toFixed(1)} kW`;
        }
        this._updateManualTotal();
      });
    });

    this._updateManualTotal();
  }

  _renderManualReactors() {
    const list = this.shadowRoot.getElementById("reactor-list");
    const reactors = this._getReactors();
    const reactorEntries = Object.values(reactors);

    if (!reactorEntries.length) {
      list.innerHTML = `<div class="reactor-card">NO REACTOR DATA</div>`;
      return;
    }

    list.innerHTML = reactorEntries.map((reactor) => {
      const capacity = reactor.capacity || 0;
      const available = reactor.available || 0;
      const availPct = capacity > 0 ? (available / capacity) * 100 : 0;
      const temp = reactor.temperature ?? 0;
      const thermal = reactor.thermal_limit ?? 0;
      const tempPct = thermal > 0 ? (temp / thermal) * 100 : 0;
      const fuelPct = reactor.fuel_percent ?? null;
      // Derive voltage/amperage from power data for manual display
      const voltage = capacity > 0 ? (300 + (available / capacity) * 200).toFixed(1) : "0.0";
      const amperage = voltage > 0 ? (available * 1000 / parseFloat(voltage)).toFixed(1) : "0.0";

      return `
        <div class="reactor-card">
          <div class="reactor-header">
            <div class="reactor-name">${reactor.name || "REACTOR"}</div>
            <div class="reactor-status ${this._statusClass(reactor.status)}">${reactor.status || "NOMINAL"}</div>
          </div>
          <div class="meter"><div class="meter-fill ${this._meterClass(availPct)}" style="width:${availPct}%"></div></div>
          <div class="meter-label"><span>OUTPUT</span><span>${available.toFixed(1)} / ${capacity.toFixed(1)} kW</span></div>
          <div class="meter"><div class="meter-fill ${this._meterClass(tempPct)}" style="width:${Math.min(100, tempPct)}%"></div></div>
          <div class="meter-label"><span>THERMAL</span><span>${temp.toFixed(1)} / ${thermal.toFixed(1)} C</span></div>
          <div class="voltage-row"><span class="voltage-label">Voltage</span><span>${voltage} V</span></div>
          <div class="voltage-row"><span class="voltage-label">Amperage</span><span>${amperage} A</span></div>
          <div class="reactor-detail"><span>FUEL</span><span>${fuelPct === null ? "--" : `${fuelPct.toFixed(1)}%`}</span></div>
        </div>
      `;
    }).join("");
  }

  _updateManualTotal() {
    const totalEl = this.shadowRoot.getElementById("allocation-total");
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
    const totalKw = inputs.reduce((sum, inp) => sum + Number(inp.value || 0), 0);
    totalEl.textContent = `TOTAL: ${totalKw.toFixed(1)} kW`;
    applyBtn.disabled = totalKw <= 0;
  }

  // ---------------------------------------------------------------------------
  // RAW tier: percentage-based but shows exact kW alongside. Full reactor detail.
  // ---------------------------------------------------------------------------

  _renderRaw() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._rawStyles()}</style>
      <div class="section">
        <div class="section-title">Power Allocation</div>
        <div id="allocation-list"></div>
        <div class="allocation-footer">
          <span id="allocation-total">Total: 0%</span>
          <button class="apply-btn" id="apply-btn">Apply Allocation</button>
        </div>
        <div class="allocation-feedback" id="allocation-feedback"></div>
      </div>
      <div class="section">
        <div class="section-title">Reactors</div>
        <div id="reactor-list"></div>
      </div>
    `;
    this._renderRawAllocation();
    this._renderRawReactors();
    this._attachHandlers();
  }

  _rawStyles() {
    return `
      .section-title {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: #ff4444;
        border-bottom: 1px solid #ff444433;
      }
      .allocation-row {
        grid-template-columns: 100px 1fr 80px;
        border-radius: 0;
      }
      .allocation-label { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; font-size: 0.8rem; }
      .allocation-value { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.8rem; }
      input[type="range"] { accent-color: #ff4444; }
      .apply-btn { background: #ff4444; border-radius: 0; font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .reactor-card { border-radius: 0; border: 1px solid #ff444422; }
      .reactor-name { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; }
      .meter { border-radius: 0; }
      .meter-fill { border-radius: 0; }
    `;
  }

  _renderRawAllocation() {
    const allocation = this._getAllocation();
    const totalCapacity = this._getTotalCapacity();
    const busKeys = Object.keys(allocation);
    const list = this.shadowRoot.getElementById("allocation-list");

    list.innerHTML = busKeys.map((bus) => {
      const fraction = allocation[bus] || 0;
      const pct = Math.round(fraction * 100);
      const kwValue = (fraction * totalCapacity).toFixed(1);
      return `
        <div class="allocation-row">
          <div class="allocation-label">${bus}</div>
          <input type="range" min="0" max="100" value="${pct}" data-bus="${bus}" />
          <div class="allocation-value" data-value="${bus}">${pct}% (${kwValue} kW)</div>
        </div>
      `;
    }).join("");

    list.querySelectorAll("input[type='range']").forEach((input) => {
      input.addEventListener("input", () => {
        const bus = input.dataset.bus;
        const valueEl = this.shadowRoot.querySelector(`[data-value="${bus}"]`);
        const totalCapacity = this._getTotalCapacity();
        const pct = Number(input.value);
        const kw = ((pct / 100) * totalCapacity).toFixed(1);
        if (valueEl) {
          valueEl.textContent = `${pct}% (${kw} kW)`;
        }
        this._updateTotal();
      });
    });

    this._updateTotal();
  }

  _renderRawReactors() {
    const list = this.shadowRoot.getElementById("reactor-list");
    const reactors = this._getReactors();
    const reactorEntries = Object.values(reactors);

    if (!reactorEntries.length) {
      list.innerHTML = `<div class="reactor-card">No reactor data.</div>`;
      return;
    }

    list.innerHTML = reactorEntries.map((reactor) => {
      const capacity = reactor.capacity || 0;
      const available = reactor.available || 0;
      const availPct = capacity > 0 ? (available / capacity) * 100 : 0;
      const temp = reactor.temperature ?? 0;
      const thermal = reactor.thermal_limit ?? 0;
      const tempPct = thermal > 0 ? (temp / thermal) * 100 : 0;
      const fuelPct = reactor.fuel_percent ?? null;

      return `
        <div class="reactor-card">
          <div class="reactor-header">
            <div class="reactor-name">${reactor.name || "reactor"}</div>
            <div class="reactor-status ${this._statusClass(reactor.status)}">${reactor.status || "nominal"}</div>
          </div>
          <div class="meter"><div class="meter-fill ${this._meterClass(availPct)}" style="width:${availPct}%"></div></div>
          <div class="meter-label"><span>Output</span><span>${available.toFixed(1)} / ${capacity.toFixed(1)} kW (${availPct.toFixed(0)}%)</span></div>
          <div class="meter"><div class="meter-fill ${this._meterClass(tempPct)}" style="width:${Math.min(100, tempPct)}%"></div></div>
          <div class="meter-label"><span>Temperature</span><span>${temp.toFixed(1)} / ${thermal.toFixed(1)} C (${tempPct.toFixed(0)}%)</span></div>
          <div class="reactor-detail"><span>Fuel</span><span>${fuelPct === null ? "--" : `${fuelPct.toFixed(1)}%`}</span></div>
        </div>
      `;
    }).join("");
  }

  // ---------------------------------------------------------------------------
  // ARCADE tier: percentage sliders, preset profiles, auto-balance
  // ---------------------------------------------------------------------------

  _renderArcade() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._arcadeStyles()}</style>
      <div class="section">
        <div class="section-title">Quick Profiles</div>
        <div class="preset-grid" id="preset-grid">
          ${Object.entries(POWER_PRESETS).map(([key, p]) => `
            <button class="preset-btn" data-preset="${key}" title="${p.desc}">
              <span class="preset-label">${p.label}</span>
              <span class="preset-desc">${p.desc}</span>
            </button>
          `).join("")}
        </div>
      </div>
      <div class="section">
        <div class="section-title">Power Allocation</div>
        <div id="allocation-list"></div>
        <div class="allocation-footer">
          <span id="allocation-total">Total: 0%</span>
          <div class="arcade-btn-group">
            <button class="auto-balance-btn" id="auto-balance-btn">AUTO-BALANCE</button>
            <button class="apply-btn" id="apply-btn">Apply</button>
          </div>
        </div>
        <div class="allocation-feedback" id="allocation-feedback"></div>
      </div>
      <div class="section">
        <div class="section-title">Reactor Status</div>
        <div id="reactor-list"></div>
      </div>
    `;
    this._renderArcadeAllocation();
    this._renderArcadeReactors();
    this._attachArcadeHandlers();
  }

  _arcadeStyles() {
    return `
      .preset-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-bottom: 12px;
      }
      .preset-btn {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2px;
        padding: 10px 8px;
        border-radius: 8px;
        border: 1px solid rgba(68, 136, 255, 0.25);
        background: rgba(68, 136, 255, 0.06);
        color: var(--text-primary, #e0e0e0);
        cursor: pointer;
        transition: all 0.15s ease;
      }
      .preset-btn:hover {
        border-color: var(--status-info, #4488ff);
        background: rgba(68, 136, 255, 0.15);
        box-shadow: 0 0 8px rgba(68, 136, 255, 0.3);
      }
      .preset-btn.active {
        border-color: var(--status-info, #4488ff);
        background: rgba(68, 136, 255, 0.2);
        box-shadow: 0 0 12px rgba(68, 136, 255, 0.4);
      }
      .preset-label {
        font-weight: 700;
        font-size: 0.85rem;
        letter-spacing: 1px;
      }
      .preset-desc {
        font-size: 0.65rem;
        color: var(--text-dim, #666);
        text-align: center;
      }
      .arcade-btn-group {
        display: flex;
        gap: 6px;
      }
      .auto-balance-btn {
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid rgba(0, 255, 136, 0.3);
        background: rgba(0, 255, 136, 0.08);
        color: var(--status-nominal, #00ff88);
        font-weight: 600;
        font-size: 0.75rem;
        cursor: pointer;
        transition: all 0.15s ease;
        letter-spacing: 0.5px;
      }
      .auto-balance-btn:hover {
        background: rgba(0, 255, 136, 0.2);
        border-color: var(--status-nominal, #00ff88);
      }
      .reactor-pct-readout {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--status-nominal, #00ff88);
        text-align: center;
        margin-bottom: 4px;
      }
      .reactor-pct-readout.warning { color: var(--status-warning, #ffaa00); }
      .reactor-pct-readout.error { color: var(--status-critical, #ff4444); }
    `;
  }

  _renderArcadeAllocation() {
    const allocation = this._getAllocation();
    const busKeys = Object.keys(allocation);
    const list = this.shadowRoot.getElementById("allocation-list");

    list.innerHTML = busKeys.map((bus) => {
      const value = Math.round((allocation[bus] || 0) * 100);
      return `
        <div class="allocation-row">
          <div class="allocation-label">${bus}</div>
          <input type="range" min="0" max="100" value="${value}" data-bus="${bus}" />
          <div class="allocation-value" data-value="${bus}">${value}%</div>
        </div>
      `;
    }).join("");

    list.querySelectorAll("input[type='range']").forEach((input) => {
      input.addEventListener("input", () => {
        const bus = input.dataset.bus;
        const valueEl = this.shadowRoot.querySelector(`[data-value="${bus}"]`);
        if (valueEl) {
          valueEl.textContent = `${input.value}%`;
        }
        this._updateTotal();
      });
    });

    this._updateTotal();
  }

  _renderArcadeReactors() {
    const list = this.shadowRoot.getElementById("reactor-list");
    const reactors = this._getReactors();
    const reactorEntries = Object.values(reactors);

    if (!reactorEntries.length) {
      list.innerHTML = `<div class="reactor-card">No reactor data.</div>`;
      return;
    }

    list.innerHTML = reactorEntries.map((reactor) => {
      const capacity = reactor.capacity || 0;
      const available = reactor.available || 0;
      const availPct = capacity > 0 ? (available / capacity) * 100 : 0;
      const temp = reactor.temperature ?? 0;
      const thermal = reactor.thermal_limit ?? 0;
      const tempPct = thermal > 0 ? (temp / thermal) * 100 : 0;
      const pctClass = availPct < 25 ? "error" : availPct < 50 ? "warning" : "";

      return `
        <div class="reactor-card">
          <div class="reactor-header">
            <div class="reactor-name">${reactor.name || "reactor"}</div>
            <div class="reactor-status ${this._statusClass(reactor.status)}">${reactor.status || "nominal"}</div>
          </div>
          <div class="reactor-pct-readout ${pctClass}">${availPct.toFixed(0)}% capacity</div>
          <div class="meter"><div class="meter-fill ${this._meterClass(availPct)}" style="width:${availPct}%"></div></div>
          <div class="meter-label"><span>Available</span><span>${availPct.toFixed(0)}%</span></div>
          <div class="meter"><div class="meter-fill ${this._meterClass(tempPct)}" style="width:${Math.min(100, tempPct)}%"></div></div>
          <div class="meter-label"><span>Temperature</span><span>${tempPct.toFixed(0)}%</span></div>
        </div>
      `;
    }).join("");
  }

  _attachArcadeHandlers() {
    this._attachHandlers();

    // Preset buttons
    this.shadowRoot.querySelectorAll(".preset-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.preset;
        const preset = POWER_PRESETS[key];
        if (!preset) return;

        // Apply preset values to sliders
        const inputs = this.shadowRoot.querySelectorAll("input[type='range']");
        inputs.forEach(input => {
          const bus = input.dataset.bus;
          if (preset[bus] !== undefined) {
            input.value = Math.round(preset[bus] * 100);
            const valueEl = this.shadowRoot.querySelector(`[data-value="${bus}"]`);
            if (valueEl) valueEl.textContent = `${input.value}%`;
          }
        });
        this._updateTotal();

        // Highlight active preset
        this.shadowRoot.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        // Auto-apply preset
        this._applyAllocation();
      });
    });

    // Auto-balance button
    const autoBtn = this.shadowRoot.getElementById("auto-balance-btn");
    if (autoBtn) {
      autoBtn.addEventListener("click", () => {
        const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
        const balanced = Math.round(100 / inputs.length);
        inputs.forEach(input => {
          input.value = balanced;
          const valueEl = this.shadowRoot.querySelector(`[data-value="${input.dataset.bus}"]`);
          if (valueEl) valueEl.textContent = `${balanced}%`;
        });
        this._updateTotal();
        this._applyAllocation();
        this._setAllocationFeedback("Auto-balanced evenly.", "success");
      });
    }
  }

  // ---------------------------------------------------------------------------
  // CPU-ASSIST tier: read-only summary, auto-ops proposals
  // ---------------------------------------------------------------------------

  _renderCpuAssist() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._cpuAssistStyles()}</style>
      <div class="section">
        <div class="section-title">Power Allocation</div>
        <div class="assist-note">Auto-ops is managing power distribution.</div>
        <div id="allocation-summary"></div>
      </div>
      <div class="section">
        <div class="section-title">Reactor Summary</div>
        <div id="reactor-list"></div>
      </div>
    `;
    this._renderCpuAssistSummary();
    this._renderCpuAssistReactors();
  }

  _cpuAssistStyles() {
    return `
      .section-title {
        color: #bb88ff;
        border-bottom: 1px solid #bb88ff33;
      }
      .assist-note {
        font-size: 0.75rem;
        color: var(--text-dim, #666);
        font-style: italic;
        margin-bottom: 10px;
      }
      .summary-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        background: rgba(128, 0, 255, 0.04);
        border-radius: 6px;
        margin-bottom: 6px;
      }
      .summary-label {
        font-size: 0.85rem;
        color: var(--text-primary, #e0e0e0);
        text-transform: capitalize;
        width: 100px;
        flex-shrink: 0;
      }
      .summary-bar {
        flex: 1;
        height: 10px;
        background: var(--bg-input, #1a1a24);
        border-radius: 5px;
        overflow: hidden;
      }
      .summary-fill {
        height: 100%;
        background: #bb88ff;
        border-radius: 5px;
        transition: width 0.3s ease;
      }
      .summary-pct {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.8rem;
        color: #bb88ff;
        width: 40px;
        text-align: right;
        flex-shrink: 0;
      }
      .reactor-summary-card {
        background: rgba(128, 0, 255, 0.04);
        border-radius: 6px;
        padding: 12px;
        margin-bottom: 8px;
      }
      .reactor-summary-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
      }
      .reactor-summary-name {
        font-size: 0.9rem;
        font-weight: 600;
        text-transform: capitalize;
      }
      .reactor-summary-status {
        font-size: 0.75rem;
        padding: 2px 8px;
        border-radius: 6px;
      }
      .reactor-summary-status.nominal {
        background: rgba(0, 255, 136, 0.15);
        color: var(--status-nominal, #00ff88);
      }
      .reactor-summary-status.warning {
        background: rgba(255, 170, 0, 0.15);
        color: var(--status-warning, #ffaa00);
      }
      .reactor-summary-status.error {
        background: rgba(255, 68, 68, 0.15);
        color: var(--status-critical, #ff4444);
      }
      .reactor-summary-stat {
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
        padding: 2px 0;
      }
      .reactor-summary-stat .label { color: var(--text-dim, #666); }
      .reactor-summary-stat .value { color: var(--text-secondary, #aaa); }
    `;
  }

  _renderCpuAssistSummary() {
    const allocation = this._getAllocation();
    const container = this.shadowRoot.getElementById("allocation-summary");
    if (!container) return;

    const busKeys = Object.keys(allocation);
    container.innerHTML = busKeys.map(bus => {
      const pct = Math.round((allocation[bus] || 0) * 100);
      return `
        <div class="summary-row">
          <span class="summary-label">${bus}</span>
          <div class="summary-bar"><div class="summary-fill" style="width:${pct}%"></div></div>
          <span class="summary-pct">${pct}%</span>
        </div>
      `;
    }).join("");
  }

  _renderCpuAssistReactors() {
    const list = this.shadowRoot.getElementById("reactor-list");
    const reactors = this._getReactors();
    const reactorEntries = Object.values(reactors);

    if (!reactorEntries.length) {
      list.innerHTML = `<div class="assist-note">No reactor data available.</div>`;
      return;
    }

    list.innerHTML = reactorEntries.map(reactor => {
      const capacity = reactor.capacity || 0;
      const available = reactor.available || 0;
      const availPct = capacity > 0 ? (available / capacity) * 100 : 0;
      const fuelPct = reactor.fuel_percent ?? null;
      const statusLabel = (reactor.status || "nominal").toUpperCase();
      const statusClass = this._statusClass(reactor.status) || "nominal";

      return `
        <div class="reactor-summary-card">
          <div class="reactor-summary-header">
            <span class="reactor-summary-name">${reactor.name || "Reactor"}</span>
            <span class="reactor-summary-status ${statusClass}">${statusLabel}</span>
          </div>
          <div class="reactor-summary-stat">
            <span class="label">Capacity</span>
            <span class="value">${availPct.toFixed(0)}% available</span>
          </div>
          <div class="reactor-summary-stat">
            <span class="label">Fuel</span>
            <span class="value">${fuelPct === null ? "--" : `${fuelPct.toFixed(0)}%`}</span>
          </div>
        </div>
      `;
    }).join("");
  }

  // ---------------------------------------------------------------------------
  // Shared methods
  // ---------------------------------------------------------------------------

  _baseStyles() {
    return `
      :host {
        display: block;
        padding: 16px;
        font-family: var(--font-sans, "Inter", sans-serif);
        color: var(--text-primary, #e0e0e0);
      }
      .section { margin-bottom: 16px; }
      .section-title {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-dim, #889);
        margin-bottom: 8px;
      }
      .allocation-row {
        display: grid;
        grid-template-columns: 120px 1fr 50px;
        gap: 10px;
        align-items: center;
        background: var(--bg-input, #1a1a24);
        padding: 10px 12px;
        border-radius: 10px;
        margin-bottom: 8px;
      }
      .allocation-label {
        font-size: 0.85rem;
        text-transform: capitalize;
      }
      input[type="range"] {
        width: 100%;
        accent-color: var(--status-nominal, #00ff88);
      }
      .allocation-value {
        font-size: 0.85rem;
        text-align: right;
        color: var(--text-secondary, #bbb);
      }
      .allocation-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 8px;
        font-size: 0.8rem;
        color: var(--text-secondary, #888);
      }
      .allocation-feedback {
        margin-top: 6px;
        font-size: 0.75rem;
        min-height: 1em;
        color: var(--status-critical, #ff4444);
      }
      .allocation-feedback.success { color: var(--status-nominal, #00ff88); }
      .allocation-feedback.warning { color: var(--status-warning, #ffaa00); }
      .apply-btn {
        padding: 8px 14px;
        border-radius: 8px;
        border: none;
        background: var(--status-info, #4aa3ff);
        color: #0a0a0f;
        font-weight: 600;
        cursor: pointer;
      }
      .apply-btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .reactor-card {
        background: var(--bg-input, #1a1a24);
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 8px;
      }
      .reactor-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }
      .reactor-name {
        text-transform: capitalize;
        font-size: 0.9rem;
        font-weight: 600;
      }
      .reactor-status {
        font-size: 0.75rem;
        text-transform: uppercase;
        padding: 2px 6px;
        border-radius: 6px;
        background: rgba(0, 255, 136, 0.2);
        color: var(--status-nominal, #00ff88);
      }
      .reactor-status.warning {
        background: rgba(255, 170, 0, 0.2);
        color: var(--status-warning, #ffaa00);
      }
      .reactor-status.error {
        background: rgba(255, 68, 68, 0.2);
        color: var(--status-critical, #ff4444);
      }
      .meter {
        height: 8px;
        border-radius: 999px;
        background: var(--bg-primary, #0a0a0f);
        overflow: hidden;
        margin-bottom: 6px;
      }
      .meter-fill {
        height: 100%;
        background: var(--status-nominal, #00ff88);
        width: 0%;
        transition: width 0.2s ease;
      }
      .meter-fill.warning { background: var(--status-warning, #ffaa00); }
      .meter-fill.error { background: var(--status-critical, #ff4444); }
      .meter-label {
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        color: var(--text-secondary, #aaa);
        margin-bottom: 8px;
      }
      .reactor-detail {
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        color: var(--text-secondary, #999);
      }
    `;
  }

  _attachHandlers() {
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    if (applyBtn) {
      applyBtn.addEventListener("click", () => this._applyAllocation());
    }
  }

  _updateTotal() {
    const totalEl = this.shadowRoot.getElementById("allocation-total");
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    if (!totalEl || !applyBtn) return;
    const total = this._getAllocationInputs().reduce((sum, value) => sum + value, 0);
    totalEl.textContent = `Total: ${total}%`;
    applyBtn.disabled = total <= 0;
  }

  _getAllocationInputs() {
    const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
    return inputs.map((input) => Number(input.value || 0));
  }

  _applyAllocation() {
    const tier = this._getTier();
    const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
    const raw = {};
    let total = 0;

    if (tier === "manual") {
      // Manual tier: sliders are in kW, convert to fractions
      inputs.forEach((input) => {
        const value = Number(input.value || 0);
        raw[input.dataset.bus] = value;
        total += value;
      });
    } else {
      // All other tiers: sliders are in percentage
      inputs.forEach((input) => {
        const value = Number(input.value || 0);
        raw[input.dataset.bus] = value;
        total += value;
      });
    }

    if (total <= 0) {
      this._setAllocationFeedback("Allocation must be greater than 0.", "warning");
      return;
    }

    const allocation = {};
    Object.keys(raw).forEach((bus) => {
      allocation[bus] = (raw[bus] || 0) / total;
    });

    this._setAllocationFeedback("Sending allocation...", "");
    wsClient.sendShipCommand("set_power_allocation", { allocation })
      .then(() => {
        this._setAllocationFeedback("Allocation updated.", "success");
        this._showMessage("Power allocation updated.", "success");
      })
      .catch((error) => {
        this._setAllocationFeedback(`Failed: ${error.message}`, "warning");
        this._showMessage(`Power allocation failed: ${error.message}`, "error");
      });
  }

  _getAllocation() {
    const power = this._getPowerState();
    const allocation = power.power_allocation;
    if (allocation && Object.keys(allocation).length > 0) {
      return allocation;
    }
    return DEFAULT_ALLOCATION;
  }

  _getReactors() {
    const power = this._getPowerState();
    return power.reactors || {};
  }

  _getPowerState() {
    const systems = stateManager.getSystems();
    return systems.power_management || systems.power || stateManager.getPower() || {};
  }

  /** Total reactor capacity in kW, used by MANUAL and RAW tiers for kW display */
  _getTotalCapacity() {
    const reactors = this._getReactors();
    let total = 0;
    for (const r of Object.values(reactors)) {
      total += r.capacity || 0;
    }
    return total || 100; // fallback to 100 kW if no data
  }

  _formatKw(value) {
    if (!Number.isFinite(value)) return "0 kW";
    return `${value.toFixed(1)} kW`;
  }

  _statusClass(status) {
    const s = (status || "").toLowerCase();
    if (["overheated", "warning", "degraded"].includes(s)) return "warning";
    if (["depleted", "error", "failed"].includes(s)) return "error";
    return "";
  }

  _meterClass(percent) {
    if (percent >= 90) return "error";
    if (percent >= 75) return "warning";
    return "";
  }

  _updateDisplay() {
    const tier = this._getTier();
    if (tier === "manual") {
      this._renderManualAllocation();
      this._renderManualReactors();
    } else if (tier === "raw") {
      this._renderRawAllocation();
      this._renderRawReactors();
    } else if (tier === "cpu-assist") {
      this._renderCpuAssistSummary();
      this._renderCpuAssistReactors();
    } else {
      this._renderArcadeAllocation();
      this._renderArcadeReactors();
    }
  }

  _setAllocationFeedback(message, variant) {
    const feedback = this.shadowRoot.getElementById("allocation-feedback");
    if (!feedback) return;
    feedback.textContent = message || "";
    feedback.classList.remove("success", "warning");
    if (variant) {
      feedback.classList.add(variant);
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("power-management", PowerManagement);
export { PowerManagement };
