<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { wsClient } from "../lib/ws/wsClient.js";
  import Panel from "../components/layout/Panel.svelte";
  import ScenarioLoader from "../components/mission/ScenarioLoader.svelte";
  import MissionObjectives from "../components/mission/MissionObjectives.svelte";
  import CampaignHub from "../components/mission/CampaignHub.svelte";
  import CommandPrompt from "../components/mission/CommandPrompt.svelte";
  import ServerAdminPanel from "../components/mission/ServerAdminPanel.svelte";

  // Game state: "lobby" | "playing" | "ended"
  type GamePhase = "lobby" | "playing" | "ended";
  let phase: GamePhase = "lobby";

  // Reference to ScenarioLoader so we can call showPostMission()
  let loaderRef: ScenarioLoader | undefined;

  // Which config panel is active
  let activePanel: "objectives" | "campaign" | "console" | "server" = "server";

  // ── Event wiring ─────────────────────────────────────────────────
  function onScenarioLoaded(e: Event) {
    const detail = (e as CustomEvent<Record<string, unknown>>).detail;
    // station claim or started flag → transition to playing
    if (detail?.station || detail?.started || detail?.assignedShip) {
      phase = "playing";
    } else if (detail?.ship_id || detail?.scenario) {
      // scenario loaded but not yet in lobby-to-playing transition — stay in lobby
      // (ScenarioLoader transitions to lobby screen internally)
    }
  }

  function onMissionEnd(e: Event) {
    const detail = (e as CustomEvent<{ status?: string }>).detail;
    if (detail?.status === "success" || detail?.status === "failure") {
      phase = "ended";
      loaderRef?.showPostMission();
    }
  }

  function onNextMission() {
    phase = "lobby";
    // ScenarioLoader will handle the state internally
  }

  let missionEndHandler: ((e: Event) => void) | null = null;
  let scenarioLoadedHandler: ((e: Event) => void) | null = null;
  let nextMissionHandler: ((e: Event) => void) | null = null;
  let missionPollGen = 0;

  async function pollForMissionEnd(gen: number) {
    if (gen !== missionPollGen || phase !== "playing") return;
    try {
      const resp = await wsClient.send("get_mission", {}) as { ok?: boolean; mission?: { mission_status?: string; status?: string } };
      if (gen !== missionPollGen) return;
      const status = resp?.mission?.mission_status ?? resp?.mission?.status;
      if (status === "success" || status === "failure") {
        phase = "ended";
        loaderRef?.showPostMission();
        return; // stop polling
      }
    } catch { /* skip */ }
    if (gen === missionPollGen) setTimeout(() => pollForMissionEnd(gen), 3000);
  }

  $: if (phase === "playing") {
    missionPollGen++;
    pollForMissionEnd(missionPollGen);
  } else {
    missionPollGen++; // cancel any running poll
  }

  onMount(() => {
    scenarioLoadedHandler = onScenarioLoaded;
    document.addEventListener("scenario-loaded", scenarioLoadedHandler);

    missionEndHandler = onMissionEnd;
    document.addEventListener("mission_complete", missionEndHandler);

    nextMissionHandler = () => onNextMission();
    document.addEventListener("next-mission", nextMissionHandler);
  });

  onDestroy(() => {
    missionPollGen++;
    if (scenarioLoadedHandler) document.removeEventListener("scenario-loaded", scenarioLoadedHandler);
    if (missionEndHandler) document.removeEventListener("mission_complete", missionEndHandler);
    if (nextMissionHandler) document.removeEventListener("next-mission", nextMissionHandler);
  });
</script>

<div class="mission-view">
  <div class="config-layout" class:mission-live={phase === "playing"}>
    <!-- Left: mission loader / scenario controls -->
    <div class="loader-sidebar">
      <Panel
        title={phase === "ended" ? "Mission Results" : "Mission Select"}
        domain="nav"
        priority={phase === "playing" ? "tertiary" : "primary"}
        collapsible={phase === "playing"}
      >
        <div class="loader-wrap" class:compact={phase === "playing"}>
          <ScenarioLoader
            bind:this={loaderRef}
            on:scenario-loaded={(e) => onScenarioLoaded(e)}
            on:next-mission={() => onNextMission()}
          />
        </div>
      </Panel>
    </div>

    <!-- Right: always-available config/admin panels -->
    <div class="mission-panels">
      <div class="panel-tabs" role="tablist">
        <button
          class="tab-btn"
          class:active={activePanel === "server"}
          role="tab"
          aria-selected={activePanel === "server"}
          on:click={() => activePanel = "server"}
        >SERVER</button>
        <button
          class="tab-btn"
          class:active={activePanel === "console"}
          role="tab"
          aria-selected={activePanel === "console"}
          on:click={() => activePanel = "console"}
        >CONSOLE</button>
        <button
          class="tab-btn"
          class:active={activePanel === "campaign"}
          role="tab"
          aria-selected={activePanel === "campaign"}
          on:click={() => activePanel = "campaign"}
        >CAMPAIGN</button>
        <button
          class="tab-btn"
          class:active={activePanel === "objectives"}
          role="tab"
          aria-selected={activePanel === "objectives"}
          on:click={() => activePanel = "objectives"}
        >OBJECTIVES</button>
      </div>

      <div class="panel-body">
        {#if activePanel === "objectives"}
          <Panel title="Mission Objectives" domain="nav" priority="primary" collapsible={false}>
            <MissionObjectives />
          </Panel>
        {:else if activePanel === "campaign"}
          <Panel title="Campaign" domain="comms" priority="secondary" collapsible={false}>
            <CampaignHub />
          </Panel>
        {:else if activePanel === "console"}
          <Panel title="Command Console" domain="" priority="tertiary" collapsible={false}>
            <CommandPrompt />
          </Panel>
        {:else if activePanel === "server"}
          <Panel title="Server Admin" domain="" priority="secondary" collapsible={false}>
            <ServerAdminPanel />
          </Panel>
        {/if}
      </div>
    </div>
  </div>
</div>

<style>
  .mission-view {
    width: 100%;
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .config-layout {
    display: grid;
    grid-template-columns: 340px 1fr;
    gap: var(--space-xs);
    height: 100%;
    padding: var(--space-xs);
    overflow: hidden;
  }

  .loader-sidebar {
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    min-height: 0;
  }

  .loader-wrap {
    height: 100%;
    overflow-y: auto;
  }

  .loader-wrap.compact {
    max-height: 300px;
    overflow-y: auto;
  }

  .mission-panels {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    overflow: hidden;
    min-height: 0;
  }

  /* ── Tabs ── */
  .panel-tabs {
    display: flex;
    gap: 2px;
    background: var(--bg-void);
    padding: 2px;
    border-radius: var(--radius-sm);
    flex-shrink: 0;
  }

  .tab-btn {
    flex: 1;
    padding: 5px 12px;
    background: transparent;
    border: none;
    border-radius: calc(var(--radius-sm) - 1px);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: all var(--transition-fast);
    text-transform: uppercase;
  }

  .tab-btn.active {
    background: var(--tier-accent, var(--hud-primary));
    color: #0a0a0f;
  }

  .tab-btn:hover:not(.active) {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  /* ── Panel body ── */
  .panel-body {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .panel-body :global(.panel) {
    flex: 1;
    min-height: 0;
  }

  .panel-body :global(.panel-body) {
    overflow-y: auto;
  }

  @media (max-width: 960px) {
    .config-layout {
      grid-template-columns: 1fr;
      grid-template-rows: minmax(220px, auto) 1fr;
      overflow: auto;
    }

    .loader-wrap.compact {
      max-height: none;
    }
  }

  @media (max-width: 680px) {
    .mission-view {
      overflow: auto;
    }

    .config-layout {
      padding: var(--space-2xs, 2px);
    }

    .panel-tabs {
      overflow-x: auto;
      overflow-y: hidden;
      scrollbar-width: none;
      -webkit-overflow-scrolling: touch;
    }

    .panel-tabs::-webkit-scrollbar {
      display: none;
    }

    .tab-btn {
      flex: 0 0 auto;
      min-width: max-content;
      padding: 7px 10px;
    }

    .panel-body :global(.panel-body) {
      overscroll-behavior: contain;
    }
  }
</style>
