<script lang="ts">
  import "./styles/app.css";
  import "./styles/tiers.css";
  import "./styles/damage.css";
  import "./styles/mobile.css";

  import { onMount } from "svelte";
  import { initializeConnection } from "./lib/stores/playerShip.js";
  import { playerShipId } from "./lib/stores/playerShip.js";

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
  let allowedViews: string[] | null = null; // null = all (pre-station-claim)

  function onViewChange(e: CustomEvent<{ view: string }>) {
    activeView = e.detail.view;
  }

  function onStationClaimed(e: CustomEvent<{ station: string }>) {
    const station = e.detail.station;
    allowedViews = STATION_VIEWS[station] ?? ["mission"];
    // Auto-switch to first allowed view that isn't mission (if available)
    const preferred = allowedViews.find((v) => v !== "mission") ?? allowedViews[0];
    if (preferred && !allowedViews.includes(activeView)) {
      activeView = preferred;
    }
  }

  function onStationReleased() {
    allowedViews = null; // unlock all views
  }

  // Listen for scenario-loaded to switch to the first active bridge view
  function onScenarioLoaded(e: Event) {
    // Server returns player_ship_id / assigned_ship — check all possible keys
    type ScenarioDetail = Record<string, string | undefined>;
    const detail = (e as CustomEvent<ScenarioDetail>).detail ?? {};
    const shipId = detail.ship_id ?? detail.player_ship_id ?? detail.assigned_ship ?? detail.assignedShip;
    if (shipId) playerShipId.set(shipId);

    // If the server auto-assigned a station (e.g. captain), apply view restrictions
    const station = detail.station ?? detail.auto_station;
    if (station && STATION_VIEWS[station]) {
      allowedViews = STATION_VIEWS[station];
    }

    if (allowedViews?.includes("helm")) activeView = "helm";
    else if (allowedViews) activeView = allowedViews[0];
    else activeView = "helm";
  }

  onMount(() => {
    initializeConnection();
    document.addEventListener("scenario-loaded", onScenarioLoaded);
    return () => document.removeEventListener("scenario-loaded", onScenarioLoaded);
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
