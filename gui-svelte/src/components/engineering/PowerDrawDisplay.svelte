<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { asRecord, formatKw, getDrawProfileBuses, toNumber } from "./engineeringData.js";

  let root: HTMLDivElement;
  let profile: Record<string, unknown> | null = null;
  let intervalHandle: number | null = null;
  let observer: IntersectionObserver | null = null;
  let isVisible = true;

  $: cpuAssistTier = $tier === "cpu-assist";
  $: buses = Object.entries(getDrawProfileBuses(asRecord(profile)));
  $: maxAxis = Math.max(
    1,
    ...buses.flatMap(([, bus]) => [toNumber(bus.available_kw), toNumber(bus.requested_kw)]),
  );

  onMount(() => {
    if (typeof IntersectionObserver !== "undefined") {
      observer = new IntersectionObserver((entries) => {
        isVisible = entries.some((entry) => entry.isIntersecting);
        if (isVisible) void refresh();
      });
      if (root) observer.observe(root);
    }

    void refresh();
    intervalHandle = window.setInterval(() => void refresh(), 3000);

    return () => {
      observer?.disconnect();
      if (intervalHandle != null) window.clearInterval(intervalHandle);
    };
  });

  async function refresh() {
    if (cpuAssistTier || !isVisible || document.hidden) return;
    try {
      const response = await wsClient.sendShipCommand("get_draw_profile", {});
      const record = asRecord(response);
      profile = (asRecord(record?.data) ?? record) as Record<string, unknown>;
    } catch {
      // best effort
    }
  }

  function widthFor(value: number): string {
    return `${Math.max(0, Math.min(100, (value / maxAxis) * 100)).toFixed(1)}%`;
  }
</script>

<Panel title="Power Draw" domain="power" priority={$tier === "raw" ? "primary" : "secondary"} className="power-draw-panel">
  <div bind:this={root} class="shell">
    {#if cpuAssistTier}
      <div class="assist">Auto-ops is managing power.</div>
    {:else if buses.length === 0}
      <div class="empty">No draw profile available.</div>
    {:else}
      {#each buses as [busName, bus]}
        {@const supply = toNumber(bus.available_kw)}
        {@const demand = toNumber(bus.requested_kw)}
        {@const deficit = demand > supply}
        <div class="bus-card" class:deficit={deficit}>
          <div class="head">
            <strong>{busName.toUpperCase()}</strong>
            <span class:deficit>{formatKw(supply)} / {formatKw(demand)}</span>
          </div>
          <div class="overlay-track">
            <div class="demand-outline" style={`width:${widthFor(demand)};`}></div>
            <div class="supply-fill" style={`width:${widthFor(supply)};`}></div>
          </div>
          <div class="meta">
            <span>Supply {formatKw(supply)}</span>
            <span>Demand {formatKw(demand)}</span>
          </div>
        </div>
      {/each}
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .bus-card,
  .assist,
  .empty {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .bus-card.deficit {
    border-color: rgba(255, 68, 68, 0.35);
    animation: deficit-pulse 0.8s ease-in-out infinite alternate;
  }

  .head,
  .meta {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .head span,
  .meta,
  .assist,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .head span.deficit {
    color: var(--status-critical);
  }

  .overlay-track {
    position: relative;
    height: 14px;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    overflow: hidden;
  }

  .demand-outline,
  .supply-fill {
    position: absolute;
    inset-block: 2px;
    left: 2px;
    border-radius: 999px;
  }

  .demand-outline {
    border: 1px solid rgba(255, 255, 255, 0.28);
    background: rgba(255, 255, 255, 0.06);
  }

  .supply-fill {
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.3), var(--tier-accent));
  }

  @keyframes deficit-pulse {
    from {
      box-shadow: 0 0 0 rgba(255, 68, 68, 0);
    }
    to {
      box-shadow: 0 0 12px rgba(255, 68, 68, 0.18);
    }
  }
</style>
