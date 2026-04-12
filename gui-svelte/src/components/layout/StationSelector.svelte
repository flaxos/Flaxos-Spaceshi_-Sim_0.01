<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { playerShipId } from "../../lib/stores/playerShip.js";

  const dispatch = createEventDispatcher<{
    "station-claimed": { station: string };
    "station-released": { station: string };
  }>();

  const STATIONS = [
    { id: "captain",         label: "CAPTAIN",         color: "#ffcc00" },
    { id: "helm",            label: "HELM",            color: "#00aaff" },
    { id: "tactical",        label: "TACTICAL",        color: "#ff4444" },
    { id: "ops",             label: "OPS",             color: "#00ff88" },
    { id: "engineering",     label: "ENGINEERING",     color: "#ff8800" },
    { id: "comms",           label: "COMMS",           color: "#aa88ff" },
    { id: "science",         label: "SCIENCE",         color: "#44ddff" },
    { id: "fleet_commander", label: "FLEET CMDR",      color: "#ff66cc" },
  ];

  let registered = false;
  let assignedShipId: string | null = null;
  let claimedStation: string | null = null;
  let isProcessing = false;
  let statusText = "Not registered";
  let statusVariant: "info" | "success" | "error" | "" = "";
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let expanded = false; // compact mode in status bar

  $: canClaim = registered && !!assignedShipId && !isProcessing;

  // Watch ship ID from store for auto-assign
  $: if ($playerShipId && registered && !assignedShipId) {
    tryAssignShip($playerShipId);
  }

  function setStatus(msg: string, variant: typeof statusVariant = "") {
    statusText = msg;
    statusVariant = variant;
  }

  async function beginRegistration() {
    if (isProcessing || registered) return;
    isProcessing = true;
    setStatus("Registering...", "info");
    try {
      const resp = await wsClient.send("register_client", { client_name: "bridge-gui" }) as { ok?: boolean; error?: string };
      if (resp && resp.ok !== false) {
        registered = true;
        setStatus("Registered. Load a scenario to continue.", "info");
        startPolling();
        const shipId = $playerShipId;
        if (shipId) await tryAssignShip(shipId);
      } else {
        setStatus(`Registration failed: ${resp?.error ?? "rejected"}`, "error");
      }
    } catch (err: unknown) {
      setStatus(`Registration error: ${(err as Error).message}`, "error");
    } finally {
      isProcessing = false;
    }
  }

  async function tryAssignShip(shipId: string) {
    if (assignedShipId === shipId) return;
    setStatus(`Assigning to ship ${shipId}...`, "info");
    try {
      const resp = await wsClient.send("assign_ship", { ship: shipId }) as { ok?: boolean; error?: string };
      if (resp && resp.ok !== false) {
        assignedShipId = shipId;
        setStatus("Assigned. Select a station.", "success");
      } else {
        setStatus(`Ship assign failed: ${resp?.error ?? "rejected"}`, "error");
      }
    } catch (err: unknown) {
      setStatus(`Assign error: ${(err as Error).message}`, "error");
    }
  }

  async function claimStation(stationId: string) {
    if (isProcessing) return;
    isProcessing = true;
    setStatus(`Claiming ${stationId.toUpperCase()}...`, "info");
    try {
      const resp = await wsClient.send("claim_station", { station: stationId }) as { ok?: boolean; error?: string };
      if (resp && resp.ok !== false) {
        claimedStation = stationId;
        setStatus(`Station: ${stationId.toUpperCase()}`, "success");
        dispatch("station-claimed", { station: stationId });
      } else {
        setStatus(`Claim failed: ${resp?.error ?? "rejected"}`, "error");
      }
    } catch (err: unknown) {
      setStatus(`Claim error: ${(err as Error).message}`, "error");
    } finally {
      isProcessing = false;
    }
  }

  async function releaseStation() {
    if (isProcessing || !claimedStation) return;
    isProcessing = true;
    const prev = claimedStation;
    setStatus("Releasing...", "info");
    try {
      const resp = await wsClient.send("release_station", {}) as { ok?: boolean; error?: string };
      if (resp && resp.ok !== false) {
        claimedStation = null;
        setStatus("Station released. Select a new station.", "info");
        dispatch("station-released", { station: prev });
      } else {
        setStatus(`Release failed: ${resp?.error ?? "rejected"}`, "error");
      }
    } catch (err: unknown) {
      setStatus(`Release error: ${(err as Error).message}`, "error");
    } finally {
      isProcessing = false;
    }
  }

  async function pollStatus() {
    if (!wsClient.isConnected) return;
    if (registered && !assignedShipId && $playerShipId) {
      await tryAssignShip($playerShipId);
    }
    try {
      const resp = await wsClient.send("my_status", {}) as { ok?: boolean; station?: string; ship_id?: string };
      if (resp?.ok !== false) {
        if (resp.ship_id && resp.ship_id !== assignedShipId) assignedShipId = resp.ship_id;
        // Detect server-side station assignment (e.g. auto-captain on load_scenario)
        if (resp.station !== undefined && resp.station !== claimedStation) {
          const prev = claimedStation;
          claimedStation = resp.station ?? null;
          // Emit station-claimed so App.svelte can apply view restrictions
          if (claimedStation && claimedStation !== prev) {
            dispatch("station-claimed", { station: claimedStation });
          }
        }
      }
    } catch { /* non-critical */ }
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollStatus, 5000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function onStatusChange() {
    if (wsClient.isConnected && !registered) beginRegistration();
  }

  function onScenarioLoaded() {
    if (registered && !assignedShipId && $playerShipId) tryAssignShip($playerShipId);
  }

  onMount(() => {
    wsClient.addEventListener("status_change", onStatusChange);
    document.addEventListener("scenario-loaded", onScenarioLoaded);
    if (wsClient.isConnected && !registered) beginRegistration();
  });

  onDestroy(() => {
    wsClient.removeEventListener("status_change", onStatusChange);
    document.removeEventListener("scenario-loaded", onScenarioLoaded);
    stopPolling();
  });

  function hexToRgb(hex: string): string {
    const h = hex.replace("#", "");
    return `${parseInt(h.slice(0,2),16)}, ${parseInt(h.slice(2,4),16)}, ${parseInt(h.slice(4,6),16)}`;
  }

  function stationColor(id: string): string {
    return STATIONS.find((s) => s.id === id)?.color ?? "#888899";
  }
</script>

<div class="station-selector">
  {#if claimedStation}
    <!-- Compact display when station is claimed -->
    <button
      class="claimed-badge"
      style="color: {stationColor(claimedStation)}; border-color: {stationColor(claimedStation)}; background: rgba({hexToRgb(stationColor(claimedStation))}, 0.12)"
      on:click={() => expanded = !expanded}
      title="Click to change station"
    >
      {STATIONS.find(s => s.id === claimedStation)?.label ?? claimedStation}
    </button>
  {:else}
    <!-- Expand button for unclaimed state -->
    <button class="expand-btn" on:click={() => expanded = !expanded}>
      STATION {expanded ? "▴" : "▾"}
    </button>
  {/if}

  {#if expanded}
    <div class="station-panel">
      <div class="status-row status-{statusVariant}">{statusText}</div>

      {#if claimedStation}
        <button class="release-btn" disabled={isProcessing} on:click={releaseStation}>
          Release Station
        </button>
      {:else}
        <div class="station-grid">
          {#each STATIONS as s, i}
            <button
              class="station-btn"
              class:full-width={i === STATIONS.length - 1 && STATIONS.length % 2 !== 0}
              disabled={!canClaim || claimedStation === s.id}
              class:active={claimedStation === s.id}
              style={claimedStation === s.id ? `border-color: ${s.color}; color: ${s.color}; background: rgba(${hexToRgb(s.color)}, 0.12)` : ""}
              on:click={() => claimStation(s.id)}
            >
              {s.label}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .station-selector {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-xs);
  }

  .claimed-badge,
  .expand-btn {
    padding: 3px 10px;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 700;
    letter-spacing: 0.5px;
    background: transparent;
    border-radius: 3px;
    min-height: unset;
    cursor: pointer;
  }

  .expand-btn {
    color: var(--text-dim);
    border-color: var(--border-default);
  }

  .station-panel {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 200;
    background: var(--bg-panel);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: var(--space-sm);
    min-width: 220px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  }

  .status-row {
    font-size: var(--font-size-xs);
    color: var(--text-dim);
    margin-bottom: var(--space-sm);
    font-family: var(--font-mono);
  }
  .status-info    { color: var(--status-info); }
  .status-success { color: var(--status-nominal); }
  .status-error   { color: var(--status-critical); }

  .station-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 5px;
  }

  .station-btn {
    padding: 8px 6px;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    text-align: center;
    border-radius: var(--radius-sm);
    cursor: pointer;
    min-height: unset;
    transition: all var(--transition-fast);
  }

  .station-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .station-btn:hover:not(:disabled) { background: var(--bg-hover); }
  .station-btn.full-width { grid-column: 1 / -1; }

  .release-btn {
    width: 100%;
    padding: 8px;
    color: var(--status-critical);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    border-color: var(--border-default);
    min-height: unset;
  }

  .release-btn:hover:not(:disabled) {
    background: rgba(255, 68, 68, 0.1);
    border-color: var(--status-critical);
  }
</style>
