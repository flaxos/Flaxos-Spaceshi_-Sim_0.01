<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getEngineeringShip, getSystemToggleState } from "./engineeringData.js";

  let pendingSystem = "";
  let feedback = "";

  $: ship = getEngineeringShip($gameState);
  $: rows = getSystemToggleState(ship);
  $: cpuAssistTier = $tier === "cpu-assist";

  async function toggleSystem(systemId: string, enabled: boolean) {
    pendingSystem = systemId;
    feedback = "";
    try {
      await wsClient.sendShipCommand("toggle_system", {
        system: systemId,
        state: enabled ? 0 : 1,
      });
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Toggle failed";
    } finally {
      pendingSystem = "";
    }
  }
</script>

<Panel title="System Toggles" domain="power" priority="secondary" className="system-toggles-panel">
  <div class="shell">
    {#each rows as row}
      <div class="toggle-row">
        <div class="meta">
          <strong>{row.label}</strong>
          <span>{row.status.toUpperCase()}</span>
        </div>
        {#if cpuAssistTier}
          <div class:active={row.enabled} class="indicator">{row.enabled ? "ON" : "OFF"}</div>
        {:else}
          <button
            type="button"
            class:active={row.enabled}
            disabled={pendingSystem === row.id}
            on:click={() => toggleSystem(row.id, row.enabled)}
          >
            {row.enabled ? "POWER DOWN" : "POWER UP"}
          </button>
        {/if}
      </div>
    {/each}
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

  .toggle-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .meta {
    display: grid;
    gap: 4px;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .meta span,
  .indicator,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .indicator,
  button {
    min-width: 100px;
    text-align: center;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .indicator.active,
  button.active {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .feedback {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid rgba(255, 170, 0, 0.28);
    background: rgba(255, 170, 0, 0.08);
    color: var(--status-warning);
  }
</style>
