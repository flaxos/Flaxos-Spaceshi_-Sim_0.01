<script lang="ts">
  import { onMount } from "svelte";

  let cursor = 0;
  let score = 0;
  let zone = 42;
  let direction = 1;
  let ticker: number | null = null;

  function tick() {
    cursor += direction * 1.8;
    if (cursor >= 100 || cursor <= 0) direction *= -1;
    zone = 45 + Math.sin(Date.now() / 700) * 18;
    ticker = window.setTimeout(tick, 24);
  }

  function capture() {
    const delta = Math.abs(cursor - zone);
    score = Math.max(0, 100 - delta * 4);
  }

  onMount(() => {
    tick();
    return () => {
      if (ticker != null) window.clearTimeout(ticker);
    };
  });
</script>

<div class="game-card">
  <div class="bar">
    <div class="zone" style={`left:${zone - 8}%`}></div>
    <div class="cursor" style={`left:${cursor}%`}></div>
  </div>
  <button on:click={capture}>LOCK</button>
  <div class="score">Lock score {Math.round(score)}%</div>
</div>

<style>
  .game-card { display: grid; gap: 10px; padding: var(--space-sm); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }
  .bar { position: relative; height: 22px; border-radius: 999px; background: var(--bg-input); overflow: hidden; }
  .zone { position: absolute; top: 0; width: 16%; height: 100%; background: rgba(0,255,136,0.22); }
  .cursor { position: absolute; top: 0; width: 4px; height: 100%; background: #00aaff; }
  .score { font-size: var(--font-size-xs); color: var(--text-secondary); }
</style>
