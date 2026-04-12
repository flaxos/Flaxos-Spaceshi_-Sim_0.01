<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { extractShipState, getTacticalContacts } from "../tactical/tacticalData.js";

  let canvas: HTMLCanvasElement | null = null;

  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship).slice(0, 6);

  onMount(() => {
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    let raf = 0;

    const draw = (time: number) => {
      if (!canvas) return;
      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;
      const sweep = (time / 1000) % (Math.PI * 2);

      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#071018";
      ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = "rgba(0,255,180,0.18)";
      [34, 64, 96].forEach((r) => {
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
      });

      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.sin(sweep) * 96, cy - Math.cos(sweep) * 96);
      ctx.strokeStyle = "rgba(0,255,180,0.55)";
      ctx.stroke();

      contacts.forEach((contact, index) => {
        const angle = ((contact.bearing + 180) * Math.PI) / 180;
        const radius = 30 + index * 14;
        const x = cx + Math.sin(angle) * radius;
        const y = cy - Math.cos(angle) * radius;
        const lit = Math.abs(angle - sweep) < 0.45;
        ctx.fillStyle = lit ? "#00ff88" : "rgba(0,255,136,0.22)";
        ctx.beginPath();
        ctx.arc(x, y, lit ? 4 : 3, 0, Math.PI * 2);
        ctx.fill();
      });

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  });
</script>

<Panel title="Sensor Sweep" domain="sensor" priority="secondary" className="sensor-sweep-game">
  <div class="shell">
    <canvas bind:this={canvas} width="220" height="220"></canvas>
    <div class="caption">Arcade ping cue. Read the sweep and react to the strongest returns.</div>
  </div>
</Panel>

<style>
  .shell { display: grid; gap: 8px; padding: var(--space-sm); }
  canvas { width: 100%; height: auto; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); background: #071018; }
  .caption { font-size: var(--font-size-xs); color: var(--text-secondary); }
</style>
