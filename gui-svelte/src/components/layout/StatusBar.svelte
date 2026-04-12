<script lang="ts">
  import { derived } from "svelte/store";
  import { shipState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import ConnectionStatus from "./ConnectionStatus.svelte";

  // Derive display values from ship state
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

  const autoTactical = derived(shipState, ($s) => {
    return $s?.auto_tactical?.enabled ?? false;
  });

  function hullColor(pct: number | null): string {
    if (pct === null) return "var(--text-dim)";
    if (pct > 70) return "var(--status-nominal)";
    if (pct > 35) return "var(--status-warning)";
    return "var(--status-critical)";
  }

  const TIER_LABELS: Record<string, string> = {
    manual:     "MANUAL",
    raw:        "RAW",
    arcade:     "ARCADE",
    "cpu-assist": "CPU-ASSIST",
  };
</script>

<header class="status-bar">
  <!-- Hull -->
  <span class="stat-item">
    HULL:
    <span style="color: {hullColor($hull)}">
      {$hull !== null ? `${$hull}%` : "—"}
    </span>
  </span>

  <!-- Fuel -->
  <span class="stat-item">
    FUEL: <span class="stat-val">{$fuel !== null ? `${$fuel}%` : "—"}</span>
  </span>

  <!-- Drive -->
  <span class="stat-item">
    DRIVE: <span class="stat-val">{$driveStatus}</span>
  </span>

  <span class="spacer"></span>

  <!-- CPU-ASSIST auto-tactical indicator -->
  {#if $tier === "cpu-assist"}
    <span class="auto-indicator" class:active={$autoTactical}>
      AUTO-TACTICAL: {$autoTactical ? "ON" : "OFF"}
    </span>
  {/if}

  <!-- Tier badge -->
  <span class="tier-badge tier-badge-{$tier}">{TIER_LABELS[$tier] ?? $tier}</span>

  <!-- Connection status -->
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

  .auto-indicator {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 1px;
    color: var(--text-dim);
    padding: 2px 6px;
    border: 1px solid var(--border-default);
    border-radius: 3px;
  }

  .auto-indicator.active {
    color: #c0a0ff;
    border-color: #c0a0ff;
    box-shadow: 0 0 6px rgba(192, 160, 255, 0.3);
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
</style>
