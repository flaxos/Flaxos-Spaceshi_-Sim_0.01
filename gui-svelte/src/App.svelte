<script lang="ts">
  import "./styles/app.css";
  import "./styles/tiers.css";
  import "./styles/damage.css";
  import "./styles/mobile.css";

  import { onMount } from "svelte";
  import { initializeConnection } from "./lib/stores/playerShip.js";
  import { playerShipId } from "./lib/stores/playerShip.js";

  import StatusBar from "./components/layout/StatusBar.svelte";
  import TierSelector from "./components/layout/TierSelector.svelte";
  import StationSelector from "./components/layout/StationSelector.svelte";
  import ViewTabs from "./components/layout/ViewTabs.svelte";

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
    captain:         ["helm", "tactical", "fleet", "comms", "ops", "mission"],
    helm:            ["helm", "tactical", "mission"],
    tactical:        ["tactical", "helm", "mission"],
    ops:             ["ops", "engineering", "mission"],
    engineering:     ["engineering", "ops", "mission"],
    comms:           ["comms", "mission"],
    science:         ["science", "tactical", "mission"],
    fleet_commander: ["fleet", "tactical", "mission"],
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

  // Listen for scenario-loaded to switch to helm/mission view
  function onScenarioLoaded(e: Event) {
    const detail = (e as CustomEvent<{ ship_id?: string }>).detail;
    if (detail?.ship_id) playerShipId.set(detail.ship_id);
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
  <StatusBar />

  <div class="bridge-controls">
    <StationSelector
      on:station-claimed={onStationClaimed}
      on:station-released={onStationReleased}
    />
    <span class="controls-spacer"></span>
    <TierSelector />
  </div>

  <ViewTabs
    bind:activeView
    {allowedViews}
    on:view-change={onViewChange}
  />

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
    flex: 0 0 32px;
  }

  .bridge-controls {
    flex: 0 0 40px;
    display: flex;
    align-items: center;
    padding: 0 var(--space-sm);
    gap: var(--space-sm);
    background: var(--bg-panel);
    border-bottom: 2px solid var(--tier-accent, var(--border-default));
    position: relative;
    z-index: 99;
  }

  .controls-spacer { flex: 1; }

  :global(.view-tabs) {
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
  }
</style>
