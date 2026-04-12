<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedLauncherType } from "../../lib/stores/tacticalUi.js";

  let guidanceMode = "guided";
  let warheadType = "fragmentation";
  let flightProfile = "direct";
  let pnGain = "3";
  let fuseDistance = "35";
  let terminalRange = "4000";
  let boostDuration = "6";
  let datalink = true;

  async function program() {
    await wsClient.sendShipCommand("program_munition", {
      munition_type: $selectedLauncherType,
      guidance_mode: guidanceMode,
      warhead_type: warheadType,
      flight_profile: flightProfile,
      pn_gain: Number(pnGain),
      fuse_distance: Number(fuseDistance),
      terminal_range: Number(terminalRange),
      boost_duration: Number(boostDuration),
      datalink,
    });
  }
</script>

<Panel title="Munition Programming" domain="weapons" priority="secondary" className="munition-programming-panel">
  <div class="shell">
    <div class="grid">
      <label><span>Guidance</span><input bind:value={guidanceMode} /></label>
      <label><span>Warhead</span><input bind:value={warheadType} /></label>
      <label><span>Profile</span><input bind:value={flightProfile} /></label>
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
