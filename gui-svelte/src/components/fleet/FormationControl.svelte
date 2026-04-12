<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";

  const FORMATIONS = [
    { label: "LINE", command: "line" },
    { label: "WEDGE", command: "wedge" },
    { label: "DIAMOND", command: "diamond" },
    { label: "COLUMN", command: "column" },
    { label: "SPREAD", command: "wall" },
    { label: "ESCORT", command: "diamond" },
    { label: "SPHERE", command: "sphere" },
  ];

  let selectedFormation = FORMATIONS[0];
  let spacing = 2000;
  let echelonAngle = 30;
  let manualOffset = { x: 0, y: 0, z: 0 };
  let feedback = "";

  $: rawTier = $tier === "raw";

  async function applyFormation() {
    feedback = "";
    try {
      await wsClient.sendShipCommand("fleet_form", {
        formation: selectedFormation.command,
        spacing,
        echelon_angle: echelonAngle,
        offset: rawTier ? manualOffset : undefined,
      });
      feedback = `${selectedFormation.label} ordered`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Formation command failed";
    }
  }

  async function breakFormation() {
    feedback = "";
    try {
      await wsClient.sendShipCommand("fleet_break_formation", {});
      feedback = "Formation broken";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Break command failed";
    }
  }
</script>

<Panel title="Formation Control" domain="weapons" priority="secondary" className="formation-control-panel">
  <div class="shell">
    <div class="preset-grid">
      {#each FORMATIONS as formation}
        <button class:active={selectedFormation.label === formation.label} type="button" on:click={() => selectedFormation = formation}>
          {formation.label}
        </button>
      {/each}
    </div>

    <label class="field">
      <span>Echelon Angle</span>
      <input type="range" min="0" max="60" step="1" bind:value={echelonAngle} />
      <strong>{Math.round(echelonAngle)}°</strong>
    </label>

    {#if rawTier}
      <div class="offset-grid">
        <label class="field"><span>Offset X</span><input type="number" bind:value={manualOffset.x} /></label>
        <label class="field"><span>Offset Y</span><input type="number" bind:value={manualOffset.y} /></label>
        <label class="field"><span>Offset Z</span><input type="number" bind:value={manualOffset.z} /></label>
      </div>
    {/if}

    <div class="button-row">
      <button type="button" on:click={applyFormation}>FORM FLEET</button>
      <button class="secondary" type="button" on:click={breakFormation}>BREAK</button>
    </div>

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

  .preset-grid,
  .offset-grid {
    display: grid;
    gap: 8px;
  }

  .preset-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .offset-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .field {
    display: grid;
    gap: 6px;
  }

  .button-row {
    display: flex;
    gap: var(--space-sm);
  }

  .field span,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  strong,
  input,
  button {
    font-family: var(--font-mono);
  }

  strong {
    color: var(--text-primary);
  }

  input,
  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-size: 0.72rem;
  }

  button.active {
    border-color: rgba(var(--tier-accent-rgb), 0.45);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .button-row button {
    flex: 1;
  }

  .feedback {
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
    color: var(--status-info);
  }

  @media (max-width: 640px) {
    .preset-grid,
    .offset-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
