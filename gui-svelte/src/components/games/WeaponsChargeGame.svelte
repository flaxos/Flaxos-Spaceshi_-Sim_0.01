<script lang="ts">
  import { onMount } from "svelte";

  let phase = 0;
  let timer: number | null = null;
  let success = 0;

  function loop() {
    phase = (phase + 2.5) % 100;
    timer = window.setTimeout(loop, 40);
  }

  function pulse() {
    success = 100 - Math.abs(phase - 76) * 3;
  }

  onMount(() => {
    loop();
    return () => {
      if (timer != null) window.clearTimeout(timer);
    };
  });
</script>

<div class="card">
  <div class="track">
    <div class="sweet"></div>
    <div class="needle" style={`left:${phase}%`}></div>
  </div>
  <button on:click={pulse}>DISCHARGE</button>
  <div class="caption">Charge timing {Math.max(0, Math.round(success))}%</div>
</div>

<style>
  .card { display: grid; gap: 10px; padding: var(--space-sm); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }
  .track { position: relative; height: 18px; border-radius: 999px; background: var(--bg-input); }
  .sweet { position: absolute; left: 70%; width: 12%; height: 100%; background: rgba(0,255,136,0.22); }
  .needle { position: absolute; top: -2px; width: 4px; height: 22px; background: #ffcc44; }
  .caption { font-size: var(--font-size-xs); color: var(--text-secondary); }
</style>
