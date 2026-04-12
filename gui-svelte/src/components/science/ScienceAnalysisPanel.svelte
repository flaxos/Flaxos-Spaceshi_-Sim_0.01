<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedScienceContactId } from "../../lib/stores/scienceUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    KNOWN_SHIP_CLASSES,
    asRecord,
    estimateMassFromContact,
    findScienceContact,
    formatDistance,
    formatSquareMeters,
    formatWatts,
    getScienceContacts,
    getScienceShip,
    inferredThrustProfile,
    recommendClassFromMass,
    spectralBandsForContact,
    toStringValue,
  } from "./scienceData.js";

  let analysisResult: Record<string, unknown> = {};
  let spectralResult: Record<string, unknown> = {};
  let feedback = "";
  let massEstimateInput = "";
  let selectedClass = "Unknown";
  let lastContactId = "";

  $: ship = getScienceShip($gameState);
  $: contacts = getScienceContacts(ship);
  $: if (!$selectedScienceContactId && contacts.length) selectedScienceContactId.set(contacts[0].id);
  $: contact = findScienceContact(ship, $selectedScienceContactId);
  $: if (contact && contact.id !== lastContactId) {
    lastContactId = contact.id;
    massEstimateInput = String(Math.round(estimateMassFromContact(contact)));
    selectedClass = recommendClassFromMass(estimateMassFromContact(contact));
    analysisResult = {};
    spectralResult = {};
  }
  $: bands = spectralBandsForContact(contact, asRecord(spectralResult));
  $: thrustProfile = inferredThrustProfile(contact, asRecord(spectralResult));
  $: analysisRecord = asRecord(analysisResult) ?? {};
  $: emissions = asRecord(analysisRecord.emissions) ?? {};
  $: contactData = asRecord(analysisRecord.contact_data) ?? {};

  async function analyze() {
    if (!contact) return;
    feedback = "";
    try {
      analysisResult = (await wsClient.sendShipCommand("analyze_contact", { contact_id: contact.id })) as Record<string, unknown>;
      feedback = `Deep analysis complete for ${contact.id}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Analysis failed";
    }
  }

  async function spectral() {
    if (!contact) return;
    feedback = "";
    try {
      spectralResult = (await wsClient.sendShipCommand("spectral_analysis", { contact_id: contact.id })) as Record<string, unknown>;
      feedback = `Spectral signature resolved for ${contact.id}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Spectral scan failed";
    }
  }

  async function classify() {
    if (!contact) return;
    await analyze();
    feedback = `${contact.id} classified as ${selectedClass.toUpperCase()} at ${massEstimateInput || "--"} kg`;
  }
</script>

<Panel title="Science Analysis" domain="sensor" priority="primary" className="science-analysis-panel">
  <div class="shell">
    <label class="field">
      <span>Contact</span>
      <select bind:value={$selectedScienceContactId}>
        <option value="">Select contact</option>
        {#each contacts as row}
          <option value={row.id}>{row.id} · {row.classification}</option>
        {/each}
      </select>
    </label>

    <section class="band-card">
      <div class="head">
        <span>Spectral Signature</span>
        <strong>{contact ? contact.id : "NO TRACK"}</strong>
      </div>
      <div class="bands">
        {#each bands as band}
          <div class="band-row">
            <span>{band.label}</span>
            <div class="track"><div class="fill" style={`width:${band.value.toFixed(1)}%;`}></div></div>
            <strong>{Math.round(band.value)}%</strong>
          </div>
        {/each}
      </div>
    </section>

    <section class="thrust-card">
      <div class="head">
        <span>Thrust Profile</span>
        <strong>{thrustProfile.label.toUpperCase()}</strong>
      </div>
      <div class="meta">
        <span>{thrustProfile.burnState.toUpperCase()}</span>
        <span>{thrustProfile.thrustKn.toFixed(1)} kN</span>
        <span>{contact ? formatDistance(contact.distance) : "--"}</span>
      </div>
    </section>

    <div class="button-row">
      <button type="button" disabled={!contact} on:click={analyze}>ANALYZE CONTACT</button>
      <button type="button" disabled={!contact} on:click={spectral}>RUN SPECTRAL</button>
    </div>

    <section class="classification-card">
      <div class="head">
        <span>Classification</span>
        <strong>{selectedClass.toUpperCase()}</strong>
      </div>
      <div class="grid">
        <label class="field">
          <span>Mass Estimate (kg)</span>
          <input bind:value={massEstimateInput} inputmode="numeric" />
        </label>
        <label class="field">
          <span>Ship Class</span>
          <select bind:value={selectedClass}>
            {#each KNOWN_SHIP_CLASSES as shipClass}
              <option value={shipClass}>{shipClass.toUpperCase()}</option>
            {/each}
          </select>
        </label>
      </div>
      <button type="button" disabled={!contact} on:click={classify}>CLASSIFY CONTACT</button>
    </section>

    <section class="readout-card">
      <div class="head">
        <span>Readout</span>
        <strong>{toStringValue(analysisRecord.classification, contact?.classification ?? "--").toUpperCase()}</strong>
      </div>
      <div class="readout-grid">
        <span>IR</span>
        <strong>{formatWatts(Number(emissions.ir_watts ?? contact?.irWatts ?? 0))}</strong>
        <span>RCS</span>
        <strong>{formatSquareMeters(Number(emissions.rcs_m2 ?? contact?.rcsSquareMeters ?? 0))}</strong>
        <span>Confidence</span>
        <strong>{Math.round(Number(contactData.confidence ?? contact?.confidence ?? 0) * 100)}%</strong>
        <span>Vector</span>
        <strong>{toStringValue(analysisRecord.detection_method, contact?.detectionMethod ?? "--").toUpperCase()}</strong>
      </div>
    </section>

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .band-card,
  .thrust-card,
  .classification-card,
  .readout-card,
  .feedback {
    display: grid;
    gap: 10px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .band-row,
  .button-row,
  .meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .field {
    display: grid;
    gap: 6px;
  }

  .field span,
  .meta,
  .feedback,
  .band-row span,
  .readout-grid span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .grid,
  .bands {
    display: grid;
    gap: 8px;
  }

  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  select,
  input,
  button {
    width: 100%;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  .track {
    flex: 1;
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.22), var(--tier-accent));
  }

  .readout-grid {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 6px 12px;
  }

  .feedback {
    color: var(--status-info);
  }

  @media (max-width: 640px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
