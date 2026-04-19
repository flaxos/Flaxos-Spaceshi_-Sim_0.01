<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import {
    clamp,
    getEngineeringShip,
    getSubsystemRows,
    getThermalState,
    toNumber,
    type SystemHealthRow,
  } from "./engineeringData.js";
  import { getArmorIntegrity, getArmorRows, getHullPercent, getRepairTargets } from "../ops/opsData.js";
  import { getLauncherInventory, getWeaponMounts, type WeaponMountState } from "../tactical/tacticalData.js";

  type ZoneLayout = {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    radius: number;
    labelX: number;
    labelY: number;
  };

  type ArmorLayout = {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    labelX: number;
    labelY: number;
  };

  type MountLayout = { x: number; y: number; r: number };

  const SUBSYSTEM_LAYOUTS: ZoneLayout[] = [
    { id: "sensors", x: 108, y: 72, width: 78, height: 26, radius: 8, labelX: 147, labelY: 88 },
    { id: "comms", x: 112, y: 136, width: 64, height: 24, radius: 8, labelX: 144, labelY: 151 },
    { id: "weapons", x: 176, y: 100, width: 78, height: 38, radius: 10, labelX: 215, labelY: 120 },
    { id: "reactor", x: 250, y: 92, width: 72, height: 52, radius: 12, labelX: 286, labelY: 118 },
    { id: "radiators", x: 185, y: 60, width: 118, height: 18, radius: 7, labelX: 244, labelY: 72 },
    { id: "life_support", x: 184, y: 148, width: 92, height: 26, radius: 8, labelX: 230, labelY: 164 },
    { id: "propulsion", x: 320, y: 96, width: 76, height: 44, radius: 10, labelX: 358, labelY: 121 },
  ];

  const ARMOR_LAYOUTS: ArmorLayout[] = [
    { id: "fore", x: 78, y: 106, width: 24, height: 28, labelX: 90, labelY: 102 },
    { id: "aft", x: 404, y: 102, width: 22, height: 36, labelX: 415, labelY: 98 },
    { id: "port", x: 126, y: 54, width: 106, height: 10, labelX: 179, labelY: 48 },
    { id: "starboard", x: 126, y: 186, width: 106, height: 10, labelX: 179, labelY: 214 },
    { id: "dorsal", x: 242, y: 46, width: 92, height: 10, labelX: 288, labelY: 40 },
    { id: "ventral", x: 242, y: 194, width: 92, height: 10, labelX: 288, labelY: 222 },
  ];

  const HARDPOINT_LAYOUT: Record<string, MountLayout> = {
    railgun_1: { x: 340, y: 72, r: 11 },
    railgun_2: { x: 324, y: 58, r: 10 },
    pdc_1: { x: 294, y: 58, r: 8 },
    pdc_2: { x: 294, y: 150, r: 8 },
    pdc_3: { x: 226, y: 52, r: 8 },
    pdc_4: { x: 226, y: 156, r: 8 },
  };

  const FALLBACK_MOUNTS: MountLayout[] = [
    { x: 180, y: 70, r: 8 },
    { x: 180, y: 144, r: 8 },
    { x: 150, y: 80, r: 8 },
    { x: 150, y: 134, r: 8 },
  ];

  function statusColor(percent: number) {
    if (percent < 35) return "#ff4f61";
    if (percent < 65) return "#ffb547";
    return "#33d17a";
  }

  function heatColor(percent: number) {
    if (percent >= 85) return "#ff6942";
    if (percent >= 60) return "#ffb547";
    if (percent >= 35) return "#5fbaff";
    return "#2f445d";
  }

  function mountColor(mount: WeaponMountState) {
    if (!mount.enabled || /destroyed|offline|failed/i.test(mount.status)) return "#ff4f61";
    if (mount.reloading) return "#59b6ff";
    if (mount.chargeState === "charging") return "#ffb547";
    if (mount.ammoCapacity > 0 && mount.ammo <= 0) return "#697284";
    return "#33d17a";
  }

  function compactLabel(label: string) {
    return label.replace(/_/g, " ").replace(/\s+/g, " ").trim().toUpperCase();
  }

  function damageMarks(row: SystemHealthRow) {
    if (row.damagePercent < 15) return [];
    const count = Math.min(4, Math.max(1, Math.round(row.damagePercent / 22)));
    return Array.from({ length: count }, (_, index) => index);
  }

  function bankDots(loaded: unknown, capacity: unknown) {
    const cap = Math.max(1, Math.min(8, Number(capacity ?? 0) || 1));
    const filled = Math.min(cap, Math.max(0, Math.round(((Number(loaded ?? 0) || 0) / Math.max(1, Number(capacity ?? 0) || 1)) * cap)));
    return Array.from({ length: cap }, (_, index) => index < filled);
  }

  $: ship = getEngineeringShip($gameState);
  $: subsystemRows = getSubsystemRows(ship);
  $: subsystemMap = new Map(subsystemRows.map((row) => [row.id, row]));
  $: repairTargets = getRepairTargets(ship).slice(0, 3);
  $: armorRows = getArmorRows(ship);
  $: armorMap = new Map(armorRows.map((row) => [row.id, row]));
  $: hullPercent = getHullPercent(ship);
  $: armorPercent = getArmorIntegrity(ship);
  $: thermal = getThermalState(ship);
  $: mounts = getWeaponMounts(ship);
  $: launcherInventory = getLauncherInventory(ship);
  $: heatPercent = clamp(toNumber(thermal.temperature_percent, 0), 0, 100);
  $: damagedSubsystems = subsystemRows.filter((row) => row.damagePercent > 0).length;
  $: criticalSubsystems = subsystemRows.filter((row) => row.healthPercent < 35).length;
  $: overallDamage = 100 - (subsystemRows.length ? subsystemRows.reduce((sum, row) => sum + row.healthPercent, 0) / subsystemRows.length : 100);
</script>

<Panel title="Ship Schematic" domain="power" priority="primary" className="engineering-ship-schematic-panel">
  <div class="shell">
    <div class="summary-row">
      <div class="summary-card">
        <span>Hull</span>
        <strong style={`color:${statusColor(hullPercent)};`}>{Math.round(hullPercent)}%</strong>
      </div>
      <div class="summary-card">
        <span>Armor</span>
        <strong style={`color:${statusColor(armorPercent)};`}>{Math.round(armorPercent)}%</strong>
      </div>
      <div class="summary-card">
        <span>Subsystem Damage</span>
        <strong style={`color:${statusColor(100 - overallDamage)};`}>{Math.round(overallDamage)}%</strong>
      </div>
      <div class="summary-card">
        <span>Thermal Load</span>
        <strong style={`color:${heatColor(heatPercent)};`}>{Math.round(heatPercent)}%</strong>
      </div>
    </div>

    <svg viewBox="0 0 460 244" aria-label="Engineering ship schematic">
      <defs>
        <linearGradient id="schematicHull" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#121828" />
          <stop offset="100%" stop-color="#0a0f18" />
        </linearGradient>
        <linearGradient id="schematicGlow" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="rgba(255,255,255,0.32)" />
          <stop offset="100%" stop-color="rgba(255,255,255,0)" />
        </linearGradient>
      </defs>

      <rect x="8" y="8" width="444" height="228" rx="12" class="frame" />

      <circle
        cx="286"
        cy="118"
        r="36"
        class="reactor-glow"
        style={`fill:${heatColor(Math.max(heatPercent, subsystemMap.get("reactor")?.heatPercent ?? 0))}; opacity:${0.08 + (subsystemMap.get("reactor")?.heatPercent ?? 0) / 220};`}
      />

      <polygon class="hull" points="68,122 114,74 280,66 372,96 402,122 372,148 280,178 114,170" />
      <polygon class="hull-gloss" points="106,82 274,72 360,98 280,96 118,94" />
      <line class="centerline" x1="68" y1="122" x2="402" y2="122" />

      <path class="radiator-fin" d="M214 44 L236 66" />
      <path class="radiator-fin" d="M230 40 L250 66" />
      <path class="radiator-fin" d="M246 40 L266 66" />
      <path class="radiator-fin" d="M262 44 L282 66" />
      <path class="radiator-fin lower" d="M214 200 L236 178" />
      <path class="radiator-fin lower" d="M230 204 L250 178" />
      <path class="radiator-fin lower" d="M246 204 L266 178" />
      <path class="radiator-fin lower" d="M262 200 L282 178" />

      {#each ARMOR_LAYOUTS as layout}
        {@const armor = armorMap.get(layout.id)}
        {@const integrity = armor?.integrityPercent ?? 100}
        <g>
          <rect
            x={layout.x}
            y={layout.y}
            width={layout.width}
            height={layout.height}
            rx="3"
            class="armor-band"
            style={`fill:${statusColor(integrity)}; opacity:${0.18 + integrity / 180};`}
          />
          <rect
            x={layout.x}
            y={layout.y}
            width={(layout.width * integrity) / 100}
            height={layout.height}
            rx="3"
            class="armor-track"
            style={`fill:${statusColor(integrity)};`}
          />
          <text class="armor-label" x={layout.labelX} y={layout.labelY}>
            {layout.id.slice(0, 3).toUpperCase()} {Math.round(integrity)}%
          </text>
        </g>
      {/each}

      {#each SUBSYSTEM_LAYOUTS as layout}
        {@const row = subsystemMap.get(layout.id)}
        {@const health = row?.healthPercent ?? 100}
        {@const heat = row?.heatPercent ?? 0}
        {@const repair = row?.repairStatus ?? "idle"}
        <g>
          <rect
            x={layout.x}
            y={layout.y}
            width={layout.width}
            height={layout.height}
            rx={layout.radius}
            class="zone"
            style={`fill:${statusColor(health)}; opacity:${0.12 + health / 150}; stroke:${statusColor(health)};`}
          />
          <rect
            x={layout.x + 4}
            y={layout.y + 4}
            width={Math.max(10, ((layout.width - 8) * heat) / 100)}
            height="5"
            rx="3"
            class="zone-heat"
            style={`fill:${heatColor(heat)}; opacity:${0.2 + heat / 150};`}
          />
          {#if repair !== "idle"}
            <circle cx={layout.x + layout.width - 8} cy={layout.y + 8} r="5" class="repair-dot" />
            <path d={`M ${layout.x + layout.width - 11} ${layout.y + 8} h 6 M ${layout.x + layout.width - 8} ${layout.y + 5} v 6`} class="repair-cross" />
          {/if}
          {#each damageMarks(row ?? { damagePercent: 0 } as SystemHealthRow) as mark}
            <path
              class="damage-mark"
              d={`M ${layout.x + 12 + mark * 10} ${layout.y + layout.height - 8} l 9 -10 m -4 12 l 9 -10`}
            />
          {/each}
          <text class="zone-label" x={layout.labelX} y={layout.labelY}>
            {compactLabel(layout.id === "life_support" ? "life" : layout.id)}
          </text>
          <text class="zone-metric" x={layout.labelX} y={layout.labelY + 11}>{Math.round(health)}% / {Math.round(heat)}%</text>
        </g>
      {/each}

      <g class="engine-cluster">
        <ellipse cx="406" cy="106" rx="10" ry="6" class="engine-ring" />
        <ellipse cx="406" cy="138" rx="10" ry="6" class="engine-ring" />
        <path d="M416 106 h18" class="engine-plume" style={`stroke:${statusColor(subsystemMap.get("propulsion")?.healthPercent ?? 100)}; opacity:${0.35 + (subsystemMap.get("propulsion")?.healthPercent ?? 0) / 180};`} />
        <path d="M416 138 h14" class="engine-plume" style={`stroke:${statusColor(subsystemMap.get("propulsion")?.healthPercent ?? 100)}; opacity:${0.25 + (subsystemMap.get("propulsion")?.healthPercent ?? 0) / 200};`} />
      </g>

      {#each mounts as mount, index}
        {@const position = HARDPOINT_LAYOUT[mount.id] ?? FALLBACK_MOUNTS[index % FALLBACK_MOUNTS.length]}
        {@const color = mountColor(mount)}
        <g class="mount">
          <circle cx={position.x} cy={position.y} r={position.r} class="mount-ring" style={`stroke:${color};`} />
          <circle cx={position.x} cy={position.y} r={Math.max(4, position.r - 4)} class="mount-core" style={`fill:${color}; opacity:${mount.ready ? 0.95 : 0.72};`} />
          <text class="mount-label" x={position.x} y={position.y + position.r + 10}>{mount.weaponType.toUpperCase()}</text>
        </g>
      {/each}

      <g transform="translate(34 194)">
        <text class="bank-title" x="0" y="-14">TORPEDO BAY</text>
        {#each bankDots(launcherInventory.torpedoes.loaded, launcherInventory.torpedoes.capacity) as filled, index}
          <circle cx={index * 12} cy="0" r="4.2" class="bank-dot" style={`fill:${filled ? "#59b6ff" : "rgba(255,255,255,0.1)"};`} />
        {/each}
      </g>

      <g transform="translate(34 220)">
        <text class="bank-title" x="0" y="-14">MISSILE CELL</text>
        {#each bankDots(launcherInventory.missiles.loaded, launcherInventory.missiles.capacity) as filled, index}
          <circle cx={index * 12} cy="0" r="4.2" class="bank-dot" style={`fill:${filled ? "#ffb547" : "rgba(255,255,255,0.1)"};`} />
        {/each}
      </g>

      {#if repairTargets.length > 0}
        {#each repairTargets as target, index}
          {@const zone = SUBSYSTEM_LAYOUTS.find((entry) => entry.id === target.id)}
          {@const zoneX = zone ? zone.x + zone.width : 310}
          {@const zoneY = zone ? zone.y + zone.height / 2 : 90 + index * 28}
          {@const calloutY = 42 + index * 32}
          <g class="repair-callout">
            <path d={`M ${zoneX} ${zoneY} C 340 ${zoneY}, 352 ${calloutY + 6}, 364 ${calloutY + 6}`} />
            <rect x="364" y={calloutY - 6} width="76" height="20" rx="5" />
            <text x="370" y={calloutY + 1}>{compactLabel(target.label).slice(0, 11)}</text>
            <text class="repair-sub" x="370" y={calloutY + 10}>{Math.round(target.damagePercent)}% DMG</text>
          </g>
        {/each}
      {/if}

      <text class="footer" x="30" y="28">CRITICAL {criticalSubsystems}</text>
      <text class="footer" x="120" y="28">DAMAGED {damagedSubsystems}</text>
      <text class="footer" x="228" y="28">REPAIRS {repairTargets.length}</text>
      <text class="footer" x="320" y="28">HULL TEMP {Math.round(toNumber(thermal.hull_temperature, 0))} K</text>
    </svg>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .summary-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .summary-card {
    display: grid;
    gap: 4px;
    padding: 8px 10px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.02);
  }

  .summary-card span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .summary-card strong {
    font-family: var(--font-mono);
    font-size: 1rem;
  }

  svg {
    width: 100%;
    height: auto;
    display: block;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background:
      radial-gradient(circle at 72% 50%, rgba(255, 102, 102, 0.08), transparent 28%),
      radial-gradient(circle at 20% 50%, rgba(95, 186, 255, 0.05), transparent 30%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 25%),
      #081019;
  }

  .frame {
    fill: rgba(4, 8, 14, 0.74);
    stroke: rgba(255, 255, 255, 0.08);
  }

  .hull {
    fill: url(#schematicHull);
    stroke: rgba(126, 172, 255, 0.3);
    stroke-width: 1.7;
  }

  .hull-gloss {
    fill: rgba(255, 255, 255, 0.04);
  }

  .centerline {
    stroke: rgba(255, 255, 255, 0.12);
    stroke-dasharray: 4 4;
  }

  .radiator-fin {
    fill: none;
    stroke: rgba(130, 188, 255, 0.22);
    stroke-width: 2.2;
    stroke-linecap: round;
  }

  .radiator-fin.lower {
    stroke: rgba(130, 188, 255, 0.16);
  }

  .armor-band {
    stroke: rgba(255, 255, 255, 0.12);
  }

  .armor-track {
    opacity: 0.88;
  }

  .armor-label,
  .zone-label,
  .zone-metric,
  .mount-label,
  .bank-title,
  .footer,
  .repair-callout text {
    font-family: var(--font-mono);
  }

  .armor-label,
  .zone-label,
  .mount-label,
  .bank-title,
  .footer {
    font-size: 8px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    fill: rgba(220, 232, 255, 0.78);
  }

  .zone-metric,
  .repair-sub {
    font-size: 7px;
    letter-spacing: 0.05em;
    fill: rgba(182, 196, 218, 0.72);
  }

  .zone {
    stroke-width: 1.3;
  }

  .zone-heat {
    stroke: none;
  }

  .repair-dot {
    fill: rgba(255, 255, 255, 0.12);
    stroke: rgba(95, 186, 255, 0.82);
  }

  .repair-cross {
    stroke: rgba(95, 186, 255, 0.92);
    stroke-width: 1.2;
    stroke-linecap: round;
  }

  .damage-mark {
    fill: none;
    stroke: rgba(255, 92, 92, 0.9);
    stroke-width: 1.2;
    stroke-linecap: round;
  }

  .reactor-glow {
    filter: blur(12px);
  }

  .engine-ring {
    fill: none;
    stroke: rgba(124, 168, 255, 0.24);
    stroke-width: 1.2;
  }

  .engine-plume {
    fill: none;
    stroke-width: 2.4;
    stroke-linecap: round;
  }

  .mount-ring {
    fill: rgba(0, 0, 0, 0.4);
    stroke-width: 1.4;
  }

  .mount-core {
    stroke: rgba(255, 255, 255, 0.12);
  }

  .mount-label {
    text-anchor: middle;
    fill: rgba(204, 214, 232, 0.74);
  }

  .bank-dot {
    stroke: rgba(255, 255, 255, 0.1);
  }

  .repair-callout path {
    fill: none;
    stroke: rgba(95, 186, 255, 0.42);
    stroke-width: 1.1;
    stroke-dasharray: 3 3;
  }

  .repair-callout rect {
    fill: rgba(9, 18, 29, 0.9);
    stroke: rgba(95, 186, 255, 0.34);
  }

  .repair-callout text {
    font-size: 7.2px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    fill: rgba(220, 232, 255, 0.82);
  }

  @media (max-width: 920px) {
    .summary-row {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
