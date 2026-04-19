<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    asRecord,
    clamp,
    formatKw,
    getEngineeringShip,
    getEngineeringState,
    getThermalState,
    toNumber,
  } from "./engineeringData.js";

  type DrawBus = Record<string, unknown>;

  const POLL_MS = 2500;
  const BUS_ORDER = ["primary", "secondary", "tertiary", "unassigned"];

  let profile: Record<string, unknown> | null = null;
  let intervalHandle: number | null = null;
  let observer: IntersectionObserver | null = null;
  let isVisible = true;
  let root: HTMLDivElement;

  function normalizeDrawProfile(raw: unknown) {
    const record = asRecord(raw);
    const payload = asRecord(record?.data) ?? record;
    if (!payload) return null;

    if (asRecord(payload.buses)) return payload;

    const hasLegacy = BUS_ORDER.some((bus) => asRecord(payload[bus]));
    if (!hasLegacy) return null;

    const buses: Record<string, DrawBus> = {};
    let availableTotal = 0;
    let requestedTotal = 0;

    for (const bus of BUS_ORDER) {
      const entry = asRecord(payload[bus]);
      if (!entry) continue;
      const available = toNumber(entry.available_kw, toNumber(entry.supply));
      const requested = toNumber(entry.requested_kw, toNumber(entry.requested));
      buses[bus] = {
        available_kw: available,
        requested_kw: requested,
        delta_kw: toNumber(entry.delta_kw, available - requested),
        status: entry.status ?? "balanced",
        systems: Array.isArray(entry.systems) ? entry.systems : [],
        top_consumers: Array.isArray(entry.top_consumers) ? entry.top_consumers : [],
      };
      availableTotal += available;
      requestedTotal += requested;
    }

    return {
      active_profile: payload.active_profile ?? null,
      buses,
      totals: {
        available_kw: availableTotal,
        requested_kw: requestedTotal,
        delta_kw: availableTotal - requestedTotal,
      },
    };
  }

  function busColor(available: number, requested: number) {
    if (available <= 0 && requested <= 0) return "#445063";
    if (available <= 0) return "#ff5b5b";
    const ratio = requested / available;
    if (ratio > 1) return "#ff5b5b";
    if (ratio >= 0.8) return "#ffb020";
    return "#35c56f";
  }

  function lineWidth(value: number, maxValue: number) {
    if (maxValue <= 0) return 2;
    return clamp(1.5 + (value / maxValue) * 6, 1.5, 7.5);
  }

  function shortName(name: unknown) {
    return String(name ?? "")
      .replace(/[_.-]/g, " ")
      .replace(/\bpower\b/ig, "")
      .trim()
      .toUpperCase()
      .slice(0, 9);
  }

  function consumerList(bus: DrawBus) {
    const systems = Array.isArray(bus.systems) ? bus.systems : [];
    const topConsumers = Array.isArray(bus.top_consumers) ? bus.top_consumers : [];
    return (systems.length ? systems : topConsumers).slice(0, 4).map((item) => asRecord(item) ?? {});
  }

  async function refresh() {
    if (!isVisible || document.hidden) return;
    try {
      const response = await wsClient.sendShipCommand("get_draw_profile", {});
      profile = normalizeDrawProfile(response) as Record<string, unknown> | null;
    } catch {
      // best effort
    }
  }

  onMount(() => {
    if (typeof IntersectionObserver !== "undefined") {
      observer = new IntersectionObserver((entries) => {
        isVisible = entries.some((entry) => entry.isIntersecting);
        if (isVisible) void refresh();
      });
      if (root) observer.observe(root);
    }

    void refresh();
    intervalHandle = window.setInterval(() => void refresh(), POLL_MS);

    return () => {
      observer?.disconnect();
      if (intervalHandle != null) window.clearInterval(intervalHandle);
    };
  });

  $: ship = getEngineeringShip($gameState);
  $: engineering = getEngineeringState(ship);
  $: thermal = getThermalState(ship);
  $: busesRecord = (asRecord(profile?.buses) as Record<string, DrawBus> | null) ?? {};
  $: busEntries = BUS_ORDER
    .filter((bus) => busesRecord[bus])
    .map((bus) => [bus, busesRecord[bus]] as [string, DrawBus]);
  $: totals = asRecord(profile?.totals) ?? {};
  $: maxBusRequest = Math.max(1, ...busEntries.map(([, bus]) => toNumber(bus.requested_kw, 0)));
  $: reactorTelemetry = toNumber(
    engineering.reactor_output,
    engineering.reactor_percent == null ? Number.NaN : toNumber(engineering.reactor_percent) / 100
  );
  $: reactorPct = clamp(
    Number.isFinite(reactorTelemetry)
      ? reactorTelemetry
      : toNumber(totals.available_kw, 0) > 0
        ? toNumber(totals.requested_kw, 0) / Math.max(1, toNumber(totals.available_kw, 1))
        : 0,
    0,
    1
  );
  $: reactorRing = 2 * Math.PI * 20;
  $: reactorColor = busColor(toNumber(totals.available_kw, 0), toNumber(totals.requested_kw, 0));
  $: heatPercent = clamp(toNumber(thermal.temperature_percent, 0) / 100, 0, 1);
  $: heatColor = Boolean(thermal.is_emergency)
    ? "#ff5b5b"
    : Boolean(thermal.is_overheating)
      ? "#ffb020"
      : heatPercent > 0.45
        ? "#59b6ff"
        : "#35c56f";
  $: busXs = busEntries.map((_, index) => {
    if (busEntries.length === 1) return 160;
    const spacing = 176 / Math.max(1, busEntries.length - 1);
    return 72 + index * spacing;
  });
</script>

<Panel title="Power Flow" domain="power" priority="primary" className="power-flow-panel">
  <div bind:this={root} class="shell">
    {#if busEntries.length === 0}
      <div class="empty">Waiting for power telemetry…</div>
    {:else}
      <svg viewBox="0 0 320 210" aria-label="Power flow display">
        <rect class="frame" x="8" y="8" width="304" height="194" rx="8" />
        <text class="title" x="18" y="22">Power Flow</text>

        <circle cx="160" cy="42" r="21" class="reactor-core" />
        <circle
          cx="160"
          cy="42"
          r="20"
          fill="none"
          stroke={reactorColor}
          stroke-width="4"
          stroke-dasharray={`${(reactorPct * reactorRing).toFixed(1)} ${reactorRing.toFixed(1)}`}
          transform="rotate(-90 160 42)"
        />
        <text class="reactor-text" x="160" y="39">REACTOR</text>
        <text class="reactor-text" x="160" y="49">{Math.round(reactorPct * 100)}%</text>
        <text class="footer" x="160" y="62">{formatKw(toNumber(totals.available_kw, 0))} avail</text>

        {#each busEntries as [busName, bus], index}
          {@const x = busXs[index] ?? 160}
          {@const available = toNumber(bus.available_kw, 0)}
          {@const requested = toNumber(bus.requested_kw, 0)}
          {@const color = busColor(available, requested)}
          {@const width = lineWidth(requested, maxBusRequest)}
          <line
            x1="160"
            y1="63"
            x2={x}
            y2="88"
            stroke={color}
            stroke-width={width}
            opacity="0.8"
          />
          <rect
            x={x - 28}
            y="88"
            width="56"
            height="28"
            rx="5"
            class="bus-card"
            stroke={color}
          />
          <text class="bus-name" x={x} y="101">{busName.toUpperCase()}</text>
          <text class="bus-meta" x={x} y="112">
            {formatKw(requested).replace(" kW", "")} / {formatKw(available).replace(" kW", "")}
          </text>

          {#each consumerList(bus) as consumer, cIndex}
            {@const cy = 142 + cIndex * 15}
            {@const draw = toNumber(consumer.draw_kw, 0)}
            {@const drawWidth = lineWidth(draw, requested || maxBusRequest)}
            {@const radius = clamp(4 + (draw / Math.max(1, requested || maxBusRequest)) * 10, 4, 10)}
            <line
              x1={x}
              y1="116"
              x2={x}
              y2={cy - 6}
              stroke={color}
              stroke-width={drawWidth}
              opacity="0.55"
            />
            <circle
              cx={x}
              cy={cy}
              r={radius}
              class="consumer-node"
              stroke={color}
            />
            <text class="consumer-meta" x={x} y={cy + 2}>{shortName(consumer.name)}</text>
            <text class="consumer-meta" x={x} y={cy + 10}>{formatKw(draw).replace(" kW", "")}</text>
          {/each}
        {/each}

        <g transform="translate(128 184)">
          <rect x="0" y="-6" width="64" height="12" rx="3" fill="none" stroke={heatColor} stroke-width="1.1" />
          <line x1="6" y1="-10" x2="6" y2="10" stroke={heatColor} stroke-width="1" />
          <line x1="16" y1="-10" x2="16" y2="10" stroke={heatColor} stroke-width="1" />
          <line x1="26" y1="-10" x2="26" y2="10" stroke={heatColor} stroke-width="1" />
          <line x1="38" y1="-10" x2="38" y2="10" stroke={heatColor} stroke-width="1" />
          <line x1="48" y1="-10" x2="48" y2="10" stroke={heatColor} stroke-width="1" />
          <line x1="58" y1="-10" x2="58" y2="10" stroke={heatColor} stroke-width="1" />
        </g>

        <text class="footer" x="160" y="197">
          THERMAL {Math.round(toNumber(thermal.temperature_percent, 0))}% • {Math.round(toNumber(thermal.hull_temperature, 0))} K
        </text>

        {#if profile?.active_profile}
          <text class="footer" x="286" y="22">PROFILE {String(profile.active_profile).toUpperCase()}</text>
        {/if}
      </svg>
    {/if}
  </div>
</Panel>

<style>
  .shell {
    padding: var(--space-sm);
  }

  svg {
    width: 100%;
    height: auto;
    display: block;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background:
      radial-gradient(circle at 50% 20%, rgba(89, 182, 255, 0.12), transparent 30%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0)),
      #091018;
  }

  .empty {
    padding: 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
    color: var(--text-secondary);
    font-size: var(--font-size-xs);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .frame {
    fill: rgba(9, 12, 18, 0.6);
    stroke: #263042;
    stroke-width: 1;
  }

  .reactor-core,
  .bus-card,
  .consumer-node {
    fill: #111722;
    stroke: #30405a;
    stroke-width: 1.2;
  }

  .title,
  .bus-name,
  .bus-meta,
  .consumer-meta,
  .reactor-text,
  .footer {
    font-family: var(--font-mono);
  }

  .title {
    font-size: 7px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    fill: #708097;
  }

  .bus-name,
  .reactor-text {
    font-size: 7px;
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
</style>
