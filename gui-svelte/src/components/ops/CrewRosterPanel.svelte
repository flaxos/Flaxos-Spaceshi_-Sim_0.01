<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { getCrewRows, getOpsShip, skillLong } from "./opsData.js";

  let selectedCrewId = "";

  $: ship = getOpsShip($gameState);
  $: rows = getCrewRows(ship);
  $: selected = rows.find((row) => row.crewId === selectedCrewId) ?? null;

  function skillSummary(skills: Record<string, number>): string {
    return Object.entries(skills)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 2)
      .map(([skill, level]) => `${skill.replaceAll("_", " ")} ${skillLong(level)}`)
      .join(" · ");
  }
</script>

<Panel title="Crew Roster" domain="power" priority="secondary" className="crew-roster-panel">
  <div class="shell">
    <div class="table">
      {#if rows.length === 0}
        <div class="empty">No crew roster loaded.</div>
      {:else}
        {#each rows as row}
          <button type="button" class="row" on:click={() => selectedCrewId = row.crewId}>
            <span>{row.name}</span>
            <span>{row.station.toUpperCase()}</span>
            <span>{row.injury.toUpperCase()}</span>
            <span>{skillSummary(row.skills).toUpperCase()}</span>
          </button>
        {/each}
      {/if}
    </div>
  </div>

  {#if selected}
    <div class="modal-backdrop">
      <div class="modal">
        <div class="modal-head">
          <strong>{selected.name}</strong>
          <button type="button" on:click={() => selectedCrewId = ""}>CLOSE</button>
        </div>
        <div class="detail-grid">
          <div><span>Station</span><strong>{selected.station.toUpperCase()}</strong></div>
          <div><span>Injury</span><strong>{selected.injury.toUpperCase()}</strong></div>
          <div><span>Fatigue</span><strong>{Math.round(selected.fatigue * 100)}%</strong></div>
          <div><span>Stress</span><strong>{Math.round(selected.stress * 100)}%</strong></div>
        </div>
        <div class="skill-list">
          {#each Object.entries(selected.skills) as [skill, level]}
            <div class="skill-row">
              <span>{skill.replaceAll("_", " ").toUpperCase()}</span>
              <strong>{skillLong(level)}</strong>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</Panel>

<style>
  .shell {
    padding: var(--space-sm);
  }

  .table {
    display: grid;
    gap: 6px;
  }

  .row,
  .empty {
    display: grid;
    gap: 6px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
    text-align: left;
  }

  .row span,
  .empty,
  .detail-grid span,
  .skill-row span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .modal-backdrop {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    background: rgba(4, 5, 10, 0.76);
  }

  .modal {
    display: grid;
    gap: var(--space-sm);
    width: min(420px, calc(100% - 24px));
    padding: 14px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--bg-panel);
  }

  .modal-head,
  .skill-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .detail-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .skill-list {
    display: grid;
    gap: 6px;
  }
</style>
