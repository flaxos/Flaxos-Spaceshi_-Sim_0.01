<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { extractShipState, getTargetingSummary } from "./tacticalData.js";

  const options = [
    { label: "NONE", value: "none" },
    { label: "HULL", value: "hull" },
    { label: "DRIVE", value: "drive" },
    { label: "REACTOR", value: "reactor" },
    { label: "COMMS", value: "comms" },
    { label: "SENSORS", value: "sensors" },
    { label: "WEAPONS", value: "weapons" },
  ];

  let draft = "none";

  $: ship = extractShipState($gameState);
  $: targeting = getTargetingSummary(ship);
  $: draft = targeting.subsystem || "none";

  async function updateSubsystem(event: Event) {
    draft = (event.currentTarget as HTMLSelectElement).value;
    await wsClient.sendShipCommand("set_target_subsystem", { target_subsystem: draft });
  }
</script>

<Panel title="Subsystem Targeting" domain="weapons" priority="secondary" className="subsystem-selector-panel">
  <div class="shell">
    <label>
      <span>Target Subsystem</span>
      <select value={draft} on:change={updateSubsystem}>
        {#each options as option}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
    </label>
  </div>
</Panel>

<style>
  .shell {
    padding: var(--space-sm);
  }

  label {
    display: grid;
    gap: 6px;
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
</style>
