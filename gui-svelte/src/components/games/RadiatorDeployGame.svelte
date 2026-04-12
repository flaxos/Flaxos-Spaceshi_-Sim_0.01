<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getEngineeringShip, getEngineeringState, getThermalState, toNumber, toStringValue } from "../engineering/engineeringData.js";

  const PANELS = ["PORT-1", "PORT-2", "DORSAL", "VENTRAL", "STBD-1", "STBD-2"];

  let pending = false;

  $: ship = getEngineeringShip($gameState);
  $: engineering = getEngineeringState(ship);
  $: thermal = getThermalState(ship);
  $: deployed = Boolean(engineering.radiators_deployed);
  $: priority = toStringValue(engineering.radiator_priority, "balanced");
  $: thermalLoad = Math.max(0, Math.min(100, toNumber(thermal.temperature_percent)));
  $: coolingScore = deployed ? Math.min(100, 45 + thermalLoad * 0.55) : Math.max(10, thermalLoad * 0.2);
  $: radarSignature = deployed ? 78 : 28;

  async function togglePanels() {
    pending = true;
    try {
      await wsClient.sendShipCommand("manage_radiators", { deployed: !deployed });
    } finally {
      pending = false;
    }
  }

  async function setPriority(value: string) {
    pending = true;
    try {
      await wsClient.sendShipCommand("manage_radiators", { priority: value });
    } finally {
      pending = false;
    }
  }
</script>

<Panel title="Radiator Deploy" domain="power" priority="primary" className="radiator-deploy-game">
  <div class="shell">
    <div class="panel-grid">
      {#each PANELS as panel}
        <button type="button" class:active={deployed} disabled={pending} on:click={togglePanels}>
          <span>{panel}</span>
          <strong>{deployed ? "DEPLOYED" : "STOWED"}</strong>
        </button>
      {/each}
    </div>

    <div class="priority-row">
      {#each ["balanced", "cooling", "stealth"] as mode}
        <button class:selected={priority === mode} type="button" on:click={() => setPriority(mode)}>
          {mode.toUpperCase()}
        </button>
      {/each}
    </div>

    <div class="tradeoff-card">
      <div class="metric">
        <span>Cooling</span>
        <div class="track"><div class="fill cooling" style={`width:${coolingScore.toFixed(0)}%;`}></div></div>
      </div>
      <div class="metric">
        <span>Radar Signature</span>
        <div class="track"><div class="fill signature" style={`width:${radarSignature.toFixed(0)}%;`}></div></div>
      </div>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .panel-grid,
  .priority-row {
    display: grid;
    gap: var(--space-xs);
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .panel-grid button,
  .priority-row button {
    display: grid;
    gap: 4px;
    padding: 10px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.68rem;
  }

  .panel-grid button.active,
  .priority-row button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .panel-grid span,
  .metric span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .tradeoff-card {
    display: grid;
    gap: var(--space-sm);
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .metric {
    display: grid;
    gap: 6px;
  }

  .track {
    height: 10px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
  }

  .fill.cooling {
    background: rgba(0, 255, 136, 0.8);
  }

  .fill.signature {
    background: rgba(255, 122, 71, 0.88);
  }
</style>
