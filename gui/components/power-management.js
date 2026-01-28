/**
 * Power Management Panel
 * Allocation sliders + reactor meters.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const DEFAULT_ALLOCATION = {
  primary: 0.5,
  secondary: 0.3,
  tertiary: 0.2,
};

class PowerManagement extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
          color: var(--text-primary, #e0e0e0);
        }

        .section {
          margin-bottom: 16px;
        }

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

        .allocation-feedback.success {
          color: var(--status-nominal, #00ff88);
        }

        .allocation-feedback.warning {
          color: var(--status-warning, #ffaa00);
        }

        .apply-btn {
          padding: 8px 14px;
          border-radius: 8px;
          border: none;
          background: var(--status-info, #4aa3ff);
          color: #0a0a0f;
          font-weight: 600;
          cursor: pointer;
        }

        .apply-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

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

        .meter-fill.warning {
          background: var(--status-warning, #ffaa00);
        }

        .meter-fill.error {
          background: var(--status-critical, #ff4444);
        }

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
      </style>

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

    this._renderAllocation();
    this._renderReactors();
    this._attachHandlers();
  }

  _attachHandlers() {
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    applyBtn.addEventListener("click", () => this._applyAllocation());
  }

  _renderAllocation() {
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

  _renderReactors() {
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
      const availabilityPercent = capacity > 0 ? (available / capacity) * 100 : 0;
      const temp = reactor.temperature ?? 0;
      const thermal = reactor.thermal_limit ?? 0;
      const tempPercent = thermal > 0 ? (temp / thermal) * 100 : 0;
      const fuelPercent = reactor.fuel_percent ?? null;

      return `
        <div class="reactor-card">
          <div class="reactor-header">
            <div class="reactor-name">${reactor.name || "reactor"}</div>
            <div class="reactor-status ${this._statusClass(reactor.status)}">${reactor.status || "nominal"}</div>
          </div>
          <div class="meter">
            <div class="meter-fill ${this._meterClass(availabilityPercent)}" style="width:${availabilityPercent}%"></div>
          </div>
          <div class="meter-label">
            <span>Available</span>
            <span>${this._formatKw(available)} / ${this._formatKw(capacity)}</span>
          </div>
          <div class="meter">
            <div class="meter-fill ${this._meterClass(tempPercent)}" style="width:${Math.min(100, tempPercent)}%"></div>
          </div>
          <div class="meter-label">
            <span>Temperature</span>
            <span>${temp.toFixed(1)}° / ${thermal.toFixed(1)}°</span>
          </div>
          <div class="reactor-detail">
            <span>Fuel</span>
            <span>${fuelPercent === null ? "—" : `${fuelPercent.toFixed(1)}%`}</span>
          </div>
        </div>
      `;
    }).join("");
  }

  _updateTotal() {
    const totalEl = this.shadowRoot.getElementById("allocation-total");
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    const total = this._getAllocationInputs().reduce((sum, value) => sum + value, 0);
    totalEl.textContent = `Total: ${total}%`;
    applyBtn.disabled = total <= 0;
  }

  _getAllocationInputs() {
    const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
    return inputs.map((input) => Number(input.value || 0));
  }

  _applyAllocation() {
    const inputs = Array.from(this.shadowRoot.querySelectorAll("input[type='range']"));
    const raw = {};
    let total = 0;
    inputs.forEach((input) => {
      const value = Number(input.value || 0);
      raw[input.dataset.bus] = value;
      total += value;
    });

    if (total <= 0) {
      this._setAllocationFeedback("Allocation must be greater than 0% total.", "warning");
      return;
    }

    const allocation = {};
    Object.keys(raw).forEach((bus) => {
      allocation[bus] = (raw[bus] || 0) / total;
    });

    this._setAllocationFeedback("Sending allocation…", "");
    wsClient.sendShipCommand("set_power_allocation", { allocation })
      .then(() => {
        this._setAllocationFeedback("Allocation updated.", "success");
        this._showMessage("Power allocation updated.", "success");
      })
      .catch((error) => {
        this._setAllocationFeedback(`Failed to update allocation: ${error.message}`, "warning");
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

  _formatKw(value) {
    if (!Number.isFinite(value)) {
      return "0 kW";
    }
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
    this._renderAllocation();
    this._renderReactors();
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
