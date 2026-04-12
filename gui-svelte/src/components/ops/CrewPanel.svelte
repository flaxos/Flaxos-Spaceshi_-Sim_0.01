<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { asRecord, getCrewRows, getOpsShip, skillShort, toStringValue } from "./opsData.js";

  interface CrewCard {
    crewId: string;
    clientId: string;
    name: string;
    station: string;
    fatigue: number;
    stress: number;
    injury: string;
    skills: Record<string, number>;
  }

  let cards: CrewCard[] = [];
  let canManageOfficers = false;
  let feedback = "";
  let pollHandle: number | null = null;

  $: ship = getOpsShip($gameState);
  $: rosterFallback = getCrewRows(ship);

  onMount(() => {
    detectCaptain();
    void refresh();
    pollHandle = window.setInterval(() => {
      detectCaptain();
      void refresh();
    }, 5000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  function detectCaptain() {
    if (typeof document === "undefined") return;
    const badge = document.querySelector(".claimed-badge");
    canManageOfficers = (badge?.textContent ?? "").trim().toUpperCase() === "CAPTAIN";
  }

  async function refresh() {
    try {
      const response = await wsClient.sendShipCommand("crew_status", {});
      const record = asRecord(response);
      const source = Array.isArray(record?.crew) ? record.crew : [];
      const stationMap = new Map(rosterFallback.map((row) => [row.crewId, row.station]));
      cards = source
        .map((item) => asRecord(item))
        .filter((item): item is Record<string, unknown> => Boolean(item))
        .map((item) => ({
          crewId: toStringValue(item.crew_id),
          clientId: toStringValue(item.client_id),
          name: toStringValue(item.name, "Crew"),
          station: stationMap.get(toStringValue(item.crew_id)) ?? toStringValue(item.station_assignment, "UNASSIGNED"),
          fatigue: Number(item.fatigue ?? 0),
          stress: Number(item.stress ?? 0),
          injury: toStringValue(item.injury_state, "healthy"),
          skills: (asRecord(item.skills) as Record<string, number> | null) ?? {},
        }));
    } catch {
      cards = rosterFallback;
    }
  }

  function topSkills(skills: Record<string, number>): Array<[string, number]> {
    return Object.entries(skills)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }

  async function officerCommand(command: "promote_to_officer" | "demote_from_officer", card: CrewCard) {
    feedback = "";
    try {
      await wsClient.sendShipCommand(command, { target_client: card.clientId || card.crewId });
      feedback = `${command.replaceAll("_", " ")} sent`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Officer command failed";
    }
  }

  async function restCrew(card: CrewCard) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("crew_rest", { crew_id: card.crewId });
      feedback = `Rest ordered for ${card.name}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Rest order failed";
    }
  }
</script>

<Panel title="Crew Panel" domain="power" priority="secondary" className="crew-panel">
  <div class="shell">
    {#if cards.length === 0}
      <div class="empty">Crew data unavailable.</div>
    {:else}
      {#each cards as card}
        <div class="crew-card">
          <div class="head">
            <strong>{card.name}</strong>
            <span>{card.station.toUpperCase()}</span>
          </div>
          <div class="status-row">
            <span>Fatigue {Math.round(card.fatigue * 100)}%</span>
            <span>Stress {Math.round(card.stress * 100)}%</span>
            <span>{card.injury.toUpperCase()}</span>
          </div>
          <div class="skills">
            {#each topSkills(card.skills) as [skill, level]}
              <span>{skill.replaceAll("_", " ").toUpperCase()} {skillShort(level)}</span>
            {/each}
          </div>
          <div class="actions">
            <button type="button" on:click={() => restCrew(card)}>REST</button>
            {#if canManageOfficers}
              <button type="button" on:click={() => officerCommand("promote_to_officer", card)}>PROMOTE</button>
              <button type="button" on:click={() => officerCommand("demote_from_officer", card)}>DEMOTE</button>
            {/if}
          </div>
        </div>
      {/each}
    {/if}
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

  .crew-card,
  .empty,
  .feedback {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .status-row,
  .actions {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .skills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .head span,
  .status-row,
  .skills span,
  .empty,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .skills span {
    padding: 2px 6px;
    border-radius: 999px;
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
  }

  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  .feedback {
    color: var(--status-info);
  }
</style>
