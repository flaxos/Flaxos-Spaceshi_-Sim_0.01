/**
 * Power Draw Display
 * Shows power supply vs demand per bus (primary, secondary, tertiary)
 * as horizontal bars with surplus/deficit indicators.
 * Polls the server via get_draw_profile every 3 seconds.
 *
 * Tier awareness:
 *   MANUAL/RAW: Exact wattage per consumer, detailed supply/demand numbers.
 *   ARCADE:     Percentage of budget per category, simplified view.
 *   CPU-ASSIST: Hidden by tiers.css (auto-ops manages). Renders minimal fallback if forced visible.
 */

import { wsClient } from "../js/ws-client.js";

const POLL_INTERVAL_MS = 3000;
const BUS_NAMES = ["primary", "secondary", "tertiary"];

function normalizeDrawProfile(raw) {
  const profile = raw?.response || raw;
  if (!profile || typeof profile !== "object") return null;

  if (profile.buses && typeof profile.buses === "object") {
    const normalized = {};
    for (const bus of BUS_NAMES) {
      const entry = profile.buses?.[bus];
      if (!entry) continue;
      normalized[bus] = {
        supply: Number(entry.available_kw ?? entry.supply ?? 0),
        requested: Number(entry.requested_kw ?? entry.requested ?? 0),
        delta: Number(
          entry.delta_kw ?? entry.delta ??
          ((entry.available_kw ?? entry.supply ?? 0) - (entry.requested_kw ?? entry.requested ?? 0))
        ),
        status: entry.status || "balanced",
      };
    }
    return normalized;
  }

  if (BUS_NAMES.some((bus) => profile[bus])) {
    return profile;
  }

  return null;
}

class PowerDrawDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._drawData = null;
    this._pollInterval = null;
    this._tierHandler = null;
  }

  connectedCallback() {
    this._renderShell();
    this._fetchDrawProfile();
    this._pollInterval = setInterval(() => this._fetchDrawProfile(), POLL_INTERVAL_MS);
    this._tierHandler = () => this._render();
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _getTier() {
    return window.controlTier || "arcade";
  }

  async _fetchDrawProfile() {
    try {
      const resp = await wsClient.sendShipCommand("get_draw_profile", {});
      this._drawData = normalizeDrawProfile(resp);
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

        /* --- MANUAL/RAW: monospace, sharper edges, amber/red tints --- */
        :host(.tier-manual) .bar-track,
        :host(.tier-raw) .bar-track {
          border-radius: 0;
        }
        :host(.tier-manual) .bar-supply,
        :host(.tier-manual) .bar-demand,
        :host(.tier-raw) .bar-supply,
        :host(.tier-raw) .bar-demand {
          border-radius: 0;
        }

        /* --- ARCADE: percentage labels, rounded --- */
        .pct-label {
          font-size: 0.7rem;
          color: var(--text-secondary, #a0a0b0);
          text-align: center;
          margin-top: 2px;
        }

        /* --- CPU-ASSIST: minimal fallback --- */
        .assist-note {
          font-size: 0.75rem;
          color: var(--text-dim, #666);
          font-style: italic;
          text-align: center;
          padding: 16px;
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

    const tier = this._getTier();

    // Apply tier class to host for CSS targeting
    this.classList.remove("tier-manual", "tier-raw", "tier-arcade", "tier-cpu-assist");
    this.classList.add(`tier-${tier}`);

    if (tier === "cpu-assist") {
      el.innerHTML = '<div class="assist-note">Auto-ops is managing power distribution.</div>';
      return;
    }

    const showExactWattage = tier === "manual" || tier === "raw";
    let hasDeficit = false;
    let html = `<div class="header">Power Draw by Bus${showExactWattage ? " [kW]" : ""}</div>`;

    // Compute total supply + demand for percentage mode
    let totalSupply = 0;
    let totalDemand = 0;
    if (!showExactWattage) {
      for (const bus of BUS_NAMES) {
        const d = this._drawData[bus];
        if (d) {
          totalSupply += d.supply ?? 0;
          totalDemand += d.requested ?? 0;
        }
      }
    }

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

      if (showExactWattage) {
        // MANUAL/RAW: exact wattage with supply/demand numbers
        html += `
          <div class="bus-row">
            <div class="bus-label">
              <span class="bus-name">${bus}</span>
              <span class="bus-values">Supply: ${supply.toFixed(1)} kW / Demand: ${requested.toFixed(1)} kW</span>
            </div>
            <div class="bar-track">
              <div class="bar-supply" style="width:${supplyPct.toFixed(1)}%;background:${supplyColor};"></div>
              <div class="bar-demand" style="width:${demandPct.toFixed(1)}%;background:${demandColor};border-color:${demandColor};"></div>
            </div>
            <div class="delta ${deltaClass}">${deltaSign}${delta.toFixed(1)} kW</div>
          </div>`;
      } else {
        // ARCADE: percentage of total budget
        const budgetPct = totalSupply > 0 ? ((supply / totalSupply) * 100).toFixed(0) : "--";
        const usagePct = totalDemand > 0 ? ((requested / totalDemand) * 100).toFixed(0) : "--";
        html += `
          <div class="bus-row">
            <div class="bus-label">
              <span class="bus-name">${bus}</span>
              <span class="bus-values">${budgetPct}% of budget</span>
            </div>
            <div class="bar-track">
              <div class="bar-supply" style="width:${supplyPct.toFixed(1)}%;background:${supplyColor};"></div>
              <div class="bar-demand" style="width:${demandPct.toFixed(1)}%;background:${demandColor};border-color:${demandColor};"></div>
            </div>
            <div class="pct-label">${usagePct}% usage</div>
          </div>`;
      }
    }

    if (hasDeficit) {
      html += '<div class="deficit-warning">POWER DEFICIT</div>';
    }

    el.innerHTML = html;
  }
}

customElements.define("power-draw-display", PowerDrawDisplay);
export { PowerDrawDisplay };
