<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedLauncherType, selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import { extractShipState, getLockedTargetId, getTacticalContacts } from "./tacticalData.js";

  const profiles = ["direct", "evasive", "terminal_pop", "bracket"];
  const salvoOptions = [1, 2, 4];

  let salvoSize = 1;
  let profile = "direct";
  let guidanceMode = "guided";
  let warheadType = "fragmentation";
  let selectedTarget = "";

  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: selectedTarget = $selectedTacticalTargetId || lockedTargetId;

  async function fire() {
    await wsClient.sendShipCommand("launch_salvo", {
      munition_type: $selectedLauncherType,
      target: selectedTarget || undefined,
      count: salvoSize,
      profile,
      guidance_mode: guidanceMode,
      warhead_type: warheadType,
    });
  }

  async function program() {
    await wsClient.sendShipCommand("program_munition", {
      munition_type: $selectedLauncherType,
      flight_profile: profile,
      guidance_mode: guidanceMode,
      warhead_type: warheadType,
      salvo_size: salvoSize,
      target: selectedTarget || undefined,
    });
  }

  function onTargetChange(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    selectedTarget = value;
    selectedTacticalTargetId.set(value);
  }
</script>

<Panel title="Launcher Control" domain="weapons" priority="secondary" className="launcher-control-panel">
  <div class="shell">
    <div class="toggle-row">
      <button class:selected={$selectedLauncherType === "torpedo"} type="button" on:click={() => selectedLauncherType.set("torpedo")}>TORPEDO</button>
      <button class:selected={$selectedLauncherType === "missile"} type="button" on:click={() => selectedLauncherType.set("missile")}>MISSILE</button>
    </div>

    <div class="option-grid">
      <label>
        <span>Target</span>
        <select value={selectedTarget} on:change={onTargetChange}>
          <option value="">Locked target</option>
          {#each contacts as contact}
            <option value={contact.id}>{contact.id} · {contact.classification}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Salvo</span>
        <select bind:value={salvoSize}>
          {#each salvoOptions as option}
            <option value={option}>{option}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Profile</span>
        <select bind:value={profile}>
          {#each profiles as option}
            <option value={option}>{option}</option>
          {/each}
        </select>
      </label>
    </div>

    <div class="option-grid">
      <label><span>Guidance</span><input bind:value={guidanceMode} /></label>
      <label><span>Warhead</span><input bind:value={warheadType} /></label>
    </div>

    <div class="actions">
      <button on:click={program}>PROGRAM</button>
      <button on:click={fire}>FIRE</button>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .toggle-row,
  .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .toggle-row button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .option-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .option-grid:last-of-type {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  label {
    display: grid;
    gap: 6px;
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
</style>
