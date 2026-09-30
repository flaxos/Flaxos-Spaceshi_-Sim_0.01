<script lang="ts">
  import "./styles/app.css";
  import "./styles/tiers.css";
  import "./styles/damage.css";
  import "./styles/mobile.css";

  import { onMount } from "svelte";
  import { initializeConnection } from "./lib/stores/playerShip.js";
  import { crewSession, initializeCrewSession, refreshCrewSession } from "./lib/stores/crewSession.js";
  import { commandFeedback } from "./lib/stores/commandFeedback.js";

  import BridgeHeader from "./components/layout/BridgeHeader.svelte";
  import StatusBar from "./components/layout/StatusBar.svelte";

  import HelmView from "./views/HelmView.svelte";
  import TacticalView from "./views/TacticalView.svelte";
  import EngineeringView from "./views/EngineeringView.svelte";
  import OpsView from "./views/OpsView.svelte";
  import ScienceView from "./views/ScienceView.svelte";
  import CommsView from "./views/CommsView.svelte";
  import FleetView from "./views/FleetView.svelte";
  import MissionView from "./views/MissionView.svelte";
  import EditorView from "./views/EditorView.svelte";

  // Station → allowed views mapping (mirrors index.html logic)
  const STATION_VIEWS: Record<string, string[]> = {
    captain:         ["mission", "helm", "tactical", "engineering", "ops", "science", "comms", "fleet"],
    helm:            ["mission", "helm", "tactical"],
    tactical:        ["mission", "tactical", "helm"],
    ops:             ["mission", "ops", "engineering"],
    engineering:     ["mission", "engineering", "ops"],
    comms:           ["mission", "comms"],
    science:         ["mission", "science", "tactical"],
    fleet_commander: ["mission", "fleet", "tactical"],
  };

  let activeView = "mission";
  let allowedViews: string[] = ["mission"];
  let previousStation: string | null = null;

  $: allowedViews = $crewSession.station ? (STATION_VIEWS[$crewSession.station] ?? ["mission"]) : ["mission"];
  $: if (!allowedViews.includes(activeView)) activeView = "mission";
  $: if ($crewSession.station !== previousStation) {
    previousStation = $crewSession.station;
    activeView = previousStation ? (allowedViews.find(view => view !== "mission") ?? "mission") : "mission";
  }

  function onViewChange(e: CustomEvent<{ view: string }>) {
    activeView = e.detail.view;
  }

  function onStationClaimed(e: CustomEvent<{ station: string }>) {
    // Authority is shared with the lobby/header through crewSession.
    if (e.detail.station !== $crewSession.station) void refreshCrewSession();
  }

  function onStationReleased() {
    activeView = "mission";
  }

  // Listen for scenario-loaded to switch to the first active bridge view
  async function onScenarioLoaded() {
    await refreshCrewSession();
    if ($crewSession.station) activeView = allowedViews.find(view => view !== "mission") ?? "mission";
  }

  function onRejoinRequested() { activeView = "mission"; }

  onMount(() => {
    initializeCrewSession();
    initializeConnection();
    document.addEventListener("scenario-loaded", onScenarioLoaded);
    document.addEventListener("crew-rejoin-request", onRejoinRequested);
    return () => {
      document.removeEventListener("scenario-loaded", onScenarioLoaded);
      document.removeEventListener("crew-rejoin-request", onRejoinRequested);
    };
  });
</script>

<div id="app-shell">
  <!-- ── Top chrome ── -->
  <BridgeHeader
    bind:activeView
    {allowedViews}
    on:station-claimed={onStationClaimed}
    on:station-released={onStationReleased}
    on:view-change={onViewChange}
  />
  <StatusBar />

  {#if $crewSession.needsRejoin}
    <div class="crew-notice" role="status">
      {$crewSession.connected ? "Connection restored. Rejoin your ship and station to continue." : "Connection lost. Ship controls are unavailable."}
      <button disabled={!$crewSession.connected || !$crewSession.registered} on:click={() => document.dispatchEvent(new CustomEvent("crew-rejoin-request"))}>Rejoin crew</button>
    </div>
  {/if}
  {#if $commandFeedback}
    <div class="command-error" role="alert">
      <span>{$commandFeedback.command}: {$commandFeedback.message}</span>
      <button aria-label="Dismiss command error" on:click={() => commandFeedback.set(null)}>×</button>
    </div>
  {/if}

  <!-- ── View stack ── -->
  <div class="view-stack">
    <div class="view-container" class:active={activeView === "helm"}>
      <HelmView />
    </div>
    <div class="view-container" class:active={activeView === "tactical"}>
      <TacticalView />
    </div>
    <div class="view-container" class:active={activeView === "engineering"}>
      <EngineeringView />
    </div>
    <div class="view-container" class:active={activeView === "ops"}>
      <OpsView />
    </div>
    <div class="view-container" class:active={activeView === "science"}>
      <ScienceView />
    </div>
    <div class="view-container" class:active={activeView === "comms"}>
      <CommsView />
    </div>
    <div class="view-container" class:active={activeView === "fleet"}>
      <FleetView />
    </div>
    <div class="view-container" class:active={activeView === "mission"}>
      <MissionView />
    </div>
    <div class="view-container" class:active={activeView === "editor"}>
      <EditorView />
    </div>
  </div>
</div>

<style>
  .crew-notice, .command-error {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 12px;
    color: var(--text-primary);
    background: var(--bg-raised);
    border-bottom: 1px solid var(--bd-default);
    flex-shrink: 0;
  }

  .command-error { color: var(--crit, #ff5555); }

  :global(html), :global(body) {
    height: 100%;
    overflow: hidden;
  }

  #app-shell {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  /* Status bar */
  :global(.status-bar) {
    flex: 0 0 36px;
  }

  .view-stack {
    flex: 1 1 0;
    min-height: 0;
    overflow: hidden;
    position: relative;
  }

  .view-container {
    position: absolute;
    inset: 0;
    display: none;
    overflow: hidden;
  }

  .view-container.active {
    display: block;
    overflow: auto;
    overscroll-behavior: contain;
  }
</style>
