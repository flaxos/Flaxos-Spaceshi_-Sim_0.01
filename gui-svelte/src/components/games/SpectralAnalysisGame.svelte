<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedScienceContactId } from "../../lib/stores/scienceUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    findScienceContact,
    getScienceContacts,
    getScienceShip,
    spectralBandsForContact,
  } from "../science/scienceData.js";

  let sliders = [50, 50, 50];
  let solvedTarget = "";

  $: ship = getScienceShip($gameState);
  $: contacts = getScienceContacts(ship);
  $: if (!$selectedScienceContactId && contacts.length) selectedScienceContactId.set(contacts[0].id);
  $: contact = findScienceContact(ship, $selectedScienceContactId);
  $: target = spectralBandsForContact(contact).slice(0, 3).map((band) => band.value);
  $: match = target.length
    ? Math.max(
        0,
        100 - (Math.abs(sliders[0] - target[0]) + Math.abs(sliders[1] - target[1]) + Math.abs(sliders[2] - target[2])) / 3,
      )
    : 0;
  $: if (contact && match >= 92 && solvedTarget !== contact.id) {
    solvedTarget = contact.id;
    void wsClient.sendShipCommand("analyze_contact", { contact_id: contact.id });
  }
</script>

<Panel title="Spectral Match" domain="sensor" priority="secondary" className="spectral-analysis-game">
  <div class="shell">
    <div class="head">
      <strong>{contact ? contact.id : "PRACTICE"}</strong>
      <span>{Math.round(match)}% match</span>
    </div>

    {#each ["IR", "EM", "RCS"] as label, index}
      <label class="row">
        <span>{label}</span>
        <input type="range" min="0" max="100" bind:value={sliders[index]} />
        <strong>{Math.round(sliders[index])}</strong>
      </label>
    {/each}

    <div class="track"><div class="fill" style={`width:${match.toFixed(1)}%;`}></div></div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: 10px;
    padding: var(--space-sm);
  }

  .head,
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .row input {
    flex: 1;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .track {
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(255, 165, 0, 0.8), rgba(0, 255, 136, 0.8));
  }
</style>
