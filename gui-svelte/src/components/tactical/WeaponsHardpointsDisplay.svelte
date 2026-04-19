<script lang="ts">
  import { onDestroy } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { extractShipState, getLauncherInventory, getWeaponMounts, type WeaponMountState } from "./tacticalData.js";

  export let title = "Hardpoints";

  type VisualState = "ready" | "charging" | "reloading" | "destroyed" | "exhausted";

  const HP_LAYOUT: Record<string, { x: number; y: number; r: number }> = {
    railgun_1: { x: 262, y: 80, r: 13 },
    railgun_2: { x: 250, y: 67, r: 12 },
    pdc_1: { x: 230, y: 57, r: 10 },
    pdc_2: { x: 230, y: 103, r: 10 },
    pdc_3: { x: 175, y: 50, r: 10 },
    pdc_4: { x: 175, y: 110, r: 10 },
  };

  const AUTO_FALLBACK = [
    { x: 130, y: 58, r: 10 },
    { x: 130, y: 102, r: 10 },
    { x: 105, y: 62, r: 10 },
    { x: 105, y: 98, r: 10 },
  ];

  const COLORS: Record<VisualState | "firing", string> = {
    ready: "#00cc66",
    charging: "#ff9900",
    reloading: "#4488ff",
    exhausted: "#4a4d5c",
    destroyed: "#cc2244",
    firing: "#ffffff",
  };

  const TORP_ANCHOR = { x: 86, y: 68 };
  const MSL_ANCHOR = { x: 86, y: 96 };
  const previousAmmo = new Map<string, number>();
  const flashTimers = new Map<string, number>();

  let flashingIds = new Set<string>();

  function svgArcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
    const rad = (deg: number) => (deg - 90) * Math.PI / 180;
    const x1 = cx + r * Math.cos(rad(startDeg));
    const y1 = cy + r * Math.sin(rad(startDeg));
    const x2 = cx + r * Math.cos(rad(endDeg));
    const y2 = cy + r * Math.sin(rad(endDeg));
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  }

  function compactMountLabel(mount: WeaponMountState) {
    if (mount.weaponType === "railgun") return mount.id.endsWith("_2") ? "RG2" : "RG";
    if (mount.weaponType === "pdc") return "PDC";
    if (mount.weaponType === "torpedo") return "TORP";
    if (mount.weaponType === "missile") return "MSL";
    return mount.label.slice(0, 4);
  }

  function visualState(mount: WeaponMountState): VisualState {
    const status = mount.status.toLowerCase();
    if (!mount.enabled || status.includes("destroyed") || status.includes("offline") || status.includes("failed")) {
      return "destroyed";
    }
    if (mount.reloading) return "reloading";
    if (mount.chargeState === "charging") return "charging";
    if (mount.ammoCapacity > 0 && mount.ammo <= 0) return "exhausted";
    return "ready";
  }

  function progressFor(mount: WeaponMountState) {
    if (mount.reloading) return mount.reloadProgress;
    if (mount.chargeState === "charging") return mount.charge;
    return 0;
  }

  function progressText(mount: WeaponMountState) {
    if (mount.chargeState === "charging") return `${Math.round(mount.charge * 100)}%`;
    if (mount.reloading) return `${mount.cooldown.toFixed(1)}s`;
    if (mount.ammoCapacity > 0) return `×${mount.ammo}`;
    return mount.status.toUpperCase();
  }

  function ammoDots(ammo: number, capacity: number) {
    const visible = 8;
    const maxDots = Math.max(1, Math.min(visible, capacity || visible));
    const filled = capacity > visible
      ? Math.round((Math.max(0, ammo) / Math.max(1, capacity)) * maxDots)
      : Math.min(maxDots, Math.max(0, ammo));
    return Array.from({ length: maxDots }, (_, index) => index < filled);
  }

  function bankDots(loaded: unknown, capacity: unknown) {
    return ammoDots(Number(loaded ?? 0), Number(capacity ?? 0));
  }

  function markFlash(id: string) {
    flashingIds = new Set([...flashingIds, id]);
    const current = flashTimers.get(id);
    if (current != null) window.clearTimeout(current);
    const handle = window.setTimeout(() => {
      const next = new Set(flashingIds);
      next.delete(id);
      flashingIds = next;
      flashTimers.delete(id);
    }, 150);
    flashTimers.set(id, handle);
  }

  function syncAmmoFlashes(mounts: WeaponMountState[]) {
    const activeIds = new Set(mounts.map((mount) => mount.id));
    for (const mount of mounts) {
      const previous = previousAmmo.get(mount.id);
      if (previous != null && mount.ammo < previous) {
        markFlash(mount.id);
      }
      previousAmmo.set(mount.id, mount.ammo);
    }
    for (const id of Array.from(previousAmmo.keys())) {
      if (!activeIds.has(id)) previousAmmo.delete(id);
    }
  }

  onDestroy(() => {
    for (const handle of flashTimers.values()) window.clearTimeout(handle);
    flashTimers.clear();
  });

  $: ship = extractShipState($gameState);
  $: hardpoints = getWeaponMounts(ship);
  $: inventory = getLauncherInventory(ship);
  $: syncAmmoFlashes(hardpoints);
</script>

<Panel title={title} domain="weapons" priority="primary" className="weapons-hardpoints-panel">
  <div class="shell">
    <svg viewBox="0 0 320 174" aria-label="Weapons hardpoints schematic">
      <polygon class="hull" points="55,80 80,50 230,52 282,80 230,108 80,110" />
      <line class="centerline" x1="55" y1="80" x2="282" y2="80" />
      <ellipse cx="62" cy="68" rx="6" ry="4" class="engine-ring" />
      <ellipse cx="62" cy="92" rx="6" ry="4" class="engine-ring" />

      {#each hardpoints as mount, index}
        {@const position = HP_LAYOUT[mount.id] ?? AUTO_FALLBACK[index % AUTO_FALLBACK.length]}
        {@const state = visualState(mount)}
        {@const fillColor = flashingIds.has(mount.id) ? COLORS.firing : COLORS[state]}
        {@const progress = progressFor(mount)}
        {@const label = compactMountLabel(mount)}
        <g class="hardpoint" class:charging={state === "charging"} transform={`translate(${position.x} ${position.y})`}>
          <circle class="hp-bg" r={position.r} />
          <circle class="hp-fill" r={position.r - 3} fill={fillColor} />
          {#if progress > 0}
            <path
              class="hp-ring"
              class:pulse-ring={state === "charging"}
              d={svgArcPath(0, 0, position.r - 1, 0, progress * 360)}
              stroke={fillColor}
            />
          {/if}
          {#if state === "destroyed"}
            <line class="hp-disabled" x1={-(position.r - 3)} y1={-(position.r - 3)} x2={position.r - 3} y2={position.r - 3} />
            <line class="hp-disabled" x1={position.r - 3} y1={-(position.r - 3)} x2={-(position.r - 3)} y2={position.r - 3} />
          {/if}
          <text class="hp-label" y="2">{label}</text>
          <text class="hp-meta" y={position.r + 9}>{progressText(mount)}</text>
          <g transform={`translate(${-((ammoDots(mount.ammo, mount.ammoCapacity).length - 1) * 4)} ${position.r + 16})`}>
            {#each ammoDots(mount.ammo, mount.ammoCapacity) as filled, dotIndex}
              <circle
                class="ammo-dot"
                cx={dotIndex * 8}
                cy="0"
                r="2.1"
                fill={filled ? fillColor : "rgba(255,255,255,0.14)"}
              />
            {/each}
          </g>
        </g>
      {/each}

      <g transform={`translate(${TORP_ANCHOR.x} ${TORP_ANCHOR.y})`}>
        <text class="bank-label" x="-2" y="-10">TORP</text>
        {#each bankDots(inventory.torpedoes.loaded, inventory.torpedoes.capacity) as filled, index}
          <circle
            class="bank-dot"
            cx={index * 9}
            cy="0"
            r="3.4"
            fill={filled ? (Number(inventory.torpedoes.cooldown ?? 0) > 0 ? COLORS.reloading : COLORS.ready) : COLORS.exhausted}
          />
        {/each}
        <text class="bank-meta" x="38" y="3">
          {inventory.torpedoes.loaded ?? 0}/{inventory.torpedoes.capacity ?? 0}
        </text>
      </g>

      <g transform={`translate(${MSL_ANCHOR.x} ${MSL_ANCHOR.y})`}>
        <text class="bank-label" x="-2" y="-10">MSL</text>
        {#each bankDots(inventory.missiles.loaded, inventory.missiles.capacity) as filled, index}
          <circle
            class="bank-dot"
            cx={index * 9}
            cy="0"
            r="3.4"
            fill={filled ? (Number(inventory.missiles.cooldown ?? 0) > 0 ? COLORS.reloading : COLORS.ready) : COLORS.exhausted}
          />
        {/each}
        <text class="bank-meta" x="38" y="3">
          {inventory.missiles.loaded ?? 0}/{inventory.missiles.capacity ?? 0}
        </text>
      </g>

      <g transform="translate(10 154)">
        <circle cx="4" cy="3" r="3" fill={COLORS.ready} />
        <text class="legend" x="10" y="5">Ready</text>
        <circle cx="48" cy="3" r="3" fill={COLORS.charging} />
        <text class="legend" x="54" y="5">Charging</text>
        <circle cx="108" cy="3" r="3" fill={COLORS.reloading} />
        <text class="legend" x="114" y="5">Reloading</text>
        <circle cx="170" cy="3" r="3" fill={COLORS.destroyed} />
        <text class="legend" x="176" y="5">Offline</text>
      </g>
    </svg>
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
      radial-gradient(circle at 76% 50%, rgba(255, 102, 102, 0.08), transparent 32%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0)),
      #090f17;
  }

  .hull {
    fill: #1a1a2e;
    stroke: #3a3a5a;
    stroke-width: 1.5;
  }

  .centerline {
    stroke: #2a2a4a;
    stroke-width: 0.5;
    stroke-dasharray: 4 3;
  }

  .engine-ring {
    fill: none;
    stroke: #2a3a5a;
    stroke-width: 1;
  }

  .hp-bg {
    fill: #10151e;
    stroke: rgba(255, 255, 255, 0.15);
    stroke-width: 1;
  }

  .hp-fill {
    transition: fill var(--transition-fast);
  }

  .hp-ring {
    fill: none;
    stroke-width: 2.5;
    stroke-linecap: round;
  }

  .pulse-ring {
    animation: pulse-ring 0.85s ease-in-out infinite;
  }

  .hp-disabled {
    stroke: #cc2244;
    stroke-width: 1.6;
    stroke-linecap: round;
  }

  .hp-label,
  .hp-meta,
  .bank-label,
  .bank-meta,
  .legend {
    font-family: var(--font-mono);
  }

  .hp-label {
    font-size: 7px;
    fill: #d8e3f1;
    text-anchor: middle;
    dominant-baseline: middle;
    pointer-events: none;
  }

  .hp-meta,
  .bank-meta,
  .legend {
    font-size: 6px;
    fill: #7f8ea5;
    text-anchor: middle;
  }

  .bank-label {
    font-size: 6px;
    fill: #8a97ab;
    text-anchor: start;
    letter-spacing: 0.08em;
  }

  .bank-dot,
  .ammo-dot {
    transition: fill var(--transition-fast);
  }

  @keyframes pulse-ring {
    0%,
    100% {
      opacity: 0.45;
    }

    50% {
      opacity: 1;
    }
  }
</style>
