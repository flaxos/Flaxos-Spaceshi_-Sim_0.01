<script lang="ts">
  import { derived } from "svelte/store";
  import { shipState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { proposals, type Proposal } from "../../lib/stores/proposals.js";
  import { extractShipState, getOrientation, getVelocity, magnitude, toNumber, toStringValue, asRecord, getSystem } from "../helm/helmData.js";

  // Mission clock (local time for now; server mission time can replace this)
  let missionTime = "00:00:00";
  setInterval(() => {
    const d = new Date();
    missionTime = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  }, 500);

  // Hull integrity (supports both nested systems.hull and top-level)
  const hull = derived(shipState, ($s) => {
    if (!$s) return null;
    const h = $s?.systems?.hull?.integrity ?? $s?.hull_integrity ?? $s?.hull ?? null;
    if (typeof h === "number") return h > 1 ? Math.round(h) : Math.round(h * 100);
    return null;
  });

  // Fuel percentage
  const fuel = derived(shipState, ($s) => {
    if (!$s) return null;
    const f = $s?.systems?.propulsion?.fuel_pct ?? $s?.fuel_pct ?? null;
    if (typeof f === "number") return f > 1 ? Math.round(f) : Math.round(f * 100);
    return null;
  });

  // Reactor output percent
  const reactor = derived(shipState, ($s) => {
    if (!$s) return null;
    const r = $s?.systems?.reactor?.output_pct ?? $s?.systems?.power?.reactor_output ?? null;
    if (typeof r === "number") return Math.round(r > 1 ? r : r * 100);
    return null;
  });

  // Speed (m/s)
  // shipState is already extracted; passing through extractShipState is a no-op guard
  // that also normalizes undefined → {} so downstream helpers don't crash.
  const speed = derived(shipState, ($s) => {
    const vel = getVelocity(extractShipState($s as Record<string, unknown>));
    return magnitude(vel);
  });

  // Heading (yaw, deg)
  const heading = derived(shipState, ($s) => {
    const ship = extractShipState($s as Record<string, unknown>);
    return getOrientation(ship).yaw;
  });

  // Heat state (K current / K max)
  const heat = derived(shipState, ($s) => {
    if (!$s) return { current: 0, max: 500 };
    const thermal = asRecord($s)?.thermal ?? getSystem($s as never, "thermal");
    const current = toNumber(asRecord(thermal)?.heat, toNumber(asRecord($s)?.heat, 0));
    const max = toNumber(asRecord(thermal)?.heat_max, toNumber(asRecord($s)?.heat_max, 500));
    return { current, max };
  });

  // Any impaired subsystems → alert indicator
  const subsystemAlert = derived(shipState, ($s) => {
    const sys = asRecord($s)?.systems ?? {};
    for (const [name, value] of Object.entries(sys as Record<string, unknown>)) {
      const status = asRecord(value)?.status;
      if (typeof status === "string" && /impair|damag|critical/i.test(status)) return name;
    }
    return null;
  });

  // Ship identity
  const shipInfo = derived(shipState, ($s) => {
    const ship = asRecord($s) ?? {};
    return {
      name: toStringValue(ship.name, toStringValue(ship.id, "MCRN Rocinante")),
      cls: toStringValue(ship.class_name, toStringValue(ship.ship_class, "Corvette")),
    };
  });

  function normPct(x: number | null): number {
    if (x === null) return 0;
    return Math.max(0, Math.min(100, x));
  }

  function heatColor(pct: number): string {
    if (pct > 80) return "var(--crit)";
    if (pct > 60) return "var(--warn)";
    return "#1e8cff";
  }

  // Proposal counts (preserved from prior design)
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

  $: heatPct = $heat.max > 0 ? ($heat.current / $heat.max) * 100 : 0;
  $: hc = heatColor(heatPct);
</script>

<header class="status-bar">
  <!-- Ship identity -->
  <div class="cell identity">
    <span class="dot nominal" aria-hidden="true"></span>
    <div class="ident-text">
      <div class="ship-name">{$shipInfo.name.toUpperCase()}</div>
      <div class="ship-cls">{$shipInfo.cls.toUpperCase()}</div>
    </div>
  </div>

  <!-- SPD -->
  <div class="cell vital">
    <span class="lbl">SPD</span>
    <span class="val">
      {$speed.toFixed(1)}<span class="unit">m/s</span>
    </span>
  </div>

  <!-- HDG -->
  <div class="cell vital">
    <span class="lbl">HDG</span>
    <span class="val">{String(Math.round($heading < 0 ? $heading + 360 : $heading)).padStart(3, "0")}°</span>
  </div>

  <!-- FUEL -->
  <div class="cell vital">
    <span class="lbl">FUEL</span>
    <span class="val" class:crit={$fuel !== null && $fuel < 20}>
      {$fuel !== null ? $fuel : "--"}<span class="unit">%</span>
    </span>
  </div>

  <!-- HULL -->
  <div class="cell vital">
    <span class="lbl">HULL</span>
    <span class="val" class:crit={$hull !== null && $hull < 60}>
      {$hull !== null ? $hull : "--"}<span class="unit">%</span>
    </span>
  </div>

  <!-- REACTOR -->
  <div class="cell vital">
    <span class="lbl">RCT</span>
    <span class="val">
      {$reactor !== null ? $reactor : "--"}<span class="unit">%</span>
    </span>
  </div>

  <!-- Thermal bar -->
  <div class="cell thermal">
    <div class="thermal-head">
      <span class="lbl">THERMAL</span>
      <span class="thermal-k" style="color: {hc}">{Math.round($heat.current)}K</span>
    </div>
    <div class="bar-track">
      <div class="bar-fill" style="width: {normPct(heatPct)}%; background: {hc}; box-shadow: {heatPct > 65 ? `0 0 6px ${hc}55` : 'none'};"></div>
    </div>
  </div>

  {#if $subsystemAlert}
    <div class="cell alert">
      <span class="dot impaired" aria-hidden="true"></span>
      <span class="alert-text">SUBSYS IMPAIRED</span>
    </div>
  {/if}

  <!-- CPU proposals (cpu-assist tier) -->
  {#if $tier === "cpu-assist"}
    <div class="cell proposals" class:urgent={anyUrgent}>
      {#if proposalCounts.length === 0}
        <span class="count-idle">AI IDLE</span>
      {:else}
        {#each proposalCounts as entry}
          <span class="count-badge">{entry.label}:{entry.count}</span>
        {/each}
      {/if}
    </div>
  {/if}

  <span class="spacer"></span>

  <!-- Mission clock -->
  <div class="cell mission">
    <span class="lbl">MISSION</span>
    <span class="clock">{missionTime}</span>
  </div>
</header>

<style>
  .status-bar {
    display: flex;
    align-items: center;
    gap: 0;
    padding: 0 2px;
    height: 36px;
    flex-shrink: 0;
    background: var(--bg-raised);
    border-bottom: 2px solid var(--tier-accent, #1e8cff);
  }

  .cell {
    height: 100%;
    display: flex;
    align-items: center;
    padding: 0 10px;
    border-right: 1px solid var(--bd-subtle);
    font-family: var(--font-mono);
  }

  .cell.identity {
    padding: 0 12px;
    border-right: 1px solid var(--bd-default);
    gap: 7px;
  }

  .cell.mission {
    padding: 0 12px;
    border-right: none;
    border-left: 1px solid var(--bd-default);
    flex-direction: column;
    align-items: flex-end;
    justify-content: center;
  }

  .cell.vital {
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    min-width: 52px;
  }

  .cell.thermal {
    flex-direction: column;
    align-items: stretch;
    justify-content: center;
    gap: 3px;
    min-width: 110px;
  }

  .cell.alert {
    gap: 5px;
  }

  .cell.proposals {
    gap: 6px;
  }

  .spacer { flex: 1; }

  .ident-text {
    display: flex;
    flex-direction: column;
  }

  .ship-name {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--tx-bright);
    letter-spacing: 0.06em;
  }

  .ship-cls {
    font-size: 0.52rem;
    color: var(--tx-dim);
    letter-spacing: 0.06em;
  }

  .lbl {
    font-size: 0.48rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--tx-dim);
  }

  .val {
    font-size: 0.76rem;
    font-weight: 600;
    color: var(--tx-bright);
    font-variant-numeric: tabular-nums;
  }

  .val.crit {
    color: var(--crit);
    animation: critFlicker 1.8s step-end infinite;
  }

  .unit {
    font-size: 0.5rem;
    color: var(--tx-dim);
    margin-left: 1px;
  }

  .thermal-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }

  .thermal-k {
    font-size: 0.55rem;
  }

  .bar-track {
    height: 4px;
    background: var(--bg-input);
    border-radius: 1px;
    overflow: hidden;
    width: 100%;
  }

  .bar-fill {
    height: 100%;
    transition: width .4s ease, background .4s ease;
  }

  .dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .dot.nominal {
    background: var(--nom);
    box-shadow: 0 0 9px rgba(0, 221, 106, 0.7);
  }

  .dot.impaired {
    background: var(--warn);
    box-shadow: 0 0 9px rgba(239, 160, 32, 0.7);
    animation: pulse 2s ease-in-out infinite;
  }

  .alert-text {
    font-size: 0.58rem;
    color: var(--warn);
    font-weight: 700;
    letter-spacing: 0.06em;
  }

  .clock {
    font-size: 0.7rem;
    color: var(--tx-bright);
  }

  .count-badge {
    font-size: 0.58rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid rgba(170, 136, 255, 0.45);
    color: #aa88ff;
    background: rgba(170, 136, 255, 0.1);
  }

  .count-idle {
    font-size: 0.58rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid var(--bd-default);
    color: var(--tx-dim);
  }

  .cell.proposals.urgent .count-badge {
    border-color: rgba(239, 160, 32, 0.6);
    color: var(--warn);
    background: rgba(239, 160, 32, 0.1);
    animation: pulse 0.8s ease-in-out infinite;
  }

  @media (max-width: 900px) {
    .cell.mission { display: none; }
    .cell.identity .ship-cls { display: none; }
  }

  @media (max-width: 600px) {
    .cell.vital { min-width: 38px; padding: 0 6px; }
    .cell.thermal { display: none; }
  }
</style>
