<script lang="ts">
  import { selectedLauncherType } from "../../lib/stores/tacticalUi.js";

  let profile = "direct";
</script>

<div class="card">
  <div class="toggle">
    <button class:selected={$selectedLauncherType === "torpedo"} on:click={() => selectedLauncherType.set("torpedo")}>TORPEDO</button>
    <button class:selected={$selectedLauncherType === "missile"} on:click={() => selectedLauncherType.set("missile")}>MISSILE</button>
  </div>
  <label>
    <span>Flight profile</span>
    <select bind:value={profile}>
      <option value="direct">direct</option>
      <option value="evasive">evasive</option>
      <option value="terminal_pop">terminal_pop</option>
      <option value="bracket">bracket</option>
    </select>
  </label>
</div>

<style>
  .card, label { display: grid; gap: 10px; padding: var(--space-sm); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }
  .toggle { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .toggle button.selected { border-color: rgba(var(--tier-accent-rgb), 0.5); background: rgba(var(--tier-accent-rgb), 0.12); }
  span { font-size: var(--font-size-xs); color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
</style>
