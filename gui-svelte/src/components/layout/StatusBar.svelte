<script lang="ts">
  import { derived } from "svelte/store";
  import { shipState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { proposals, type Proposal } from "../../lib/stores/proposals.js";
  import ConnectionStatus from "./ConnectionStatus.svelte";

  const hull = derived(shipState, ($s) => {
    if (!$s) return null;
    const h = $s?.systems?.hull?.integrity ?? $s?.hull_integrity ?? $s?.hull ?? null;
    if (typeof h === "number") return Math.round(h * 100);
    return null;
  });

  const fuel = derived(shipState, ($s) => {
    if (!$s) return null;
    const f = $s?.systems?.propulsion?.fuel_pct ?? $s?.fuel_pct ?? null;
    if (typeof f === "number") return Math.round(f * 100);
    return null;
  });

  const driveStatus = derived(shipState, ($s) => {
    if (!$s) return "—";
    return $s?.systems?.propulsion?.status ?? $s?.drive_status ?? "nominal";
  });

  function hullColor(pct: number | null): string {
    if (pct === null) return "var(--text-dim)";
    if (pct > 70) return "var(--status-nominal)";
    if (pct > 35) return "var(--status-warning)";
    return "var(--status-critical)";
  }

  const TIER_LABELS: Record<string, string> = {
    manual:       "MANUAL",
    raw:          "RAW",
    arcade:       "ARCADE",
    "cpu-assist": "CPU-ASSIST",
  };

  // Per-station proposal counts (cpu-assist only)
  const STATION_LABELS: Array<[keyof typeof $proposals, string]> = [
    ["tactical", "TAC"],
    ["engineering", "ENG"],
    ["ops", "OPS"],
    ["comms", "COM"],
    ["fleet", "FLT"],
  ];

  $: proposalCounts = STATION_LABELS
    .map(([key, label]) => ({ label, count: ($proposals[key] as Proposal[]).length }))
    .filter((entry) => entry.count > 0);

  $: anyUrgent = (Object.values($proposals) as Proposal[][])
    .flat()
    .some((p) => p.urgent);
</script>

<header class="status-bar">
  <span class="stat-item">
    HULL:
    <span style="color: {hullColor($hull)}">
      {$hull !== null ? `${$hull}%` : "—"}
    </span>
  </span>

  <span class="stat-item">
    FUEL: <span class="stat-val">{$fuel !== null ? `${$fuel}%` : "—"}</span>
  </span>

  <span class="stat-item">
    DRIVE: <span class="stat-val">{$driveStatus}</span>
  </span>

  <span class="spacer"></span>

  {#if $tier === "cpu-assist"}
    <span class="proposal-counts" class:urgent={anyUrgent}>
      {#if proposalCounts.length === 0}
        <span class="count-idle">AI IDLE</span>
      {:else}
        {#each proposalCounts as entry}
          <span class="count-badge">{entry.label}:{entry.count}</span>
        {/each}
      {/if}
    </span>
  {/if}

  <span class="tier-badge tier-badge-{$tier}">{TIER_LABELS[$tier] ?? $tier}</span>

  <ConnectionStatus />
</header>

<style>
  .status-bar {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 0 var(--space-sm);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    flex-shrink: 0;
    height: 32px;
  }

  .stat-item {
    color: var(--text-dim);
    white-space: nowrap;
  }

  .stat-val { color: var(--text-secondary); }

  .spacer { flex: 1; }

  .proposal-counts {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.5px;
  }

  .count-badge {
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid rgba(192, 160, 255, 0.45);
    color: #c0a0ff;
    background: rgba(192, 160, 255, 0.1);
  }

  .count-idle {
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid var(--border-default);
    color: var(--text-dim);
  }

  .proposal-counts.urgent .count-badge {
    border-color: rgba(255, 170, 0, 0.6);
    color: #ffaa00;
    background: rgba(255, 170, 0, 0.1);
    animation: urgentFlash 0.8s ease-in-out infinite;
  }

  .tier-badge {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 2px 8px;
    border-radius: 3px;
    border: 1px solid var(--tier-accent, var(--border-default));
    color: var(--tier-accent, var(--text-dim));
  }

  @keyframes urgentFlash {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.5; }
  }

  @media (prefers-reduced-motion: reduce) {
    .proposal-counts.urgent .count-badge {
      animation: none;
    }
  }

  @media (max-width: 768px) {
    .status-bar {
      min-width: 0;
    }

    .proposal-counts {
      gap: 4px;
    }

    .tier-badge,
    .count-badge,
    .count-idle {
      white-space: nowrap;
    }
  }
</style>
