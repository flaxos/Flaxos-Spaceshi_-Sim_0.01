/**
 * Power Flow Display — reactor -> buses -> subsystem loads.
 *
 * Combines:
 *   - get_draw_profile (per-bus available/requested/top consumers)
 *   - ship.engineering (reactor output percentage)
 *   - ship.thermal (heat / radiator state)
 *
 * The component is display-only. Existing power controls remain in the
 * allocation/profile panels.
 */
import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const POLL_MS = 2500;
const BUS_ORDER = ["primary", "secondary", "tertiary", "unassigned"];

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizeDrawProfile(raw) {
  const profile = raw?.response || raw;
  if (!profile || typeof profile !== "object") return null;

  if (profile.buses && typeof profile.buses === "object") {
    return profile;
  }

  const hasLegacy = BUS_ORDER.some((bus) => profile?.[bus]);
  if (!hasLegacy) return null;

  const buses = {};
  let availableTotal = 0;
  let requestedTotal = 0;

  for (const bus of BUS_ORDER) {
    const entry = profile?.[bus];
    if (!entry) continue;
    const available = Number(entry.available_kw ?? entry.supply ?? 0);
    const requested = Number(entry.requested_kw ?? entry.requested ?? 0);
    buses[bus] = {
      available_kw: available,
      requested_kw: requested,
      delta_kw: Number(entry.delta_kw ?? entry.delta ?? (available - requested)),
      status: entry.status || "balanced",
      systems: entry.systems || [],
      top_consumers: entry.top_consumers || [],
    };
    availableTotal += available;
    requestedTotal += requested;
  }

  return {
    active_profile: profile.active_profile || null,
    buses,
    totals: {
      available_kw: availableTotal,
      requested_kw: requestedTotal,
      delta_kw: availableTotal - requestedTotal,
    },
  };
}

function busColor(available, requested) {
  if (available <= 0 && requested <= 0) return "#445063";
  if (available <= 0) return "#ff5b5b";
  const ratio = requested / available;
  if (ratio > 1) return "#ff5b5b";
  if (ratio >= 0.8) return "#ffb020";
  return "#35c56f";
}

function lineWidth(value, maxValue) {
  if (maxValue <= 0) return 2;
  return clamp(1.5 + (value / maxValue) * 6, 1.5, 7.5);
}

function formatKw(value) {
  if (value == null || Number.isNaN(value)) return "?";
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)} MW`;
  return `${value.toFixed(value >= 100 ? 0 : 1)} kW`;
}

function shortName(name = "") {
  return name
    .replace(/[_.-]/g, " ")
    .replace(/\bpower\b/ig, "")
    .trim()
    .toUpperCase()
    .slice(0, 9);
}

class PowerFlowDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._profile = null;
    this._pollTimer = null;
    this._unsubs = [];
  }

  connectedCallback() {
    this._renderShell();
    this._unsubs = [
      stateManager.subscribe("engineering", () => this._draw()),
      stateManager.subscribe("thermal", () => this._draw()),
    ];
    this._poll();
    this._pollTimer = setInterval(() => this._poll(), POLL_MS);
  }

  disconnectedCallback() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    this._unsubs.forEach((unsub) => unsub?.());
    this._unsubs = [];
  }

  async _poll() {
    try {
      const raw = await wsClient.sendShipCommand("get_draw_profile", {});
      this._profile = normalizeDrawProfile(raw);
      this._draw();
    } catch (_) {
      // Ignore transient bridge / ship selection failures.
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        svg {
          width: 100%;
          height: auto;
          display: block;
        }

        .frame {
          fill: rgba(9, 12, 18, 0.6);
          stroke: #263042;
          stroke-width: 1;
        }

        .title {
          font-size: 7px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          fill: #708097;
        }

        .bus-name {
          font-size: 7px;
          letter-spacing: 0.08em;
          fill: #d5deea;
          text-anchor: middle;
        }

        .bus-meta,
        .consumer-meta,
        .footer {
          font-size: 6px;
          fill: #8896a9;
          text-anchor: middle;
        }

        .reactor-text {
          font-size: 7px;
          fill: #d5deea;
          text-anchor: middle;
        }

        .empty {
          font-size: 8px;
          fill: #7a889b;
          text-anchor: middle;
        }
      </style>

      <svg viewBox="0 0 320 210" xmlns="http://www.w3.org/2000/svg">
        <rect class="frame" x="8" y="8" width="304" height="194" rx="8" />
        <text class="title" x="18" y="22">POWER FLOW</text>
        <g id="flow-layer"></g>
      </svg>
    `;
  }

  _draw() {
    const layer = this.shadowRoot.getElementById("flow-layer");
    if (!layer) return;

    const profile = this._profile;
    if (!profile?.buses) {
      layer.innerHTML = `<text class="empty" x="160" y="108">Waiting for power telemetry...</text>`;
      return;
    }

    const engineering = stateManager.getShipState?.()?.engineering || {};
    const thermal = stateManager.getThermal?.() || stateManager.getShipState?.()?.thermal || {};
    const busEntries = BUS_ORDER
      .filter((bus) => profile.buses?.[bus])
      .map((bus) => [bus, profile.buses[bus]]);

    if (!busEntries.length) {
      layer.innerHTML = `<text class="empty" x="160" y="108">No power buses available</text>`;
      return;
    }

    const totals = profile.totals || {};
    const maxBusRequest = Math.max(
      1,
      ...busEntries.map(([, entry]) => Number(entry.requested_kw || 0))
    );
    const reactorTelemetry = engineering.reactor_output ?? (
      engineering.reactor_percent != null ? engineering.reactor_percent / 100 : null
    );
    const reactorPct = clamp(
      reactorTelemetry ?? (totals.available_kw > 0 ? totals.requested_kw / totals.available_kw : 0),
      0,
      1
    );
    const reactorRing = 2 * Math.PI * 20;
    const reactorColor = busColor(totals.available_kw || 0, totals.requested_kw || 0);

    const heatPercent = clamp((thermal.temperature_percent ?? 0) / 100, 0, 1);
    const heatColor = thermal.is_emergency
      ? "#ff5b5b"
      : thermal.is_overheating
        ? "#ffb020"
        : heatPercent > 0.45
          ? "#59b6ff"
          : "#35c56f";

    let html = `
      <circle cx="160" cy="42" r="21" fill="#111722" stroke="#30405a" stroke-width="1.2" />
      <circle cx="160" cy="42" r="20" fill="none" stroke="${reactorColor}" stroke-width="4"
        stroke-dasharray="${(reactorPct * reactorRing).toFixed(1)} ${reactorRing.toFixed(1)}"
        transform="rotate(-90 160 42)" />
      <text class="reactor-text" x="160" y="39">REACTOR</text>
      <text class="reactor-text" x="160" y="49">${Math.round(reactorPct * 100)}%</text>
      <text class="footer" x="160" y="62">${formatKw(totals.available_kw || 0)} avail</text>
    `;

    const busXs = busEntries.map((_, index) => {
      if (busEntries.length === 1) return 160;
      const spacing = 176 / (busEntries.length - 1);
      return 72 + index * spacing;
    });
    const busY = 104;

    busEntries.forEach(([busName, bus], index) => {
      const x = busXs[index] ?? (56 + index * 64);
      const available = Number(bus.available_kw || 0);
      const requested = Number(bus.requested_kw || 0);
      const color = busColor(available, requested);
      const width = lineWidth(requested, maxBusRequest);
      const consumers = (bus.systems?.length ? bus.systems : bus.top_consumers || []).slice(0, 4);

      html += `
        <line x1="160" y1="63" x2="${x}" y2="${busY - 16}"
          stroke="${color}" stroke-width="${width.toFixed(1)}" opacity="0.8" />
        <rect x="${x - 28}" y="${busY - 16}" width="56" height="28" rx="5"
          fill="#111722" stroke="${color}" stroke-width="1.3" />
        <text class="bus-name" x="${x}" y="${busY - 3}">${busName.toUpperCase()}</text>
        <text class="bus-meta" x="${x}" y="${busY + 8}">
          ${formatKw(requested).replace(" kW", "")} / ${formatKw(available).replace(" kW", "")}
        </text>
      `;

      const leafStartY = 142;
      const leafStep = 15;
      consumers.forEach((consumer, cIndex) => {
        const cy = leafStartY + cIndex * leafStep;
        const draw = Number(consumer.draw_kw || 0);
        const drawWidth = lineWidth(draw, requested || maxBusRequest);

        html += `
          <line x1="${x}" y1="${busY + 12}" x2="${x}" y2="${cy - 6}"
            stroke="${color}" stroke-width="${drawWidth.toFixed(1)}" opacity="0.55" />
          <circle cx="${x}" cy="${cy}" r="${clamp(4 + draw / Math.max(1, requested) * 10, 4, 10).toFixed(1)}"
            fill="#111722" stroke="${color}" stroke-width="1" />
          <text class="consumer-meta" x="${x}" y="${cy + 1.8}">${shortName(consumer.name)}</text>
          <text class="consumer-meta" x="${x}" y="${cy + 10}">${formatKw(draw).replace(" kW", "")}</text>
        `;
      });
    });

    html += `
      <g transform="translate(128 184)">
        <rect x="0" y="-6" width="64" height="12" rx="3" fill="none" stroke="${heatColor}" stroke-width="1.1" />
        <line x1="6" y1="-10" x2="6" y2="10" stroke="${heatColor}" stroke-width="1" />
        <line x1="58" y1="-10" x2="58" y2="10" stroke="${heatColor}" stroke-width="1" />
        <line x1="16" y1="-10" x2="16" y2="10" stroke="${heatColor}" stroke-width="1" />
        <line x1="26" y1="-10" x2="26" y2="10" stroke="${heatColor}" stroke-width="1" />
        <line x1="38" y1="-10" x2="38" y2="10" stroke="${heatColor}" stroke-width="1" />
        <line x1="48" y1="-10" x2="48" y2="10" stroke="${heatColor}" stroke-width="1" />
      </g>
      <text class="footer" x="160" y="197">
        THERMAL ${Math.round((thermal.temperature_percent ?? 0))}% • ${Math.round(thermal.hull_temperature ?? 0)} K
      </text>
      <text class="footer" x="286" y="22">${profile.active_profile ? `PROFILE ${String(profile.active_profile).toUpperCase()}` : ""}</text>
    `;

    layer.innerHTML = html;
  }
}

customElements.define("power-flow-display", PowerFlowDisplay);
