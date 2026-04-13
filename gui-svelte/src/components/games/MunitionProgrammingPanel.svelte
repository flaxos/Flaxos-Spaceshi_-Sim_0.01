<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { selectedLauncherType } from "../../lib/stores/tacticalUi.js";
  import {
    getMunitionProfileOptions,
    GUIDANCE_OPTIONS,
    programMunition,
    WARHEAD_OPTIONS,
  } from "../tactical/tacticalActions.js";

  let guidanceMode = "guided";
  let warheadType = "fragmentation";
  let flightProfile = "direct";
  let pnGain = "3";
  let fuseDistance = "35";
  let terminalRange = "4000";
  let boostDuration = "6";
  let datalink = true;
  $: profileOptions = getMunitionProfileOptions($selectedLauncherType);
  $: if (!profileOptions.includes(flightProfile)) {
    flightProfile = profileOptions[0] ?? "direct";
  }

  async function program() {
    await programMunition({
      munitionType: $selectedLauncherType,
      guidanceMode,
      warheadType,
      flightProfile,
      pnGain: Number(pnGain),
      fuseDistance: Number(fuseDistance),
      terminalRange: Number(terminalRange),
      boostDuration: Number(boostDuration),
      datalink,
    });
  }
</script>

<Panel title="Munition Programming" domain="weapons" priority="secondary" className="munition-programming-panel">
  <div class="shell">
    <div class="grid">
      <label>
        <span>Guidance</span>
        <select bind:value={guidanceMode}>
          {#each GUIDANCE_OPTIONS as option}
            <option value={option}>{option}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Warhead</span>
        <select bind:value={warheadType}>
          {#each WARHEAD_OPTIONS as option}
            <option value={option}>{option}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Profile</span>
        <select bind:value={flightProfile}>
          {#each profileOptions as option}
            <option value={option}>{option}</option>
          {/each}
        </select>
      </label>
      <label><span>PN gain</span><input bind:value={pnGain} /></label>
      <label><span>Fuse distance</span><input bind:value={fuseDistance} /></label>
      <label><span>Terminal range</span><input bind:value={terminalRange} /></label>
      <label><span>Boost duration</span><input bind:value={boostDuration} /></label>
    </div>
    <label class="toggle"><input type="checkbox" bind:checked={datalink} /> Datalink</label>
    <button on:click={program}>PROGRAM MUNITION</button>
  </div>
</Panel>

<style>
  .shell,
  .grid,
  label {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 0;
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0;
  }
</style>
