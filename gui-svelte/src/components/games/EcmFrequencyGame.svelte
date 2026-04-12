<script lang="ts">
  import { onMount } from "svelte";

  let slider = 40;
  let target = 62;
  let delta = 22;
  let timer: number | null = null;

  function drift() {
    target = 50 + Math.sin(Date.now() / 900) * 26;
    delta = Math.abs(slider - target);
    timer = window.setTimeout(drift, 60);
  }

  onMount(() => {
    drift();
    return () => {
      if (timer != null) window.clearTimeout(timer);
    };
  });
</script>

<div class="card">
  <input type="range" min="0" max="100" bind:value={slider} />
  <div class="readout">Filter delta {Math.round(delta)}</div>
  <div class="track">
    <div class="target" style={`left:${target}%`}></div>
    <div class="user" style={`left:${slider}%`}></div>
  </div>
</div>

<style>
  .card { display: grid; gap: 10px; padding: var(--space-sm); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }
  .track { position: relative; height: 18px; border-radius: 999px; background: var(--bg-input); }
  .target, .user { position: absolute; top: -2px; width: 4px; height: 22px; transform: translateX(-50%); }
  .target { background: #ff4444; }
  .user { background: #00aaff; }
  .readout { font-size: var(--font-size-xs); color: var(--text-secondary); }
</style>
