<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import { extractShipState, getTacticalContacts, getWeaponMounts, type TacticalContact } from "./tacticalData.js";

  let canvas: HTMLCanvasElement | null = null;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let offsetX = 0;
  let offsetY = 0;
  let zoom = 0.0015;

  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship);
  $: mounts = getWeaponMounts(ship);
  $: maxRange = mounts.reduce((max, mount) => Math.max(max, mount.range), 50_000);

  onMount(() => {
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    let raf = 0;

    const draw = () => {
      if (!canvas) return;
      const width = canvas.width;
      const height = canvas.height;
      const cx = width / 2 + offsetX;
      const cy = height / 2 + offsetY;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#081019";
      ctx.fillRect(0, 0, width, height);

      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, height);
      ctx.moveTo(0, cy);
      ctx.lineTo(width, cy);
      ctx.stroke();

      [maxRange * 0.3, maxRange * 0.6, maxRange].forEach((range, index) => {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(0, 170, 255, ${0.1 + index * 0.06})`;
        ctx.arc(cx, cy, range * zoom, 0, Math.PI * 2);
        ctx.stroke();
      });

      contacts.forEach((contact) => {
        const x = cx + contact.position.x * zoom;
        const y = cy - contact.position.y * zoom;
        ctx.strokeStyle = "rgba(255,255,255,0.16)";
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(x, y);
        ctx.stroke();

        if (contact.confidence < 0.95) {
          ctx.strokeStyle = "rgba(255, 216, 77, 0.3)";
          ctx.beginPath();
          ctx.ellipse(x, y, 12 + (1 - contact.confidence) * 18, 8 + (1 - contact.confidence) * 12, 0, 0, Math.PI * 2);
          ctx.stroke();
        }

        ctx.fillStyle = contact.id === $selectedTacticalTargetId ? "#00ffaa" : "#74b9ff";
        ctx.beginPath();
        ctx.arc(x, y, 4 + contact.threatScore * 4, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.font = "11px JetBrains Mono";
        ctx.fillText(`${contact.id} ${contact.classification ?? ""}`, x + 8, y - 8);
      });

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  });

  async function lockNearest(event: MouseEvent) {
    if (!canvas || contacts.length === 0) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((event.clientX - rect.left) * canvas.width) / rect.width;
    const y = ((event.clientY - rect.top) * canvas.height) / rect.height;
    const cx = canvas.width / 2 + offsetX;
    const cy = canvas.height / 2 + offsetY;
    let best: TacticalContact | null = null;
    let bestDistance = Number.POSITIVE_INFINITY;

    for (const contact of contacts) {
      const dotX = cx + contact.position.x * zoom;
      const dotY = cy - contact.position.y * zoom;
      const distance = Math.hypot(dotX - x, dotY - y);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = contact;
      }
    }

    if (!best || bestDistance > 28) return;
    selectedTacticalTargetId.set(best.id);
    await wsClient.sendShipCommand("lock_target", { contact_id: best.id });
  }

  function startDrag(event: MouseEvent) {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
  }

  function onMove(event: MouseEvent) {
    if (!dragging) return;
    offsetX += event.clientX - lastX;
    offsetY += event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
  }

  function endDrag() {
    dragging = false;
  }

  function onWheel(event: WheelEvent) {
    event.preventDefault();
    zoom = Math.min(0.01, Math.max(0.0002, zoom * (event.deltaY > 0 ? 0.88 : 1.12)));
  }
</script>

<Panel title="Tactical Map" domain="sensor" priority="primary" className="tactical-map-panel">
  <div class="shell">
    <canvas
      bind:this={canvas}
      width="520"
      height="360"
      on:click={lockNearest}
      on:mousedown={startDrag}
      on:mousemove={onMove}
      on:mouseup={endDrag}
      on:mouseleave={endDrag}
      on:wheel={onWheel}
    ></canvas>
    <div class="caption">Drag to pan. Scroll to zoom. Click a contact to lock.</div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: 8px;
    padding: var(--space-sm);
  }

  canvas {
    width: 100%;
    height: auto;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: #081019;
    cursor: crosshair;
  }

  .caption {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }
</style>
