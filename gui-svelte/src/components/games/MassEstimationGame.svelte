<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedScienceContactId } from "../../lib/stores/scienceUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    findScienceContact,
    formatWatts,
    getScienceContacts,
    getScienceShip,
    pseudoAcceleration,
    pseudoTargetMass,
  } from "../science/scienceData.js";

  let estimate = 80_000;
  let sentForTarget = "";

  $: ship = getScienceShip($gameState);
  $: contacts = getScienceContacts(ship);
  $: if (!$selectedScienceContactId && contacts.length) selectedScienceContactId.set(contacts[0].id);
  $: contact = findScienceContact(ship, $selectedScienceContactId);
  $: targetMass = pseudoTargetMass(contact);
  $: acceleration = pseudoAcceleration(contact);
  $: thrust = targetMass * acceleration;
  $: errorRatio = targetMass > 0 ? Math.abs(estimate - targetMass) / targetMass : 1;
  $: if (contact && errorRatio <= 0.08 && sentForTarget !== contact.id) {
    sentForTarget = contact.id;
    void wsClient.sendShipCommand("estimate_mass", { contact_id: contact.id });
  }
</script>

<Panel title="Mass Estimate" domain="sensor" priority="secondary" className="mass-estimation-game">
  <div class="shell">
    <div class="equation">F = m · a</div>
    <div class="meta">
      <span>Thrust {formatWatts(thrust)}</span>
      <span>Accel {acceleration.toFixed(1)} m/s²</span>
    </div>
    <input type="range" min="1000" max="500000" step="1000" bind:value={estimate} />
    <div class="readout">
      <strong>{Math.round(estimate).toLocaleString()} kg</strong>
      <span>{Math.round((1 - Math.min(errorRatio, 1)) * 100)}% fit</span>
    </div>
    <div class="track"><div class="fill" style={`width:${((1 - Math.min(errorRatio, 1)) * 100).toFixed(1)}%;`}></div></div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: 10px;
    padding: var(--space-sm);
  }

  .equation,
  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .equation {
    font-size: 1rem;
    text-align: center;
  }

  .meta,
  .readout {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .meta,
  .readout span {
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
    background: linear-gradient(90deg, rgba(255, 120, 80, 0.8), rgba(0, 255, 136, 0.8));
  }
</style>
