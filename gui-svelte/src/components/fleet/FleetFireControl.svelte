<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getTacticalContacts } from "../tactical/tacticalData.js";
  import { getFleetShip } from "./fleetData.js";

  let selectedTarget = "";
  let fireMode: "salvo" | "sustained" | "cease" = "salvo";
  let feedback = "";

  $: ship = getFleetShip($gameState);
  $: contacts = getTacticalContacts(ship);
  $: if (!selectedTarget && contacts.length) selectedTarget = contacts[0].id;

  async function designate() {
    if (!selectedTarget) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("fleet_target", { contact: selectedTarget });
      feedback = `Fleet target set to ${selectedTarget}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Target designation failed";
    }
  }

  async function fire() {
    feedback = "";
    try {
      if (fireMode === "cease") {
        await wsClient.sendShipCommand("fleet_cease_fire", {});
        feedback = "Fleet cease-fire issued";
      } else {
        await wsClient.sendShipCommand("fleet_fire", { volley: fireMode === "salvo" });
        feedback = fireMode === "salvo" ? "Fleet salvo launched" : "Fleet sustained fire ordered";
      }
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Fire control command failed";
    }
  }
</script>

<Panel title="Fleet Fire Control" domain="weapons" priority="secondary" className="fleet-fire-control-panel">
  <div class="shell">
    <label class="field">
      <span>Target</span>
      <select bind:value={selectedTarget}>
        <option value="">Select contact</option>
        {#each contacts as contact}
          <option value={contact.id}>{contact.id} · {contact.classification}</option>
        {/each}
      </select>
    </label>

    <div class="button-row">
      <button type="button" disabled={!selectedTarget} on:click={designate}>DESIGNATE</button>
    </div>

    <label class="field">
      <span>Fire Mode</span>
      <select bind:value={fireMode}>
        <option value="salvo">SALVO</option>
        <option value="sustained">SUSTAINED</option>
        <option value="cease">CEASE</option>
      </select>
    </label>

    <button class:danger={fireMode !== "cease"} type="button" on:click={fire}>
      {fireMode === "cease" ? "CEASE FIRE" : "EXECUTE FIRE ORDER"}
    </button>

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

  .field,
  .feedback {
    display: grid;
    gap: 6px;
  }

  .field span,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  select,
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

  button.danger {
    border-color: rgba(255, 68, 68, 0.35);
    background: rgba(255, 68, 68, 0.12);
  }

  .feedback {
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
    color: var(--status-info);
  }
</style>
