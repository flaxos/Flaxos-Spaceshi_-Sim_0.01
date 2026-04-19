<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { playerShipId } from "../../lib/stores/playerShip.js";

  const dispatch = createEventDispatcher<{
    "station-claimed": { station: string };
    "station-released": { station: string };
  }>();

  const STATIONS = [
    { id: "captain",         label: "CAPTAIN",         icon: "✦", desc: "Full command authority", color: "#ffcc00" },
    { id: "helm",            label: "HELM",            icon: "⛵", desc: "Flight and navigation", color: "#00aaff" },
    { id: "tactical",        label: "TACTICAL",        icon: "⊕", desc: "Weapons and fire control", color: "#ff4444" },
    { id: "ops",             label: "OPS",             icon: "⚙", desc: "Crew and ship operations", color: "#00ff88" },
    { id: "engineering",     label: "ENGINEERING",     icon: "⚛", desc: "Reactor and thermal control", color: "#ff8800" },
    { id: "comms",           label: "COMMS",           icon: "◈", desc: "Hailing and traffic", color: "#aa88ff" },
    { id: "science",         label: "SCIENCE",         icon: "◎", desc: "Sensor analysis", color: "#44ddff" },
    { id: "fleet_commander", label: "FLEET CMDR",      icon: "◇", desc: "Fleet coordination", color: "#ff66cc" },
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
        expanded = false;
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

  function stationMeta(id: string) {
    return STATIONS.find((s) => s.id === id);
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
      <div class="panel-summary">
        <div class="summary-chip" class:ok={registered}>
          <span class="chip-label">Link</span>
          <span class="chip-value">{registered ? "READY" : "OFFLINE"}</span>
        </div>
        <div class="summary-chip" class:ok={!!assignedShipId}>
          <span class="chip-label">Ship</span>
          <span class="chip-value">{assignedShipId ?? "UNASSIGNED"}</span>
        </div>
        <div class="summary-chip" class:ok={!!claimedStation}>
          <span class="chip-label">Role</span>
          <span class="chip-value">{claimedStation ? (stationMeta(claimedStation)?.label ?? claimedStation.toUpperCase()) : "OPEN"}</span>
        </div>
      </div>
      <div class="status-row status-{statusVariant}">{statusText}</div>

      {#if claimedStation}
        <div class="claimed-card" style="--claimed-color: {stationColor(claimedStation)};">
          <div class="claimed-icon">{stationMeta(claimedStation)?.icon ?? "•"}</div>
          <div class="claimed-copy">
            <div class="claimed-label">{stationMeta(claimedStation)?.label ?? claimedStation}</div>
            <div class="claimed-desc">{stationMeta(claimedStation)?.desc ?? "Active bridge assignment"}</div>
          </div>
        </div>
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
              style="--station-color: {s.color}; --station-rgb: {hexToRgb(s.color)}"
              on:click={() => claimStation(s.id)}
            >
              <span class="station-btn-icon" aria-hidden="true">{s.icon}</span>
              <span class="station-btn-copy">
                <span class="station-btn-label">{s.label}</span>
                <span class="station-btn-desc">{s.desc}</span>
              </span>
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
    display: inline-flex;
    align-items: center;
    justify-content: center;
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
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.018), transparent 18%),
      var(--bg-panel);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: var(--space-sm);
    min-width: 320px;
    box-shadow: 0 10px 34px rgba(0,0,0,0.58);
  }

  .panel-summary {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
    margin-bottom: var(--space-sm);
  }

  .summary-chip {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 7px 8px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--bg-input);
    min-width: 0;
  }

  .summary-chip.ok {
    border-color: rgba(var(--tier-accent-rgb, 30, 140, 255), 0.3);
    background: rgba(var(--tier-accent-rgb, 30, 140, 255), 0.08);
  }

  .chip-label,
  .chip-value {
    font-family: var(--font-mono);
    text-transform: uppercase;
  }

  .chip-label {
    font-size: 0.52rem;
    letter-spacing: 0.1em;
    color: var(--text-dim);
  }

  .chip-value {
    font-size: 0.58rem;
    font-weight: 700;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
    gap: 6px;
  }

  .claimed-card {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: var(--space-sm);
    padding: 10px;
    border: 1px solid rgba(var(--tier-accent-rgb, 30, 140, 255), 0.24);
    border-left: 3px solid var(--claimed-color, var(--tier-accent));
    border-radius: var(--radius-sm);
    background: rgba(var(--tier-accent-rgb, 30, 140, 255), 0.08);
  }

  .claimed-icon {
    width: 28px;
    height: 28px;
    display: grid;
    place-items: center;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.04);
    color: var(--claimed-color, var(--tier-accent));
    font-size: 0.95rem;
    flex-shrink: 0;
  }

  .claimed-copy {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .claimed-label,
  .claimed-desc {
    font-family: var(--font-mono);
  }

  .claimed-label {
    font-size: 0.68rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: 0.06em;
  }

  .claimed-desc {
    font-size: 0.55rem;
    color: var(--text-secondary);
  }

  .station-btn {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 9px;
    text-align: left;
    border-radius: var(--radius-sm);
    cursor: pointer;
    min-height: unset;
    transition: all var(--transition-fast);
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.018), transparent 70%),
      var(--bg-input);
    border: 1px solid rgba(var(--station-rgb, 136, 136, 153), 0.22);
  }

  .station-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .station-btn:hover:not(:disabled) {
    background:
      linear-gradient(180deg, rgba(var(--station-rgb, 136, 136, 153), 0.12), transparent 70%),
      var(--bg-hover);
    border-color: rgba(var(--station-rgb, 136, 136, 153), 0.58);
    transform: translateY(-1px);
  }
  .station-btn.full-width { grid-column: 1 / -1; }

  .station-btn-icon {
    width: 22px;
    display: grid;
    place-items: center;
    color: var(--station-color, var(--tier-accent));
    font-size: 0.95rem;
    line-height: 1;
    flex-shrink: 0;
    margin-top: 1px;
  }

  .station-btn-copy {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }

  .station-btn-label,
  .station-btn-desc {
    font-family: var(--font-mono);
  }

  .station-btn-label {
    font-size: 0.61rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--text-primary);
    text-transform: uppercase;
  }

  .station-btn-desc {
    font-size: 0.54rem;
    color: var(--text-secondary);
    line-height: 1.35;
  }

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

  @media (max-width: 768px) {
    .station-selector {
      width: 100%;
    }

    .claimed-badge,
    .expand-btn {
      width: 100%;
      justify-content: space-between;
    }

    .station-panel {
      left: 0;
      right: 0;
      min-width: 0;
      max-width: min(100vw - 12px, 420px);
      max-height: min(60vh, 420px);
      overflow-y: auto;
    }
  }

  @media (max-width: 480px) {
    .station-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
