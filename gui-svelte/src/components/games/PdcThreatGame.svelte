<script lang="ts">
  import { gameState } from "../../lib/stores/gameState.js";
  import { extractShipState, getThreatList } from "../tactical/tacticalData.js";

  $: ship = extractShipState($gameState);
  $: threats = getThreatList(ship).slice(0, 6);
  let score = 0;

  function hit(id: string) {
    score += id.length;
  }
</script>

<div class="radial-card">
  <div class="radial">
    {#each threats as threat, index}
      <button
        class="pip {threat.threatLevel}"
        style={`left:${50 + Math.sin(index * 1.1) * 34}%; top:${50 - Math.cos(index * 1.1) * 34}%;`}
        aria-label={`Intercept ${threat.id}`}
        on:click={() => hit(threat.id)}
      ></button>
    {/each}
  </div>
  <div class="caption">Threat intercept score {score}</div>
</div>

<style>
  .radial-card { display: grid; gap: 8px; padding: var(--space-sm); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }
  .radial { position: relative; aspect-ratio: 1; border-radius: 50%; border: 1px solid rgba(255,255,255,0.08); background: radial-gradient(circle, rgba(255,255,255,0.04), transparent 70%); }
  .pip { position: absolute; transform: translate(-50%, -50%); width: 14px; height: 14px; border-radius: 50%; min-height: 0; padding: 0; }
  .pip.green { background: #00ff88; }
  .pip.yellow { background: #ffd84d; }
  .pip.orange { background: #ff9d47; }
  .pip.red { background: #ff4444; }
  .caption { font-size: var(--font-size-xs); color: var(--text-secondary); }
</style>
