<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getTacticalContacts } from "../tactical/tacticalData.js";
  import {
    fleetIdFromRecord,
    fleetShipsFromStatus,
    fleetSummaryFromTactical,
    getFleetShip,
    type FleetShipRow,
  } from "./fleetData.js";

  const SCALES = [5_000, 10_000, 50_000, 100_000, 500_000];

  let canvas: HTMLCanvasElement | null = null;
  let wrapper: HTMLDivElement | null = null;
  let scale = SCALES[2];
  let panX = 0;
  let panY = 0;
  let dragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let originPanX = 0;
  let originPanY = 0;
  let tacticalSummary: Record<string, unknown> = {};
  let fleetRecord: Record<string, unknown> = {};
  let ships: FleetShipRow[] = [];
  let pollHandle: number | null = null;
  let resizeObserver: ResizeObserver | null = null;

  $: ship = getFleetShip($gameState);
  $: localContacts = getTacticalContacts(ship);
  $: fleetId = fleetIdFromRecord(fleetRecord);

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 3000);

    if (wrapper) {
      resizeObserver = new ResizeObserver(() => draw());
      resizeObserver.observe(wrapper);
    }

    draw();
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
      resizeObserver?.disconnect();
    };
  });

  $: draw();

  async function refresh() {
    if (document.hidden) return;
    try {
      const [tactical, status] = await Promise.all([
        wsClient.sendShipCommand("fleet_tactical", {}),
        wsClient.sendShipCommand("fleet_status", {}),
      ]);
      tacticalSummary = (tactical as Record<string, unknown>) ?? {};
      fleetRecord = (status as Record<string, unknown>) ?? {};
      ships = fleetShipsFromStatus(status);
    } catch {
      tacticalSummary = {};
      ships = [];
    }
  }

  function zoom(delta: number) {
    const index = Math.max(0, Math.min(SCALES.length - 1, SCALES.indexOf(scale) + delta));
    scale = SCALES[index];
  }

  function toScreen(x: number, z: number, width: number, height: number): [number, number] {
    const ppm = Math.min(width, height) / 2 / scale;
    return [width / 2 + (x - panX) * ppm, height / 2 - (z - panY) * ppm];
  }

  function draw() {
    if (!canvas || !wrapper) return;
    const rect = wrapper.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#0b1219";
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "rgba(120,180,255,0.1)";
    ctx.lineWidth = 1;
    const gridStep = Math.max(32, Math.min(width, height) / 6);
    for (let x = 0; x <= width; x += gridStep) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y <= height; y += gridStep) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    if (ships.length > 1) {
      ctx.strokeStyle = "rgba(80,166,255,0.28)";
      ctx.setLineDash([6, 6]);
      for (let index = 1; index < ships.length; index += 1) {
        const a = ships[index - 1];
        const b = ships[index];
        const [ax, ay] = toScreen(a.position.x, a.position.z, width, height);
        const [bx, by] = toScreen(b.position.x, b.position.z, width, height);
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
      }
      ctx.setLineDash([]);
    }

    ships.forEach((row) => {
      const [sx, sy] = toScreen(row.position.x, row.position.z, width, height);
      const size = row.isFlagship ? 9 : 7;
      ctx.fillStyle = row.isFlagship ? "#ffd46b" : "#00ff88";
      ctx.beginPath();
      ctx.moveTo(sx, sy - size);
      ctx.lineTo(sx - size * 0.75, sy + size * 0.7);
      ctx.lineTo(sx + size * 0.75, sy + size * 0.7);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "#d4e6ff";
      ctx.font = "10px JetBrains Mono";
      ctx.fillText(row.name, sx + size + 4, sy + 4);
    });

    localContacts.forEach((contact) => {
      const [tx, ty] = toScreen(contact.position.x, contact.position.z, width, height);
      ctx.fillStyle = contact.threatLevel === "red" ? "#ff4444" : contact.threatLevel === "orange" ? "#ff9f43" : "#5dd3ff";
      ctx.beginPath();
      ctx.moveTo(tx, ty - 6);
      ctx.lineTo(tx + 6, ty);
      ctx.lineTo(tx, ty + 6);
      ctx.lineTo(tx - 6, ty);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "#9fb8d9";
      ctx.font = "10px JetBrains Mono";
      ctx.fillText(contact.id, tx + 10, ty + 4);
    });
  }

  function handlePointerDown(event: PointerEvent) {
    dragging = true;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    originPanX = panX;
    originPanY = panY;
  }

  function handlePointerMove(event: PointerEvent) {
    if (!dragging || !wrapper) return;
    const rect = wrapper.getBoundingClientRect();
    const ppm = Math.min(rect.width, rect.height) / 2 / scale;
    panX = originPanX - (event.clientX - dragStartX) / ppm;
    panY = originPanY + (event.clientY - dragStartY) / ppm;
  }

  function handlePointerUp() {
    dragging = false;
  }
</script>

<svelte:window on:pointermove={handlePointerMove} on:pointerup={handlePointerUp} />

<Panel title="Fleet Tactical" domain="weapons" priority="primary" className="fleet-tactical-display">
  <div class="shell">
    <div class="toolbar">
      <div class="summary">
        <strong>{fleetId || "NO FLEET"}</strong>
        <span>{ships.length} ships · {Number(fleetSummaryFromTactical(tacticalSummary).contacts_tracked ?? localContacts.length)} contacts</span>
      </div>
      <label>
        <span>Scale</span>
        <select bind:value={scale}>
          {#each SCALES as option}
            <option value={option}>{option >= 1000 ? `${option / 1000} km` : `${option} m`}</option>
          {/each}
        </select>
      </label>
    </div>

    <div class="canvas-wrap" bind:this={wrapper}>
      <canvas bind:this={canvas} on:pointerdown={handlePointerDown} on:wheel|preventDefault={(event) => zoom(event.deltaY > 0 ? 1 : -1)}></canvas>
      <div class="legend">
        <span class="friendly">▲ Friendly</span>
        <span class="hostile">◆ Threat</span>
      </div>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
    min-height: 420px;
  }

  .toolbar,
  .summary {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .summary span,
  label span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  label {
    display: grid;
    gap: 4px;
  }

  select {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  .canvas-wrap {
    position: relative;
    min-height: 360px;
    border-radius: var(--radius-sm);
    overflow: hidden;
    border: 1px solid var(--border-subtle);
    background: #0b1219;
  }

  canvas {
    width: 100%;
    height: 100%;
    display: block;
    touch-action: none;
    cursor: grab;
  }

  .legend {
    position: absolute;
    left: 10px;
    bottom: 10px;
    display: flex;
    gap: 12px;
    padding: 6px 8px;
    border-radius: 999px;
    background: rgba(5, 8, 12, 0.75);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .friendly {
    color: #00ff88;
  }

  .hostile {
    color: #ff6666;
  }
</style>
