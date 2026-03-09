/**
 * Power Draw Display
 * Shows power supply vs demand per bus (primary, secondary, tertiary)
 * as horizontal bars with surplus/deficit indicators.
 * Polls the server via get_draw_profile every 3 seconds.
 */

import { wsClient } from "../js/ws-client.js";

const POLL_INTERVAL_MS = 3000;
const BUS_NAMES = ["primary", "secondary", "tertiary"];

class PowerDrawDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._drawData = null;
    this._pollInterval = null;
  }

  connectedCallback() {
    this._renderShell();
    this._fetchDrawProfile();
    this._pollInterval = setInterval(() => this._fetchDrawProfile(), POLL_INTERVAL_MS);
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }

  async _fetchDrawProfile() {
    try {
      const resp = await wsClient.sendShipCommand("get_draw_profile", {});
      this._drawData = resp;
      this._render();
    } catch (err) {
      console.warn("power-draw-display: fetch failed:", err.message);
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          padding: 16px;
        }
        .header {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #a0a0b0);
          margin-bottom: 12px;
        }
        .bus-row {
          margin-bottom: 12px;
        }
        .bus-label {
          display: flex;
          justify-content: space-between;
          margin-bottom: 4px;
        }
        .bus-name {
          color: var(--text-primary, #e0e0e0);
          text-transform: uppercase;
          font-size: 0.7rem;
          font-weight: 600;
        }
        .bus-values {
          color: var(--text-dim, #666680);
          font-size: 0.7rem;
        }
        .bar-track {
          height: 16px;
          background: var(--bg-input, #1a1a2e);
          border-radius: 3px;
          position: relative;
          overflow: hidden;
        }
        .bar-supply {
          height: 100%;
          border-radius: 3px;
          position: absolute;
          top: 0;
          left: 0;
        }
        .bar-demand {
          height: 100%;
          border-radius: 3px;
          position: absolute;
          top: 0;
          left: 0;
          opacity: 0.35;
          border-right: 2px solid;
        }
        .delta {
          font-size: 0.75rem;
          font-weight: 600;
          text-align: right;
          margin-top: 2px;
        }
        .delta.surplus { color: var(--status-nominal, #00ff88); }
        .delta.deficit { color: var(--status-critical, #ff4444); }
        .deficit-warning {
          margin-top: 12px;
          padding: 8px 12px;
          background: rgba(255, 68, 68, 0.15);
          border: 1px solid var(--status-critical, #ff4444);
          border-radius: 6px;
          text-align: center;
          font-weight: 700;
          font-size: 0.85rem;
          color: var(--status-critical, #ff4444);
          letter-spacing: 2px;
          animation: pulse 1.5s ease-in-out infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        .empty-state {
          text-align: center;
          color: var(--text-dim, #666680);
          padding: 24px;
          font-style: italic;
        }
      </style>
      <div id="content">
        <div class="empty-state">Waiting for power data...</div>
      </div>
    `;
  }

  _render() {
    const el = this.shadowRoot.getElementById("content");
    if (!this._drawData) {
      el.innerHTML = '<div class="empty-state">Waiting for power data...</div>';
      return;
    }

    let hasDeficit = false;
    let html = '<div class="header">Power Draw by Bus</div>';

    for (const bus of BUS_NAMES) {
      const d = this._drawData[bus];
      if (!d) continue;

      const supply = d.supply ?? 0;
      const requested = d.requested ?? 0;
      const delta = d.delta ?? (supply - requested);
      const max = Math.max(supply, requested, 1);
      const supplyPct = (supply / max) * 100;
      const demandPct = (requested / max) * 100;
      const overloaded = requested > supply;

      if (delta < 0) hasDeficit = true;

      const supplyColor = "var(--status-nominal, #00ff88)";
      const demandColor = overloaded
        ? "var(--status-warning, #ffaa00)"
        : "var(--status-nominal, #00ff88)";
      const deltaSign = delta >= 0 ? "+" : "";
      const deltaClass = delta >= 0 ? "surplus" : "deficit";

      html += `
        <div class="bus-row">
          <div class="bus-label">
            <span class="bus-name">${bus}</span>
            <span class="bus-values">Supply: ${supply.toFixed(1)} / Demand: ${requested.toFixed(1)}</span>
          </div>
          <div class="bar-track">
            <div class="bar-supply" style="width:${supplyPct.toFixed(1)}%;background:${supplyColor};"></div>
            <div class="bar-demand" style="width:${demandPct.toFixed(1)}%;background:${demandColor};border-color:${demandColor};"></div>
          </div>
          <div class="delta ${deltaClass}">${deltaSign}${delta.toFixed(1)}</div>
        </div>`;
    }

    if (hasDeficit) {
      html += '<div class="deficit-warning">POWER DEFICIT</div>';
    }

    el.innerHTML = html;
  }
}

customElements.define("power-draw-display", PowerDrawDisplay);
export { PowerDrawDisplay };
