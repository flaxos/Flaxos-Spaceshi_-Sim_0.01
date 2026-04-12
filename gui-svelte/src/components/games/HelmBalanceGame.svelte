<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { extractShipState, getOrientation, magnitude, toVec3 } from "../helm/helmData.js";

  let canvas: HTMLCanvasElement | null = null;
  let drift = 0;
  let rotation = 0;

  $: ship = extractShipState($gameState);
  $: drift = Math.min(1, Math.abs(getOrientation(ship).yaw) / 180);
  $: rotation = Math.min(1, magnitude(toVec3(ship.angular_velocity)) / 40);

  onMount(() => {
    if (!canvas) return undefined;

    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    let raf = 0;

    const draw = (time: number) => {
      if (!canvas) return;
      const width = canvas.width;
      const height = canvas.height;
      const centerX = width / 2;
      const centerY = height / 2;
      const zoneWidth = 76;
      const zoneHeight = 34;
      const ballX = centerX + Math.sin(time / 500) * 10 + (drift - 0.5) * 80;
      const ballY = centerY + Math.cos(time / 650) * 8 + (rotation - 0.5) * 58;

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#0d1622";
      ctx.fillRect(0, 0, width, height);

      ctx.strokeStyle = "rgba(68, 136, 255, 0.35)";
      ctx.lineWidth = 1;
      ctx.strokeRect(centerX - zoneWidth / 2, centerY - zoneHeight / 2, zoneWidth, zoneHeight);

      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.beginPath();
      ctx.moveTo(centerX, 10);
      ctx.lineTo(centerX, height - 10);
      ctx.moveTo(10, centerY);
      ctx.lineTo(width - 10, centerY);
      ctx.stroke();

      const inZone = Math.abs(ballX - centerX) < zoneWidth / 2 && Math.abs(ballY - centerY) < zoneHeight / 2;
      ctx.fillStyle = inZone ? "#00ff88" : "#ffaa00";
      ctx.beginPath();
      ctx.arc(ballX, ballY, 10, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "rgba(255,255,255,0.75)";
      ctx.font = "11px JetBrains Mono";
      ctx.fillText("trim zone", centerX - 24, centerY - zoneHeight / 2 - 8);

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  });
</script>

<Panel title="Balance Game" domain="helm" priority="secondary" className="helm-balance-game">
  <div class="game-shell">
    <canvas bind:this={canvas} width="220" height="140"></canvas>
    <div class="caption">Arcade stability cue. Keep the ball centered while the ship settles.</div>
  </div>
</Panel>

<style>
  .game-shell {
    display: grid;
    gap: 10px;
    padding: var(--space-sm);
  }

  canvas {
    width: 100%;
    height: auto;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: #0d1622;
  }

  .caption {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }
</style>
