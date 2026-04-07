/**
 * Power Allocation Panel
 * Per-system power sliders with real-time draw feedback.
 * Shows each power bus (primary/secondary/tertiary) and the systems
 * mapped to each bus, letting the player redistribute power.
 *
 * Data sources:
 *   - stateManager.getSystems().power_management  -> power_allocation, reactors
 *   - wsClient.sendShipCommand("get_draw_profile") -> per-bus supply/demand/consumers
 *   - wsClient.sendShipCommand("set_power_allocation") -> commit changes
 *
 * Tier awareness:
 *   MANUAL:     kW sliders, voltage readouts, per-system draw breakdown, deficit warnings.
 *   RAW:        Percentage sliders with kW annotation, system draw list, surplus/deficit.
 *   ARCADE:     Percentage sliders, simplified bar view, quick-balance button.
 *   CPU-ASSIST: Read-only summary bars. Hidden by default (tiers.css).
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const BUS_NAMES = ["primary", "secondary", "tertiary"];
const DRAW_POLL_MS = 3000;

class PowerAllocationPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._tierHandler = null;
    this._drawData = null;
    this._drawPollInterval = null;
    // Track pending slider values (not yet sent) so live updates do not
    // overwrite a slider the user is actively dragging.
    this._pendingAlloc = null;
  }

  connectedCallback() {
    this._applyTier();
    this._subscribe();
    this._tierHandler = () => this._applyTier();
    document.addEventListener("tier-change", this._tierHandler);
    this._fetchDrawProfile();
    this._drawPollInterval = setInterval(() => this._fetchDrawProfile(), DRAW_POLL_MS);
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
    if (this._drawPollInterval) {
      clearInterval(this._drawPollInterval);
      this._drawPollInterval = null;
    }
  }

  // ---------------------------------------------------------------------------
  // State helpers
  // ---------------------------------------------------------------------------

  _getTier() {
    return window.controlTier || "arcade";
  }

  _getPowerState() {
    const systems = stateManager.getSystems();
    return systems.power_management || systems.power || stateManager.getPower() || {};
  }

  _getAllocation() {
    const power = this._getPowerState();
    const alloc = power.power_allocation;
    if (alloc && Object.keys(alloc).length > 0) return alloc;
    return { primary: 0.5, secondary: 0.3, tertiary: 0.2 };
  }

  _getReactors() {
    const power = this._getPowerState();
    return power.reactors || {};
  }

  _getTotalCapacity() {
    let total = 0;
    for (const r of Object.values(this._getReactors())) {
      total += r.capacity || 0;
    }
    return total || 100;
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  async _fetchDrawProfile() {
    try {
      const resp = await wsClient.sendShipCommand("get_draw_profile", {});
      this._drawData = resp;
      this._updateDisplay();
    } catch {
      // Silently ignore fetch failures (server may not be ready)
    }
  }

  // ---------------------------------------------------------------------------
  // Tier-aware rendering
  // ---------------------------------------------------------------------------

  _applyTier() {
    this._pendingAlloc = null;
    this.render();
    this._updateDisplay();
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
  // MANUAL tier
  // ---------------------------------------------------------------------------

  _renderManual() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._manualStyles()}</style>
      <div class="buses" id="buses"></div>
      <div class="footer">
        <span class="total mono" id="total">TOTAL: 0.0 kW</span>
        <button class="apply-btn" id="apply-btn">TX ALLOC</button>
      </div>
      <div class="feedback" id="feedback"></div>
    `;
    this._renderBuses("manual");
    this._attachHandlers();
  }

  _manualStyles() {
    return `
      :host { font-family: var(--font-mono, "JetBrains Mono", monospace); color: #ffe0b0; }
      .bus-title { color: #ff8800; border-bottom-color: #ff880044; font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .slider-label, .slider-value { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.75rem; }
      input[type="range"] { accent-color: #ff8800; }
      .apply-btn { background: #ff8800; color: #0a0a0f; font-family: var(--font-mono, "JetBrains Mono", monospace); border-radius: 0; text-transform: uppercase; letter-spacing: 1px; }
      .supply-meter .meter-fill { background: #ff8800; border-radius: 0; }
      .demand-meter .meter-fill { border-radius: 0; }
      .bus-card { border-radius: 0; border: 1px solid #ff880033; }
      .consumer-name { font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .consumer-draw { font-family: var(--font-mono, "JetBrains Mono", monospace); color: #ffe0b0; }
      .mono { font-family: var(--font-mono, "JetBrains Mono", monospace); }
    `;
  }

  // ---------------------------------------------------------------------------
  // RAW tier
  // ---------------------------------------------------------------------------

  _renderRaw() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._rawStyles()}</style>
      <div class="buses" id="buses"></div>
      <div class="footer">
        <span class="total" id="total">Total: 0%</span>
        <button class="apply-btn" id="apply-btn">Apply</button>
      </div>
      <div class="feedback" id="feedback"></div>
    `;
    this._renderBuses("raw");
    this._attachHandlers();
  }

  _rawStyles() {
    return `
      .bus-title { color: #ff4444; border-bottom-color: #ff444433; font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .slider-label { font-family: var(--font-mono, "JetBrains Mono", monospace); text-transform: uppercase; font-size: 0.8rem; }
      .slider-value { font-family: var(--font-mono, "JetBrains Mono", monospace); font-size: 0.8rem; }
      input[type="range"] { accent-color: #ff4444; }
      .apply-btn { background: #ff4444; border-radius: 0; font-family: var(--font-mono, "JetBrains Mono", monospace); }
      .bus-card { border-radius: 0; border: 1px solid #ff444422; }
    `;
  }

  // ---------------------------------------------------------------------------
  // ARCADE tier
  // ---------------------------------------------------------------------------

  _renderArcade() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._arcadeStyles()}</style>
      <div class="buses" id="buses"></div>
      <div class="footer">
        <span class="total" id="total">Total: 0%</span>
        <div class="btn-group">
          <button class="balance-btn" id="balance-btn">AUTO-BALANCE</button>
          <button class="apply-btn" id="apply-btn">Apply</button>
        </div>
      </div>
      <div class="feedback" id="feedback"></div>
    `;
    this._renderBuses("arcade");
    this._attachArcadeHandlers();
  }

  _arcadeStyles() {
    return `
      .btn-group { display: flex; gap: 6px; }
      .balance-btn {
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
      .balance-btn:hover {
        background: rgba(0, 255, 136, 0.2);
        border-color: var(--status-nominal, #00ff88);
      }
    `;
  }

  // ---------------------------------------------------------------------------
  // CPU-ASSIST tier (read-only)
  // ---------------------------------------------------------------------------

  _renderCpuAssist() {
    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._cpuAssistStyles()}</style>
      <div class="assist-note">Auto-ops is managing power distribution.</div>
      <div class="buses" id="buses"></div>
    `;
    this._renderBuses("cpu-assist");
  }

  _cpuAssistStyles() {
    return `
      .bus-title { color: #bb88ff; border-bottom-color: #bb88ff33; }
      .assist-note {
        font-size: 0.75rem;
        color: var(--text-dim, #666);
        font-style: italic;
        margin-bottom: 10px;
      }
      .bus-card {
        background: rgba(128, 0, 255, 0.04);
      }
      .summary-bar { height: 10px; border-radius: 5px; overflow: hidden; background: var(--bg-input, #1a1a24); }
      .summary-fill { height: 100%; border-radius: 5px; background: #bb88ff; transition: width 0.3s ease; }
    `;
  }

  // ---------------------------------------------------------------------------
  // Bus rendering (shared across tiers, parameterized)
  // ---------------------------------------------------------------------------

  _renderBuses(tier) {
    const allocation = this._getAllocation();
    const totalCapacity = this._getTotalCapacity();
    const buses = this._drawData?.buses || {};
    const container = this.shadowRoot.getElementById("buses");
    if (!container) return;

    container.innerHTML = BUS_NAMES.map((bus) => {
      const fraction = allocation[bus] || 0;
      const busInfo = buses[bus] || {};
      const availKw = busInfo.available_kw ?? (fraction * totalCapacity);
      const requestedKw = busInfo.requested_kw ?? 0;
      const deltaKw = availKw - requestedKw;
      const consumers = busInfo.top_consumers || busInfo.systems || [];

      if (tier === "cpu-assist") {
        return this._renderCpuAssistBus(bus, fraction, availKw, requestedKw, consumers);
      }

      const isManual = tier === "manual";
      const sliderMax = isManual ? totalCapacity.toFixed(0) : "100";
      const sliderValue = isManual ? (fraction * totalCapacity).toFixed(0) : Math.round(fraction * 100);
      const valueLabel = isManual
        ? `${(fraction * totalCapacity).toFixed(1)} kW`
        : `${Math.round(fraction * 100)}%`;

      // Supply vs demand meters
      const supplyPct = totalCapacity > 0 ? (availKw / totalCapacity) * 100 : 0;
      const demandPct = totalCapacity > 0 ? (requestedKw / totalCapacity) * 100 : 0;
      const statusClass = deltaKw < 0 ? "deficit" : deltaKw > 0 ? "surplus" : "balanced";

      // Consumer list (MANUAL and RAW only)
      let consumerHtml = "";
      if ((tier === "manual" || tier === "raw") && consumers.length > 0) {
        consumerHtml = `<div class="consumer-list">
          ${consumers.map(c => `
            <div class="consumer-row">
              <span class="consumer-name">${c.name || "unknown"}</span>
              <span class="consumer-draw">${(c.draw_kw || 0).toFixed(1)} kW</span>
            </div>
          `).join("")}
        </div>`;
      }

      return `
        <div class="bus-card">
          <div class="bus-header">
            <span class="bus-title">${bus.toUpperCase()}</span>
            <span class="bus-status ${statusClass}">${deltaKw >= 0 ? "+" : ""}${deltaKw.toFixed(1)} kW</span>
          </div>
          <div class="slider-row">
            <input type="range" min="0" max="${sliderMax}" step="${isManual ? "0.1" : "1"}"
                   value="${sliderValue}" data-bus="${bus}" />
            <span class="slider-value" data-value="${bus}">${valueLabel}</span>
          </div>
          <div class="meter-pair">
            <div class="meter-row">
              <span class="meter-label">Supply</span>
              <div class="supply-meter"><div class="meter-fill" style="width:${Math.min(100, supplyPct)}%"></div></div>
              <span class="meter-kw">${availKw.toFixed(1)} kW</span>
            </div>
            <div class="meter-row">
              <span class="meter-label">Demand</span>
              <div class="demand-meter"><div class="meter-fill ${this._demandFillClass(deltaKw)}" style="width:${Math.min(100, demandPct)}%"></div></div>
              <span class="meter-kw">${requestedKw.toFixed(1)} kW</span>
            </div>
          </div>
          ${consumerHtml}
        </div>
      `;
    }).join("");

    // Attach live slider update listeners
    container.querySelectorAll("input[type='range']").forEach((input) => {
      input.addEventListener("input", () => this._onSliderInput(input, tier));
    });

    this._updateTotal(tier);
  }

  _renderCpuAssistBus(bus, fraction, availKw, requestedKw, consumers) {
    const pct = Math.round(fraction * 100);
    const deltaKw = availKw - requestedKw;
    const statusClass = deltaKw < 0 ? "deficit" : deltaKw > 0 ? "surplus" : "balanced";
    return `
      <div class="bus-card">
        <div class="bus-header">
          <span class="bus-title">${bus.toUpperCase()}</span>
          <span class="bus-status ${statusClass}">${pct}%</span>
        </div>
        <div class="summary-bar"><div class="summary-fill" style="width:${pct}%"></div></div>
        <div class="meter-pair">
          <div class="meter-row">
            <span class="meter-label">Supply</span>
            <span class="meter-kw">${availKw.toFixed(1)} kW</span>
          </div>
          <div class="meter-row">
            <span class="meter-label">Demand</span>
            <span class="meter-kw">${requestedKw.toFixed(1)} kW</span>
          </div>
        </div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Slider interaction
  // ---------------------------------------------------------------------------

  _onSliderInput(input, tier) {
    const bus = input.dataset.bus;
    const valueEl = this.shadowRoot.querySelector(`[data-value="${bus}"]`);
    const isManual = tier === "manual";

    if (isManual) {
      const kw = Number(input.value);
      if (valueEl) valueEl.textContent = `${kw.toFixed(1)} kW`;
    } else {
      const pct = Number(input.value);
      if (valueEl) valueEl.textContent = `${pct}%`;
    }

    // Store pending allocation so state updates do not reset the slider
    if (!this._pendingAlloc) this._pendingAlloc = {};
    this._pendingAlloc[bus] = Number(input.value);

    this._updateTotal(tier);
  }

  // ---------------------------------------------------------------------------
  // Total / feedback
  // ---------------------------------------------------------------------------

  _updateTotal(tier) {
    const totalEl = this.shadowRoot.getElementById("total");
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    if (!totalEl) return;

    const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
    const isManual = tier === "manual";

    if (isManual) {
      const sumKw = inputs.reduce((s, inp) => s + Number(inp.value || 0), 0);
      totalEl.textContent = `TOTAL: ${sumKw.toFixed(1)} kW`;
      if (applyBtn) applyBtn.disabled = sumKw <= 0;
    } else {
      const sumPct = inputs.reduce((s, inp) => s + Number(inp.value || 0), 0);
      totalEl.textContent = `Total: ${sumPct}%`;
      if (applyBtn) applyBtn.disabled = sumPct <= 0;
    }
  }

  _setFeedback(message, variant) {
    const el = this.shadowRoot.getElementById("feedback");
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("success", "warning");
    if (variant) el.classList.add(variant);
  }

  // ---------------------------------------------------------------------------
  // Apply allocation
  // ---------------------------------------------------------------------------

  _applyAllocation() {
    const tier = this._getTier();
    const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
    const raw = {};
    let total = 0;

    inputs.forEach((input) => {
      const value = Number(input.value || 0);
      raw[input.dataset.bus] = value;
      total += value;
    });

    if (total <= 0) {
      this._setFeedback("Allocation must be greater than 0.", "warning");
      return;
    }

    // Normalize to fractions
    const allocation = {};
    for (const bus of Object.keys(raw)) {
      allocation[bus] = (raw[bus] || 0) / total;
    }

    this._setFeedback("Sending allocation...", "");
    this._pendingAlloc = null;

    wsClient.sendShipCommand("set_power_allocation", { allocation })
      .then(() => {
        this._setFeedback("Allocation updated.", "success");
        this._fetchDrawProfile();
      })
      .catch((error) => {
        this._setFeedback(`Failed: ${error.message}`, "warning");
      });
  }

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  _attachHandlers() {
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    if (applyBtn) {
      applyBtn.addEventListener("click", () => this._applyAllocation());
    }
  }

  _attachArcadeHandlers() {
    this._attachHandlers();

    const balanceBtn = this.shadowRoot.getElementById("balance-btn");
    if (balanceBtn) {
      balanceBtn.addEventListener("click", () => {
        const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
        const balanced = Math.round(100 / inputs.length);
        inputs.forEach((input) => {
          input.value = balanced;
          const valueEl = this.shadowRoot.querySelector(`[data-value="${input.dataset.bus}"]`);
          if (valueEl) valueEl.textContent = `${balanced}%`;
        });
        this._updateTotal("arcade");
        this._applyAllocation();
        this._setFeedback("Auto-balanced evenly.", "success");
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Live update (state changes from server)
  // ---------------------------------------------------------------------------

  _updateDisplay() {
    // Only re-render bus content, not the whole shell, to preserve slider focus.
    const tier = this._getTier();
    const container = this.shadowRoot.getElementById("buses");
    if (!container) return;

    // If user is dragging a slider (pendingAlloc exists), skip overwriting
    if (this._pendingAlloc) return;

    this._renderBuses(tier);
  }

  // ---------------------------------------------------------------------------
  // Utility
  // ---------------------------------------------------------------------------

  _demandFillClass(deltaKw) {
    if (deltaKw < -5) return "deficit";
    if (deltaKw < 0) return "warning";
    return "";
  }

  // ---------------------------------------------------------------------------
  // Base styles shared across all tiers
  // ---------------------------------------------------------------------------

  _baseStyles() {
    return `
      :host {
        display: block;
        padding: 12px;
        font-family: var(--font-sans, "Inter", sans-serif);
        color: var(--text-primary, #e0e0e0);
      }

      .buses {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }

      .bus-card {
        background: var(--bg-input, #1a1a24);
        border-radius: 10px;
        padding: 12px;
      }

      .bus-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }

      .bus-title {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding-bottom: 4px;
        border-bottom: 1px solid var(--border-default, #2a2a3a);
      }

      .bus-status {
        font-size: 0.75rem;
        font-weight: 600;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        padding: 2px 8px;
        border-radius: 6px;
      }
      .bus-status.surplus {
        background: rgba(0, 255, 136, 0.15);
        color: var(--status-nominal, #00ff88);
      }
      .bus-status.deficit {
        background: rgba(255, 68, 68, 0.15);
        color: var(--status-critical, #ff4444);
      }
      .bus-status.balanced {
        background: rgba(68, 136, 255, 0.15);
        color: var(--status-info, #4488ff);
      }

      .slider-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
      }
      .slider-row input[type="range"] {
        flex: 1;
        accent-color: var(--status-nominal, #00ff88);
      }
      .slider-value {
        min-width: 60px;
        text-align: right;
        font-size: 0.8rem;
        color: var(--text-secondary, #bbb);
      }

      .meter-pair {
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin-bottom: 6px;
      }
      .meter-row {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .meter-label {
        font-size: 0.7rem;
        color: var(--text-dim, #888);
        width: 50px;
        flex-shrink: 0;
      }
      .supply-meter, .demand-meter {
        flex: 1;
        height: 6px;
        border-radius: 999px;
        background: var(--bg-primary, #0a0a0f);
        overflow: hidden;
      }
      .meter-fill {
        height: 100%;
        background: var(--status-nominal, #00ff88);
        transition: width 0.2s ease;
        border-radius: 999px;
      }
      .meter-fill.warning { background: var(--status-warning, #ffaa00); }
      .meter-fill.deficit { background: var(--status-critical, #ff4444); }
      .meter-kw {
        font-size: 0.7rem;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: var(--text-secondary, #aaa);
        min-width: 55px;
        text-align: right;
      }

      .consumer-list {
        margin-top: 6px;
        padding-top: 6px;
        border-top: 1px dashed var(--border-default, #2a2a3a);
      }
      .consumer-row {
        display: flex;
        justify-content: space-between;
        font-size: 0.7rem;
        padding: 2px 0;
      }
      .consumer-name {
        color: var(--text-dim, #888);
        text-transform: capitalize;
      }
      .consumer-draw {
        color: var(--text-secondary, #aaa);
      }

      .footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 10px;
        font-size: 0.8rem;
        color: var(--text-secondary, #888);
      }

      .total {
        font-size: 0.8rem;
      }

      .apply-btn {
        padding: 8px 14px;
        border-radius: 8px;
        border: none;
        background: var(--status-info, #4aa3ff);
        color: #0a0a0f;
        font-weight: 600;
        cursor: pointer;
        font-size: 0.8rem;
      }
      .apply-btn:disabled { opacity: 0.5; cursor: not-allowed; }

      .feedback {
        margin-top: 6px;
        font-size: 0.75rem;
        min-height: 1em;
        color: var(--status-critical, #ff4444);
      }
      .feedback.success { color: var(--status-nominal, #00ff88); }
      .feedback.warning { color: var(--status-warning, #ffaa00); }
    `;
  }
}

customElements.define("power-allocation-panel", PowerAllocationPanel);
export { PowerAllocationPanel };
