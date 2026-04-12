<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { extractShipState, getECCMState, toStringValue } from "./tacticalData.js";

  const commands = [
    { label: "OFF", command: "eccm_off", active: (mode: string, multispectral: boolean) => mode === "off" && !multispectral },
    { label: "FREQ HOP", command: "eccm_frequency_hop", active: (mode: string) => mode === "frequency_hop" },
    { label: "BURN THROUGH", command: "eccm_burn_through", active: (mode: string) => mode === "burn_through" },
    { label: "MULTISPECTRAL", command: "eccm_multispectral", active: (_mode: string, multispectral: boolean) => multispectral },
  ];

  $: ship = extractShipState($gameState);
  $: eccm = getECCMState(ship);
  $: mode = toStringValue(eccm.mode, "off");
  $: multispectral = Boolean(eccm.multispectral_active);

  async function send(command: string) {
    await wsClient.sendShipCommand(command, {});
  }
</script>

<Panel title="ECCM Control" domain="sensor" priority={mode !== "off" || multispectral ? "primary" : "secondary"} className="eccm-control-panel">
  <div class="shell">
    <div class="mode-grid">
      {#each commands as item}
        <button class:selected={item.active(mode, multispectral)} type="button" on:click={() => send(item.command)}>{item.label}</button>
      {/each}
    </div>

    <div class="status-row">
      <span>Status</span>
      <strong>{eccm.status ?? "standby"}</strong>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .mode-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .mode-grid button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .status-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
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
