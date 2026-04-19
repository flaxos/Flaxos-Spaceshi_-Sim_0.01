<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedLauncherType, selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    asRecord,
    extractShipState,
    getCombatState,
    getLockedTargetId,
    getTacticalContacts,
    toStringValue,
  } from "./tacticalData.js";
  import {
    getMunitionProfileOptions,
    GUIDANCE_OPTIONS,
    launchSalvo,
    programMunition,
    WARHEAD_OPTIONS,
  } from "./tacticalActions.js";

  export let embedded = false;

  const salvoOptions = [1, 2, 4];

  let salvoSize = 1;
  let profile = "direct";
  let guidanceMode = "guided";
  let warheadType = "fragmentation";
  let selectedTarget = "";

  $: ship = extractShipState($gameState);
  $: combat = getCombatState(ship);
  $: contacts = getTacticalContacts(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: selectedTarget = $selectedTacticalTargetId || lockedTargetId;
  $: profileOptions = getMunitionProfileOptions($selectedLauncherType);
  $: if (!profileOptions.includes(profile)) {
    profile = profileOptions[0] ?? "direct";
  }
  $: armedProgram = asRecord(combat.munition_program) ?? {};
  $: armedProgramType = toStringValue(armedProgram.munition_type);
  $: hasProgram = Object.keys(armedProgram).length > 0;
  $: programMatchesSelection = !armedProgramType || armedProgramType === $selectedLauncherType;

  async function fire() {
    await launchSalvo({
      munitionType: $selectedLauncherType,
      targetId: selectedTarget || undefined,
      count: salvoSize,
      profile,
      guidanceMode,
      warheadType,
    });
  }

  async function program() {
    await programMunition({
      munitionType: $selectedLauncherType,
      flightProfile: profile,
      guidanceMode,
      warheadType,
    });
  }

  function onTargetChange(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    selectedTarget = value;
    selectedTacticalTargetId.set(value);
  }

  function summaryValue(key: string, fallback = "DEFAULT") {
    return toStringValue(armedProgram[key], fallback).replaceAll("_", " ").toUpperCase();
  }
</script>

{#if embedded}
  <div class="shell embedded-shell">
    {#if hasProgram}
      <div class="armed-program" class:mismatch={!programMatchesSelection}>
        <div class="armed-header">
          <span class="eyebrow">Armed Program</span>
          <strong>{armedProgramType.toUpperCase()}</strong>
        </div>
        <div class="armed-grid">
          <div><span>Profile</span><strong>{summaryValue("flight_profile")}</strong></div>
          <div><span>Guidance</span><strong>{summaryValue("guidance_mode")}</strong></div>
          <div><span>Warhead</span><strong>{summaryValue("warhead_type")}</strong></div>
          <div><span>Datalink</span><strong>{armedProgram.datalink === false ? "OFF" : "ON"}</strong></div>
        </div>
        {#if !programMatchesSelection}
          <p class="mismatch-note">
            Next {$selectedLauncherType.toUpperCase()} launch will ignore the armed {armedProgramType.toUpperCase()} program.
          </p>
        {/if}
      </div>
    {/if}

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
          {#each profileOptions as option}
            <option value={option}>{option}</option>
          {/each}
        </select>
      </label>
    </div>

    <div class="option-grid">
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
    </div>

    <div class="actions">
      <button on:click={program}>ARM PROGRAM</button>
      <button class="fire-action" on:click={fire}>QUEUE SALVO</button>
    </div>
  </div>
{:else}
  <Panel title="Launcher Control" domain="weapons" priority="secondary" className="launcher-control-panel">
    <div class="shell">
      {#if hasProgram}
        <div class="armed-program" class:mismatch={!programMatchesSelection}>
          <div class="armed-header">
            <span class="eyebrow">Armed Program</span>
            <strong>{armedProgramType.toUpperCase()}</strong>
          </div>
          <div class="armed-grid">
            <div><span>Profile</span><strong>{summaryValue("flight_profile")}</strong></div>
            <div><span>Guidance</span><strong>{summaryValue("guidance_mode")}</strong></div>
            <div><span>Warhead</span><strong>{summaryValue("warhead_type")}</strong></div>
            <div><span>Datalink</span><strong>{armedProgram.datalink === false ? "OFF" : "ON"}</strong></div>
          </div>
          {#if !programMatchesSelection}
            <p class="mismatch-note">
              Next {$selectedLauncherType.toUpperCase()} launch will ignore the armed {armedProgramType.toUpperCase()} program.
            </p>
          {/if}
        </div>
      {/if}

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
            {#each profileOptions as option}
              <option value={option}>{option}</option>
            {/each}
          </select>
        </label>
      </div>

      <div class="option-grid">
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
      </div>

      <div class="actions">
        <button on:click={program}>ARM PROGRAM</button>
        <button class="fire-action" on:click={fire}>QUEUE SALVO</button>
      </div>
    </div>
  </Panel>
{/if}

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .embedded-shell {
    padding: 0;
  }

  .armed-program {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid rgba(var(--tier-accent-rgb), 0.3);
    background: rgba(var(--tier-accent-rgb), 0.08);
  }

  .armed-program.mismatch {
    border-color: rgba(239, 160, 32, 0.35);
    background: rgba(239, 160, 32, 0.08);
  }

  .armed-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .armed-header strong,
  .armed-grid strong {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    letter-spacing: 0.06em;
  }

  .armed-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 12px;
  }

  .armed-grid div {
    display: grid;
    gap: 4px;
  }

  .eyebrow,
  .armed-grid span,
  .mismatch-note,
  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .mismatch-note {
    margin: 0;
    line-height: 1.4;
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

  .fire-action {
    border-color: rgba(232, 48, 48, 0.4);
    background: rgba(192, 48, 48, 0.18);
    color: var(--crit);
  }

  @media (max-width: 720px) {
    .option-grid,
    .option-grid:last-of-type,
    .toggle-row,
    .actions,
    .armed-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
