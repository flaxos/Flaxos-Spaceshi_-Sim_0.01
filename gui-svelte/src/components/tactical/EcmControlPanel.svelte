<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { extractShipState, getECMState, toNumber } from "./tacticalData.js";

  let emconLevel = "0";

  $: ship = extractShipState($gameState);
  $: ecm = getECMState(ship);
  $: emconEnabled = Boolean(ecm.emcon_active);
  $: emconLevel = emconEnabled ? "5" : "0";

  async function toggleJammer() {
    await wsClient.sendShipCommand(ecm.jammer_enabled ? "deactivate_jammer" : "activate_jammer", {});
  }

  async function deployChaff() {
    await wsClient.sendShipCommand("deploy_chaff", {});
  }

  async function setEmcon(event: Event) {
    emconLevel = (event.currentTarget as HTMLSelectElement).value;
    await wsClient.sendShipCommand("set_emcon", { enabled: emconLevel !== "0" });
  }
</script>

<Panel title="ECM Control" domain="sensor" priority={ecm.jammer_enabled || emconEnabled ? "primary" : "secondary"} className="ecm-control-panel">
  <div class="shell">
    <div class="status-grid">
      <div class="card"><span>Jammer</span><strong>{ecm.jammer_enabled ? "ACTIVE" : "OFF"}</strong></div>
      <div class="card"><span>Chaff</span><strong>{ecm.chaff_count ?? 0}</strong></div>
      <div class="card"><span>EMCON</span><strong>{emconEnabled ? "ON" : "OFF"}</strong></div>
      <div class="card"><span>Power</span><strong>{toNumber(ecm.jammer_power) / 1000} kW</strong></div>
    </div>

    <div class="actions">
      <button on:click={toggleJammer}>{ecm.jammer_enabled ? "DEACTIVATE JAMMER" : "ACTIVATE JAMMER"}</button>
      <button on:click={deployChaff}>DEPLOY CHAFF</button>
    </div>

    <label>
      <span>EMCON level</span>
      <select value={emconLevel} on:change={setEmcon}>
        {#each [0, 1, 2, 3, 4, 5] as level}
          <option value={String(level)}>{level}</option>
        {/each}
      </select>
    </label>
  </div>
</Panel>

<style>
  .shell,
  label {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .status-grid,
  .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .card {
    display: grid;
    gap: 4px;
    padding: 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
  }

  span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  strong {
    font-family: var(--font-mono);
  }
</style>
