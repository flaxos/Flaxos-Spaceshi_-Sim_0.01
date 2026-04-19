<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { selectedLauncherType } from "../../lib/stores/tacticalUi.js";
  import {
    getMunitionProfileOptions,
    GUIDANCE_OPTIONS,
    programMunition,
    WARHEAD_OPTIONS,
  } from "../tactical/tacticalActions.js";

  export let embedded = false;

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

{#if embedded}
  <div class="shell embedded-shell">
    <div class="program-note">
      <span>Programming {$selectedLauncherType.toUpperCase()}</span>
      <strong>Next matching launch consumes this profile.</strong>
    </div>
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
      <label><span>PN Gain</span><input type="number" step="0.1" bind:value={pnGain} /></label>
      <label><span>Fuse Distance</span><input type="number" step="1" bind:value={fuseDistance} /></label>
      <label><span>Terminal Range</span><input type="number" step="100" bind:value={terminalRange} /></label>
      <label><span>Boost Duration</span><input type="number" step="0.5" bind:value={boostDuration} /></label>
    </div>
    <label class="toggle"><input type="checkbox" bind:checked={datalink} /> Datalink</label>
    <button on:click={program}>PROGRAM MUNITION</button>
  </div>
{:else}
  <Panel title="Munition Programming" domain="weapons" priority="secondary" className="munition-programming-panel">
    <div class="shell">
      <div class="program-note">
        <span>Programming {$selectedLauncherType.toUpperCase()}</span>
        <strong>Next matching launch consumes this profile.</strong>
      </div>
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
        <label><span>PN Gain</span><input type="number" step="0.1" bind:value={pnGain} /></label>
        <label><span>Fuse Distance</span><input type="number" step="1" bind:value={fuseDistance} /></label>
        <label><span>Terminal Range</span><input type="number" step="100" bind:value={terminalRange} /></label>
        <label><span>Boost Duration</span><input type="number" step="0.5" bind:value={boostDuration} /></label>
      </div>
      <label class="toggle"><input type="checkbox" bind:checked={datalink} /> Datalink</label>
      <button on:click={program}>PROGRAM MUNITION</button>
    </div>
  </Panel>
{/if}

<style>
  .shell,
  .grid,
  label,
  .program-note {
    display: grid;
    gap: var(--space-sm);
  }

  .shell {
    padding: var(--space-sm);
  }

  .embedded-shell {
    padding: 0;
  }

  .program-note {
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid rgba(var(--tier-accent-rgb), 0.28);
    background: rgba(var(--tier-accent-rgb), 0.06);
  }

  .program-note strong {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
  }

  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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
  }

  @media (max-width: 720px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
