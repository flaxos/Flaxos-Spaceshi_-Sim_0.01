<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getEngineeringShip } from "../engineering/engineeringData.js";
  import { getEngineeringState, getThermalState, toNumber } from "../engineering/engineeringData.js";

  let canvas: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null = null;
  let frame = 0;
  let outputDraft = 50;
  let sweetSpot = 0.55;
  let timer: number | null = null;
  let rafId: number | null = null;

  $: ship = getEngineeringShip($gameState);
  $: engineering = getEngineeringState(ship);
  $: thermal = getThermalState(ship);
  $: powerLevel = toNumber(engineering.reactor_percent, toNumber(engineering.reactor_output) * 100);
  $: heatLevel = Math.max(toNumber(thermal.temperature_percent), toNumber(thermal.hull_temperature) / Math.max(1, toNumber(thermal.max_temperature)) * 100);
  $: outputDraft = Math.round(powerLevel);

  onMount(() => {
    ctx = canvas.getContext("2d");
    const loop = () => {
      frame += 1;
      sweetSpot = 0.5 + Math.sin(frame / 90) * 0.18;
      draw();
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);
    return () => {
      if (rafId != null) cancelAnimationFrame(rafId);
      if (timer != null) window.clearTimeout(timer);
    };
  });

  function scheduleOutput(value: number) {
    outputDraft = value;
    if (timer != null) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      void wsClient.sendShipCommand("set_reactor_output", { output: value });
    }, 50);
  }

  function drawMeter(x: number, label: string, value: number, hue: string) {
    if (!ctx) return;
    const top = 26;
    const height = 150;
    const width = 72;
    const sweetY = top + height * (1 - sweetSpot);

    ctx.fillStyle = "rgba(12, 18, 28, 0.92)";
    ctx.fillRect(x, top, width, height);
    ctx.strokeStyle = "rgba(150, 170, 210, 0.18)";
    ctx.strokeRect(x, top, width, height);

    ctx.fillStyle = "rgba(68, 136, 255, 0.12)";
    ctx.fillRect(x + 2, sweetY - 16, width - 4, 32);

    const markerY = top + height * (1 - Math.max(0, Math.min(100, value)) / 100);
    ctx.fillStyle = hue;
    ctx.fillRect(x + 6, markerY - 6, width - 12, 12);

    ctx.fillStyle = "#d8e4ff";
    ctx.font = "12px var(--font-mono)";
    ctx.fillText(label, x, 198);
    ctx.fillText(`${Math.round(value)}%`, x, 214);
  }

  function draw() {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#060912";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#8da4d8";
    ctx.font = "12px var(--font-mono)";
    ctx.fillText("KEEP BOTH METERS INSIDE THE DRIFTING SWEET SPOT", 18, 18);

    drawMeter(28, "POWER", powerLevel, "#4da3ff");
    drawMeter(132, "HEAT", heatLevel, "#ff8047");

    const balance = Math.max(0, 100 - Math.abs(powerLevel - heatLevel) - Math.abs(powerLevel - sweetSpot * 100));
    ctx.fillStyle = "#aeb9d4";
    ctx.fillText(`BALANCE ${Math.round(balance)}%`, 252, 48);
    ctx.strokeStyle = "rgba(114, 145, 204, 0.25)";
    ctx.strokeRect(248, 60, 120, 18);
    ctx.fillStyle = "rgba(68, 136, 255, 0.7)";
    ctx.fillRect(250, 62, Math.max(0, Math.min(116, balance * 1.16)), 14);

    ctx.fillStyle = "#8da4d8";
    ctx.fillText(`SWEET SPOT ${Math.round(sweetSpot * 100)}%`, 252, 96);
    ctx.fillText(`OUTPUT ${outputDraft}%`, 252, 124);
    ctx.fillText(`THERMAL ${Math.round(heatLevel)}%`, 252, 152);
  }
</script>

<Panel title="Reactor Balance" domain="power" priority="primary" className="reactor-balance-game">
  <div class="shell">
    <canvas bind:this={canvas} width="390" height="226"></canvas>
    <div class="slider-row">
      <span>Output</span>
      <input type="range" min="0" max="100" step="1" value={outputDraft} on:input={(event) => scheduleOutput(Number((event.currentTarget as HTMLInputElement).value))} />
      <strong>{outputDraft}%</strong>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  canvas {
    width: 100%;
    height: auto;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: #060912;
  }

  .slider-row {
    display: flex;
    gap: var(--space-sm);
    align-items: center;
  }

  .slider-row span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .slider-row input {
    flex: 1;
  }

  .slider-row strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }
</style>
