<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import {
    formatMass,
    formatPercent,
    formatSpeed,
    getArmorIntegrity,
    getArmorRows,
    getHullPercent,
    getOpsShip,
    getReadiness,
    readinessClass,
    toNumber,
  } from "./opsData.js";

  $: ship = getOpsShip($gameState);
  $: armorRows = getArmorRows(ship);
  $: hullPercent = getHullPercent(ship);
  $: armorPercent = getArmorIntegrity(ship);
  $: readiness = getReadiness(ship);
</script>

<Panel title="Ship Status" domain="power" priority="primary" className="ship-status-panel">
  <div class="stack">
    <section class="hero-card">
      <div class="hero-row">
        <div>
          <span class="label">Hull Integrity</span>
          <strong>{formatPercent(hullPercent)}</strong>
        </div>
        <div>
          <span class="label">Readiness</span>
          <strong class={readinessClass(readiness.score)}>{readiness.label.toUpperCase()}</strong>
        </div>
      </div>
      <div class="track">
        <div class="fill {readinessClass(hullPercent)}" style={`width:${hullPercent.toFixed(0)}%;`}></div>
      </div>
    </section>

    <section class="armor-grid">
      {#each armorRows as row}
        <div class="armor-card">
          <div class="armor-head">
            <span>{row.label}</span>
            <strong class:critical={row.integrityPercent < 35}>{formatPercent(row.integrityPercent)}</strong>
          </div>
          <div class="track compact">
            <div class="fill {readinessClass(row.integrityPercent)}" style={`width:${row.integrityPercent.toFixed(0)}%;`}></div>
          </div>
        </div>
      {/each}
    </section>

    <section class="metrics">
      <div><span>Armor Avg</span><strong>{formatPercent(armorPercent)}</strong></div>
      <div><span>Mass</span><strong>{formatMass(toNumber(ship.mass))}</strong></div>
      <div><span>Delta-V</span><strong>{formatSpeed(toNumber(ship.delta_v_remaining))}</strong></div>
      <div><span>Crew</span><strong>{toNumber(ship.crew_complement, 0).toFixed(0)}</strong></div>
    </section>
  </div>
</Panel>

<style>
  .stack {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .hero-card,
  .armor-card {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent);
  }

  .hero-row,
  .armor-head,
  .metrics {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .armor-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .metrics {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .label,
  .armor-head span,
  .metrics span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  strong.nominal {
    color: var(--status-nominal);
  }

  strong.warning {
    color: var(--status-warning);
  }

  strong.critical {
    color: var(--status-critical);
  }

  .track {
    height: 12px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .track.compact {
    height: 8px;
  }

  .fill {
    height: 100%;
  }

  .fill.nominal {
    background: rgba(0, 255, 136, 0.84);
  }

  .fill.warning {
    background: rgba(255, 170, 0, 0.88);
  }

  .fill.critical {
    background: rgba(255, 68, 68, 0.9);
  }
</style>
