<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import {
    formatThermalStatus,
    getEngineeringShip,
    getEngineeringState,
    getThermalBars,
    getThermalState,
    toNumber,
    toStringValue,
  } from "./engineeringData.js";

  $: ship = getEngineeringShip($gameState);
  $: thermal = getThermalState(ship);
  $: engineering = getEngineeringState(ship);
  $: bars = getThermalBars(ship);
  $: hullTemperature = toNumber(thermal.hull_temperature);
  $: maxTemperature = toNumber(thermal.max_temperature, 1);
  $: warningTemperature = toNumber(thermal.warning_temperature);
  $: netHeat = toNumber(thermal.net_heat_rate);
  $: radiatorFactor = toNumber(thermal.radiator_factor, 1);
  $: radiatorPriority = toStringValue(engineering.radiator_priority, "balanced").toUpperCase();
  $: radiatorsDeployed = Boolean(engineering.radiators_deployed ?? (radiatorFactor > 1.05));
  $: arcadeTier = $tier === "arcade";

  function temperatureValue(id: string, current: number): string {
    if (id === "radiators") return `${current.toFixed(1)} area`;
    if (!Number.isFinite(current)) return "--";
    return `${current.toFixed(current >= 1000 ? 0 : 1)} K`;
  }
</script>

<Panel title="Thermal Display" domain="power" priority={$tier === "manual" || $tier === "raw" ? "primary" : "secondary"} className="thermal-display-panel">
  <div class="stack">
    <section class="summary">
      <div>
        <span class="label">Hull Temp</span>
        <strong>{hullTemperature.toFixed(1)} K</strong>
      </div>
      <div>
        <span class="label">Thermal State</span>
        <strong class:warn={hullTemperature >= warningTemperature} class:critical={hullTemperature >= maxTemperature * 0.9}>{formatThermalStatus(thermal)}</strong>
      </div>
      <div>
        <span class="label">Net Heat</span>
        <strong class:cool={netHeat <= 0}>{netHeat >= 0 ? "+" : ""}{netHeat.toFixed(1)} kW</strong>
      </div>
    </section>

    <section class="radiator-card">
      <div class="radiator-head">
        <div>
          <div class="label">Radiators</div>
          <strong>{radiatorsDeployed ? "DEPLOYED" : "RETRACTED"}</strong>
        </div>
        <div class="radiator-meta">
          <span>{radiatorPriority}</span>
          <span>x{radiatorFactor.toFixed(2)} cooling</span>
        </div>
      </div>
    </section>

    <section class="bar-list">
      {#each bars as bar}
        <div class="bar-card">
          <div class="bar-head">
            <span>{bar.label}</span>
            <strong class={bar.status}>{bar.percent.toFixed(0)}%</strong>
          </div>
          <div class="track">
            <div class="fill {bar.status}" style={`width:${bar.percent.toFixed(0)}%;`}></div>
          </div>
          {#if !arcadeTier}
            <div class="detail-row">
              <span>{temperatureValue(bar.id, bar.current)}</span>
              <span>{bar.status.toUpperCase()}</span>
            </div>
          {/if}
        </div>
      {/each}
    </section>
  </div>
</Panel>

<style>
  .stack {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .summary,
  .radiator-head,
  .bar-head,
  .detail-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .summary,
  .radiator-card,
  .bar-card {
    padding: 10px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent);
  }

  .summary {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .bar-list {
    display: grid;
    gap: var(--space-sm);
  }

  .label,
  .detail-row,
  .radiator-meta {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .warn {
    color: var(--status-warning);
  }

  .critical {
    color: var(--status-critical);
  }

  .cool {
    color: var(--status-nominal);
  }

  .track {
    height: 10px;
    border-radius: 999px;
    overflow: hidden;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    margin-top: 8px;
  }

  .fill {
    height: 100%;
  }

  .fill.green,
  strong.green {
    background: rgba(0, 255, 136, 0.85);
    color: var(--status-nominal);
  }

  .fill.yellow,
  strong.yellow {
    background: rgba(255, 210, 77, 0.88);
    color: #ffd24d;
  }

  .fill.orange,
  strong.orange {
    background: rgba(255, 151, 71, 0.9);
    color: #ff9747;
  }

  .fill.red,
  strong.red {
    background: rgba(255, 68, 68, 0.92);
    color: var(--status-critical);
  }

  @media (max-width: 720px) {
    .summary {
      grid-template-columns: 1fr;
    }
  }
</style>
